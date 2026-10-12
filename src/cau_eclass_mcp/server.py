"""
CAU e-class MCP Server (CAU-ON API Version)
Provides tools to read e-class dashboard, announcements, and assignments
"""

import os
import logging
import threading
from contextvars import ContextVar
from datetime import datetime, timezone
import anyio
import httpx
import jsonschema
from typing import Optional
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, CallToolResult, ToolAnnotations

from .auth import CauAuthenticator
from .cau_on_client import CAUOnClient
from .utils.credentials import get_credentials, CredentialManager
from .utils.cache import get_cached, set_cached, clear_cache

# Create MCP server instance
app = Server("cau-eclass", version="0.2.0")
logger = logging.getLogger(__name__)
remote_mode: ContextVar[bool] = ContextVar("cau_remote_mode", default=False)
_client_lock = threading.RLock()

# Global client instances
_authenticator: Optional[CauAuthenticator] = None
_cau_on_client: Optional[CAUOnClient] = None


def get_cau_on_client() -> CAUOnClient:
    """Get or initialize CAU-ON API client with SSO authentication"""
    global _authenticator, _cau_on_client

    if _cau_on_client is not None and _authenticator is not None:
        previous_login = _authenticator.last_auth_time
        if not _authenticator.ensure_authenticated():
            reset_client()
            raise RuntimeError("School session expired. Reconnect your CAU account.")
        if previous_login != _authenticator.last_auth_time:
            _cau_on_client.close()
            _cau_on_client = CAUOnClient(_authenticator.session)
            clear_cache()

    if _cau_on_client is None:
        # Get credentials from keyring, environment variables, or prompt
        creds = get_credentials()

        # Initialize authenticator
        _authenticator = CauAuthenticator(creds["username"], creds["password"])

        # Perform SSO login
        if not _authenticator.login():
            raise RuntimeError(
                "Failed to authenticate with CAU SSO. Please check your credentials."
            )

        # Create CAU-ON client with authenticated session
        _cau_on_client = CAUOnClient(_authenticator.session)

    return _cau_on_client


def reset_client() -> None:
    """Clear school sessions and cached private data; caller holds the client lock."""
    global _authenticator, _cau_on_client
    if _cau_on_client is not None:
        _cau_on_client.close()
    if _authenticator is not None:
        _authenticator.session.close()
    _authenticator = None
    _cau_on_client = None
    clear_cache()


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available MCP tools"""
    tools = [
        Tool(
            name="get_dashboard",
            description="Get courses returned by the school favorites dashboard with course names, IDs, and terms. This may be a subset of all enrollments.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="get_course_details",
            description="Get detailed course content: weekly lectures, assignments, or files",
            inputSchema={
                "type": "object",
                "properties": {
                    "course_id": {"type": "string", "description": "Course ID"},
                    "content_type": {
                        "type": "string",
                        "enum": ["weekly", "assignments", "files"],
                        "description": "Type of content to retrieve (default: 'weekly')",
                    },
                },
                "required": ["course_id"],
            },
        ),
        Tool(
            name="download_file",
            description="Download a file from e-class. Automatically routes to Obsidian vault (90_자료 folder with auto-numbering) if save_path is omitted.",
            inputSchema={
                "type": "object",
                "properties": {
                    "course_id": {
                        "type": "string",
                        "description": "Course ID (from dashboard or announcement)",
                    },
                    "file_id": {
                        "type": "string",
                        "description": "File ID (from announcement attachments)",
                    },
                    "save_path": {
                        "type": "string",
                        "description": "Optional local file path to save override. If omitted, saves to Obsidian vault automatically.",
                    },
                    "filename": {
                        "type": "string",
                        "description": "Filename hint (e.g., 'week1.pdf') for auto-routing.",
                    },
                },
                "required": ["course_id", "file_id"],
            },
        ),
        Tool(
            name="get_vod_info",
            description="Get direct streaming URLs and metadata for a VOD content ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "content_id": {
                        "type": "string",
                        "description": "VOD Content ID (from module items or weekly view)",
                    }
                },
                "required": ["content_id"],
            },
        ),
        Tool(
            name="get_daily_briefing",
            description="Get a unified summary of upcoming deadlines, new messages, and recent course updates",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
    ]
    tools.extend(
        [
            Tool(
                name="get_connection_status",
                description="Check whether school credentials are configured and a school session exists. Does not attempt school login or reveal credentials.",
                inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
            ),
            Tool(
                name="get_announcements",
                description="Read recent course announcements, their full text, original links, and attachments.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "course_id": {"type": "string", "pattern": "^[0-9]+$"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
                    },
                    "required": ["course_id"],
                    "additionalProperties": False,
                },
            ),
        ]
    )
    for tool in tools:
        tool.inputSchema["additionalProperties"] = False
        for field in ("course_id", "file_id", "content_id"):
            if field in tool.inputSchema["properties"]:
                tool.inputSchema["properties"][field]["pattern"] = (
                    "^[A-Za-z0-9_-]{1,128}$" if field == "content_id" else "^[0-9]+$"
                )
        tool.annotations = ToolAnnotations(
            readOnlyHint=tool.name != "download_file" or remote_mode.get(),
            destructiveHint=False,
            openWorldHint=True,
        )
        if tool.name == "download_file" and remote_mode.get():
            tool.inputSchema["properties"].pop("save_path", None)
            tool.inputSchema["properties"].pop("filename", None)
            tool.description = "Return a school-authenticated browser download link for an accessible course file. The browser must be signed in to CAU e-class. Does not write a server-side file."
    return tools


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> CallToolResult:
    definitions = {tool.name: tool for tool in await list_tools()}
    if name not in definitions:
        return CallToolResult(
            isError=True, content=[TextContent(type="text", text="Unknown tool.")]
        )
    try:
        jsonschema.validate(arguments, definitions[name].inputSchema)
    except jsonschema.ValidationError:
        return CallToolResult(
            isError=True,
            content=[
                TextContent(
                    type="text", text="Invalid tool arguments. Check IDs and allowed parameters."
                )
            ],
        )

    def invoke():
        with _client_lock:
            return anyio.run(_dispatch_tool, name, arguments)

    # CAU's existing requests/httpx clients are synchronous. Serialize this
    # single-account runtime on a worker thread instead of blocking ASGI.
    return await anyio.to_thread.run_sync(invoke)


async def _dispatch_tool(name: str, arguments: dict) -> CallToolResult:
    """Handle tool calls"""

    try:
        if name == "get_connection_status":
            status = {
                "credentials_configured": CredentialManager().check_credentials_exist(),
                "school_session_exists": _authenticator is not None
                and _authenticator.authenticated,
                "mode": "remote" if remote_mode.get() else "stdio",
                "single_account": True,
            }
            return CallToolResult(
                content=[TextContent(type="text", text="CAU e-class connection status")],
                structuredContent=status,
            )
        client = get_cau_on_client()

        if name == "get_dashboard":
            content = await handle_get_dashboard(client)

        elif name == "get_course_details":
            course_id = arguments.get("course_id")
            content_type = arguments.get("content_type", "weekly")
            content = await handle_get_course_details(client, course_id, content_type)

        elif name == "download_file":
            course_id = arguments.get("course_id")
            file_id = arguments.get("file_id")
            save_path = arguments.get("save_path")
            filename = arguments.get("filename")
            if remote_mode.get():
                if not client.get_file_info(course_id, file_id):
                    raise RuntimeError("File is unavailable.")
                url = f"https://eclass3.cau.ac.kr/courses/{course_id}/files/{file_id}/download"
                content = [
                    TextContent(
                        type="text",
                        text=f"[Download course file]({url})\nOpen this link in a browser signed in to CAU e-class.",
                    )
                ]
            else:
                content = await handle_download_file(
                    client, course_id, file_id, save_path, filename
                )

        elif name == "get_vod_info":
            content_id = arguments.get("content_id")
            content = await handle_get_vod_info(client, content_id)

        elif name == "get_daily_briefing":
            content = await handle_get_daily_briefing(client)

        elif name == "get_announcements":
            content = await handle_list_announcements(
                client, arguments["course_id"], arguments.get("limit", 20)
            )

        else:
            raise ValueError("Unknown tool")
        return CallToolResult(
            content=content,
            structuredContent={
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "timezone": "Asia/Seoul",
            },
        )

    except Exception as exc:
        logger.warning("CAU tool failed: %s (%s)", name, type(exc).__name__)
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (401, 403):
            reset_client()
            message = "School session expired or access was denied. Reconnect your CAU account."
        elif isinstance(exc, RuntimeError) and not CredentialManager().check_credentials_exist():
            message = "School credentials are not configured. Set them up on the server; do not send passwords in chat."
        else:
            message = "CAU e-class lookup failed. Retry or check the school connection. This is not an empty result."
        return CallToolResult(isError=True, content=[TextContent(type="text", text=message)])


async def handle_get_dashboard(client: CAUOnClient) -> list[TextContent]:
    """Handle get_dashboard tool call"""

    # Check cache (5 min)
    cache_key = "dashboard"
    cached = get_cached(cache_key, max_age_seconds=300)

    if cached:
        courses = cached
    else:
        # Fetch courses via CAU-ON API
        courses = client.get_courses()

        if not courses:
            return [TextContent(type="text", text="No active courses found.")]

        # Cache response
        set_cached(cache_key, courses)

    # Format output
    output = "# CAU e-class Dashboard (CAU-ON)\n\n"
    output += f"Total active courses: {len(courses)}\n\n"

    for course in courses:
        output += f"## {course.get('name', 'Unknown Course')}\n"
        output += f"- **Course ID**: {course.get('id')}\n"

        if course.get("course_code"):
            output += f"- **Course Code**: {course['course_code']}\n"

        # Handle term information
        term = course.get("term")
        if term:
            if isinstance(term, dict):
                output += f"- **Term**: {term.get('name', 'Unknown')}\n"
            else:
                output += f"- **Term**: {term}\n"

        if course.get("workflow_state"):
            output += f"- **Status**: {course['workflow_state']}\n"

        output += "\n"

    return [TextContent(type="text", text=output)]


async def handle_list_announcements(
    client: CAUOnClient, course_id: str, limit: int
) -> list[TextContent]:
    """Handle list_course_announcements tool call"""

    # Check cache (2 min)
    cache_key = f"announcements_{course_id}_{limit}"
    cached = get_cached(cache_key, max_age_seconds=120)

    if cached:
        announcements = cached
    else:
        # Fetch announcements via CAU-ON API
        announcements = client.get_course_announcements(course_id, limit)

        if not announcements:
            return [TextContent(type="text", text=f"No announcements found for course {course_id}")]

        set_cached(cache_key, announcements)

    # Format output
    output = f"# Course Announcements (Course ID: {course_id})\n\n"
    output += f"Total: {len(announcements)} announcements\n\n"

    from bs4 import BeautifulSoup

    for item in announcements:
        output += f"## {item.get('title', 'Untitled')}\n"
        if item.get("posted_at"):
            output += f"- Posted: {client._convert_utc_to_kst(item['posted_at'])}\n"
        if item.get("id"):
            output += f"- Source: https://eclass3.cau.ac.kr/courses/{course_id}/discussion_topics/{item['id']}\n"
        output += BeautifulSoup(item.get("message", ""), "lxml").get_text("\n", strip=True) + "\n"
        for attachment in client.extract_attachments_from_html(item.get("message", "")):
            output += f"- Attachment: {attachment.get('filename', 'file')} (File ID: {attachment.get('file_id')})\n"
        output += "\n"

    return [TextContent(type="text", text=output)]


async def handle_get_course_details(
    client: CAUOnClient, course_id: str, content_type: str
) -> list[TextContent]:
    """Handle get_course_details tool call by routing to specific content handlers"""
    if content_type == "assignments":
        return await handle_list_assignments(client, course_id)
    elif content_type == "files":
        return await handle_list_course_files(client, course_id)
    else:  # default "weekly"
        return await handle_get_weekly_view(client, course_id)


async def handle_list_assignments(client: CAUOnClient, course_id: str) -> list[TextContent]:
    """Handle list_assignments logic (internal)"""

    # Check cache (2 min)
    cache_key = f"assignments_{course_id}"
    cached = get_cached(cache_key, max_age_seconds=120)

    if cached:
        assignments = cached
    else:
        # Fetch assignments via CAU-ON API (now includes submissions)
        assignments = client.get_course_assignments(course_id)

        if not assignments:
            return [TextContent(type="text", text=f"No assignments found for course {course_id}")]

        set_cached(cache_key, assignments)

    # Format output
    output = f"# Assignments (Course ID: {course_id})\n\n"
    output += f"Total: {len(assignments)} assignments\n\n"

    for assign in assignments:
        # Get submission info if available
        sub = assign.get("submission", {})
        workflow_state = sub.get("workflow_state", "unknown")

        status_emoji = {
            "submitted": "✅",
            "graded": "📊",
            "pending_review": "⏳",
            "unsubmitted": "❌",
        }.get(workflow_state, "❓")

        # Use actual assignment name
        name = assign.get("name", f"Assignment ID: {assign.get('id')}")
        output += f"## {status_emoji} {name}\n"

        output += f"- **Assignment ID**: {assign.get('id')}\n"
        output += f"- **Status**: {workflow_state}\n"

        if assign.get("due_at"):
            output += f"- **Due At**: {client._convert_utc_to_kst(assign['due_at'])}\n"

        if assign.get("points_possible") is not None:
            output += f"- **Points Possible**: {assign['points_possible']}\n"

        if sub.get("submitted_at"):
            output += f"- **Submitted At**: {sub['submitted_at']}\n"

        if sub.get("score") is not None:
            output += f"- **Score**: {sub['score']}\n"

        if sub.get("grade"):
            output += f"- **Grade**: {sub['grade']}\n"

        # Show flags
        flags = []
        if sub.get("late"):
            flags.append("⚠️ Late")
        if sub.get("missing"):
            flags.append("❌ Missing")

        if flags:
            output += f"- **Flags**: {', '.join(flags)}\n"

        output += "\n"

    return [TextContent(type="text", text=output)]


async def handle_download_file(
    client: CAUOnClient,
    course_id: str,
    file_id: str,
    save_path: str = None,
    filename_hint: str = None,
) -> list[TextContent]:
    """Handle download_file tool call"""
    import os

    # Get file metadata first
    file_info = client.get_file_info(course_id, file_id)

    if not file_info:
        return [TextContent(type="text", text=f"Failed to get file info for file_id={file_id}")]

    filename = file_info.get("display_name", file_info.get("filename", filename_hint or "unknown"))
    filesize = file_info.get("size", 0)

    # If save_path is None, the client will auto-calculate it.
    # We need to know what it will be for the final report.
    actual_save_path = save_path
    if actual_save_path is None:
        actual_save_path = client._get_auto_save_path(course_id, filename)

    # Download file
    success = client.download_file(course_id, file_id, actual_save_path, filename)

    if success:
        # Verify file was saved
        if os.path.exists(actual_save_path):
            actual_size = os.path.getsize(actual_save_path)
            output = f"# File Download Successful\n\n"
            output += f"- **Filename**: {filename}\n"
            output += f"- **File ID**: {file_id}\n"
            output += f"- **Course ID**: {course_id}\n"
            output += f"- **Expected Size**: {filesize:,} bytes\n"
            output += f"- **Downloaded Size**: {actual_size:,} bytes\n"
            output += f"- **Saved to**: `{actual_save_path}`\n"

            if actual_size == filesize:
                output += f"\n✅ **File size matches - download verified**"
            else:
                # In some cases size might differ slightly due to transfer encoding, but usually matches
                output += f"\n⚠️ **Note: File size differs (Expected: {filesize}, Actual: {actual_size})**"

            return [TextContent(type="text", text=output)]
        else:
            return [
                TextContent(
                    type="text",
                    text=f"Download reported success but file not found at {actual_save_path}",
                )
            ]
    else:
        return [
            TextContent(
                type="text", text=f"Failed to download file: {filename} (file_id={file_id})"
            )
        ]


async def handle_list_course_files(client: CAUOnClient, course_id: str) -> list[TextContent]:
    """Handle list_course_files tool call"""
    # Check cache (5 min)
    cache_key = f"files_{course_id}"
    cached = get_cached(cache_key, max_age_seconds=300)

    if cached:
        files = cached
    else:
        files = client.get_course_files(course_id)

        if not files:
            return [TextContent(type="text", text=f"No files found for course {course_id}")]

        set_cached(cache_key, files)

    output = f"# Course Files (자료실)\n\n"
    output += f"**Course ID**: {course_id}\n"
    output += f"**Total Files**: {len(files)}\n\n"

    for f in files:
        output += f"### {f.get('display_name', f.get('filename', 'Unknown'))}\n"
        output += f"- **File ID**: {f.get('id')}\n"
        output += f"- **Size**: {f.get('size', 0):,} bytes\n"
        if f.get("created_at"):
            output += f"- **Created At**: {f['created_at']}\n"
        output += "\n"

    return [TextContent(type="text", text=output)]


async def handle_get_weekly_view(client: CAUOnClient, course_id: str) -> list[TextContent]:
    """Handle get_weekly_view tool call"""
    # Check cache (5 min)
    cache_key = f"weekly_{course_id}"
    cached = get_cached(cache_key, max_age_seconds=300)

    if cached:
        modules = cached
    else:
        modules = client.get_learningx_modules(course_id)
        if not modules:
            return [
                TextContent(type="text", text=f"No LearningX modules found for course {course_id}")
            ]
        set_cached(cache_key, modules)

    output = f"# Weekly Study View (주차별 학습)\n\n"
    output += f"**Course ID**: {course_id}\n\n"

    for mod in modules:
        output += f"## {mod.get('title', 'Unnamed Module')}\n"
        items = mod.get("module_items", [])

        if not items:
            output += "- _No items in this week_\n\n"
            continue

        for item in items:
            title = item.get("title", "Untitled")
            item_type = item.get("type", "Unknown")
            output += f"### {title}\n"
            output += f"- **Type**: {item_type}\n"

            # Show attendance/progress for video content
            if item_type == "lecture":
                att = item.get("attendance_status", {})
                status = (
                    "✅ Completed"
                    if att.get("attendance_status") == "attendance"
                    else "Attendance status: " + str(att.get("attendance_status", "unknown"))
                )
                output += f"- **Attendance**: {status}\n"
                if att.get("progress"):
                    output += f"- **Progress**: {att['progress']}%\n"
                if item.get("content_id"):
                    output += f"- **Content ID (for VOD info)**: {item['content_id']}\n"

            elif item_type == "assignment":
                sub = item.get("submission_status", {})
                status = (
                    "✅ Submitted"
                    if sub.get("workflow_state") in ["submitted", "graded"]
                    else "Submission status: " + str(sub.get("workflow_state", "unknown"))
                )
                output += f"- **Status**: {status}\n"
                if item.get("due_at"):
                    output += f"- **Due**: {item['due_at']}\n"

            output += "\n"

    return [TextContent(type="text", text=output)]


async def handle_get_vod_info(client: CAUOnClient, content_id: str) -> list[TextContent]:
    """Handle get_vod_info tool call"""
    info = client.get_ocs_content_info(content_id)

    if not info:
        return [
            TextContent(type="text", text=f"Failed to fetch VOD info for content_id={content_id}")
        ]

    output = f"# VOD Content Information\n\n"
    output += f"**Title**: {info.get('title', 'Unknown')}\n"
    output += f"**Content ID**: {content_id}\n"
    output += f"**Content Type**: {info.get('content_type', 'Unknown')}\n\n"

    output += "## Streaming URLs (Media URIs)\n"
    media_uris = info.get("media_uris", [])
    if not media_uris:
        output += "_No streaming links found._\n"
    else:
        for uri in media_uris:
            output += f"### {uri.get('target', 'Default')} ({uri.get('method', 'N/A')})\n"
            output += f"- **URL**: {uri.get('url')}\n\n"

    return [TextContent(type="text", text=output)]


async def handle_get_daily_briefing(client: CAUOnClient) -> list[TextContent]:
    """Handle get_daily_briefing tool call"""
    # Fetch data from multiple endpoints
    todo_items = client.get_todo_items()
    conversations = client.get_conversations(limit=5)
    activity_stream = client.get_activity_stream()

    output = "# 📅 Daily Briefing (중앙대 e-class 요약)\n\n"

    # 1. Deadlines (Todo)
    output += "## 🚨 마감 임박 (Upcoming Deadlines)\n"
    if not todo_items:
        output += "_현재 예정된 할 일이 없습니다._\n"
    else:
        ordered_items = sorted(
            todo_items,
            key=lambda item: item.get("assignment", {}).get("due_at")
            or item.get("quiz", {}).get("due_at")
            or "9999",
        )
        for item in ordered_items[:10]:  # Show the nearest deadlines first
            course_name = item.get("context_name", "Unknown Course")
            title = item.get("title", "Untitled")
            due_at = item.get("assignment", {}).get("due_at") or item.get("quiz", {}).get("due_at")

            status = ""
            if item.get("needs_grading_count"):
                status = " (채점 대기 중)"

            output += f"- **[{course_name}]** {title}\n"
            if due_at:
                output += f"  - 마감: {client._convert_utc_to_kst(due_at)}\n"
    output += "\n"

    # 2. Messages (Inbox)
    output += "## 📩 새로운 쪽지 (Recent Messages)\n"
    unread_messages = [c for c in conversations if c.get("workflow_state") == "unread"]
    display_messages = unread_messages if unread_messages else conversations[:3]

    if not display_messages:
        output += "_최근 받은 쪽지가 없습니다._\n"
    else:
        for conv in display_messages:
            author = conv.get("participants", [{}])[0].get("name", "Unknown")
            subject = conv.get("subject", "No Subject")
            last_msg = conv.get("last_message", "...")
            unread_tag = "🔴 [미읽음] " if conv.get("workflow_state") == "unread" else ""

            output += f"- {unread_tag}**{author}**: {subject}\n"
            output += f"  - _{last_msg[:50]}..._\n"
    output += "\n"

    # 3. Activity Stream
    output += "## 🆕 최근 업데이트 (Activity Stream)\n"
    if not activity_stream:
        output += "_최근 업데이트 소식이 없습니다._\n"
    else:
        # Categorize by type
        for activity in activity_stream[:7]:
            act_type = activity.get("type", "Message")
            title = activity.get("title", "Notification")
            course = activity.get("course_name", "")

            emoji = {
                "Announcement": "📢",
                "Conversation": "✉️",
                "Assignment": "📝",
                "Submission": "📤",
                "GradeChange": "📊",
            }.get(act_type, "🔔")

            output += f"- {emoji} **{title}**"
            if course:
                output += f" ({course})"
            output += "\n"

    return [TextContent(type="text", text=output)]


async def main():
    """Main entry point for MCP server"""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())

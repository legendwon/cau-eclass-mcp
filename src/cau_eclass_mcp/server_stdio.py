"""
CAU e-class MCP Server - stdio transport
Entry point for stdio mode (default, for Claude Code integration)
"""

from mcp.server.stdio import stdio_server
from .server import app


async def main():
    """Main entry point for stdio transport"""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )

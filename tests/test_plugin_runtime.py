import asyncio
import io
import time
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import jwt
import pytest
import requests
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from mcp.server.auth.provider import AccessToken

from cau_eclass_mcp import server
from cau_eclass_mcp.cau_on_client import CAUOnClient
from cau_eclass_mcp.server_http import OwnerTokenVerifier, RemoteSettings, create_app
from cau_eclass_mcp.utils.cache import clear_cache, get_cached, set_cached
from cau_eclass_mcp.utils.credentials import CredentialManager

SETTINGS = RemoteSettings(
    "https://eclass.example.org",
    "https://identity.example.org/",
    "https://identity.example.org/jwks",
    "owner-123",
)


class TestVerifier:
    async def verify_token(self, token):
        if token != "test-owner-token":
            return None
        return AccessToken(
            token=token,
            client_id="chatgpt",
            scopes=["eclass:read"],
            subject="owner-123",
            resource=SETTINGS.resource,
            expires_at=int(time.time()) + 300,
        )


def test_remote_initialization_discovery_and_safe_call(monkeypatch):
    monkeypatch.setattr(CredentialManager, "check_credentials_exist", lambda self: False)
    app = create_app(SETTINGS, token_verifier=TestVerifier())
    with TestClient(app, base_url=SETTINGS.public_url) as client:
        assert client.get("/health").status_code == 200
        response = client.post("/mcp", json={})
        assert response.status_code == 401
        assert "oauth-protected-resource/mcp" in response.headers["www-authenticate"]
        assert (
            client.get("/.well-known/oauth-protected-resource/mcp").json()["resource"]
            == SETTINGS.resource
        )
        assert (
            client.post("/api/credentials", json={"username": "no", "password": "no"}).status_code
            == 404
        )
        client.headers.update(
            {
                "Authorization": "Bearer test-owner-token",
                "Accept": "application/json, text/event-stream",
            }
        )
        response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
        )
        assert response.status_code == 200, response.text
        assert "serverInfo" in response.json()["result"]
        client.headers["MCP-Protocol-Version"] = response.json()["result"]["protocolVersion"]
        response = client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = {item["name"]: item for item in response.json()["result"]["tools"]}
        assert len(tools) == 7
        assert "save_path" not in tools["download_file"]["inputSchema"]["properties"]
        response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "get_connection_status", "arguments": {}},
            },
        )
        assert response.json()["result"]["structuredContent"]["mode"] == "remote"
        assert response.json()["result"]["structuredContent"]["credentials_configured"] is False
        response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "get_dashboard", "arguments": {}},
            },
        )
        assert response.json()["result"]["isError"] is True


@pytest.mark.parametrize(
    "change",
    [
        {"sub": "another-user"},
        {"aud": "https://other.example/mcp"},
        {"iss": "https://other.example/"},
        {"exp": 1},
        {"scope": "other:read"},
        {"scope": ["eclass:read"]},
    ],
)
def test_oauth_rejects_invalid_claims(change):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = OwnerTokenVerifier(SETTINGS)
    verifier.jwks.get_signing_key_from_jwt = Mock(
        return_value=SimpleNamespace(key=key.public_key())
    )
    claims = {
        "sub": SETTINGS.owner_subject,
        "iss": SETTINGS.issuer,
        "aud": SETTINGS.resource,
        "exp": int(time.time()) + 300,
        "scope": "eclass:read",
    }
    token = jwt.encode(claims | change, key, algorithm="RS256")
    assert asyncio.run(verifier.verify_token(token)) is None


def test_oauth_valid_token_and_bad_signature():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = OwnerTokenVerifier(SETTINGS)
    verifier.jwks.get_signing_key_from_jwt = Mock(
        return_value=SimpleNamespace(key=key.public_key())
    )
    claims = {
        "sub": SETTINGS.owner_subject,
        "iss": SETTINGS.issuer,
        "aud": SETTINGS.resource,
        "exp": int(time.time()) + 300,
        "scope": "eclass:read",
    }
    assert (
        asyncio.run(verifier.verify_token(jwt.encode(claims, key, algorithm="RS256"))) is not None
    )
    assert asyncio.run(verifier.verify_token(jwt.encode(claims, other, algorithm="RS256"))) is None


def test_no_credentials_never_prompts(monkeypatch):
    monkeypatch.setattr(CredentialManager, "load_credentials", lambda self: None)
    monkeypatch.setattr("builtins.input", lambda *args: pytest.fail("MCP must not prompt on stdin"))
    with pytest.raises(RuntimeError, match="not configured"):
        CredentialManager().get_credentials()


def test_remote_download_returns_school_link_without_local_write(monkeypatch):
    client = SimpleNamespace(get_file_info=lambda course_id, file_id: {"id": file_id})
    monkeypatch.setattr(server, "get_cau_on_client", lambda: client)
    flag = server.remote_mode.set(True)
    try:
        result = asyncio.run(
            server.call_tool("download_file", {"course_id": "42", "file_id": "123"})
        )
        assert result.isError is False
        assert "/courses/42/files/123/download" in result.content[0].text
        result = asyncio.run(
            server.call_tool(
                "download_file", {"course_id": "42", "file_id": "123", "save_path": "/tmp/private"}
            )
        )
        assert result.isError is True
    finally:
        server.remote_mode.reset(flag)


def test_api_failure_is_not_an_empty_briefing():
    client = CAUOnClient(requests.Session())
    client._make_request = Mock(side_effect=httpx.ReadTimeout("school timed out"))
    try:
        with pytest.raises(httpx.ReadTimeout):
            client.get_todo_items()
    finally:
        client.close()


def test_announcements_include_body_link_and_attachment(monkeypatch):
    clear_cache()
    client = CAUOnClient(requests.Session())
    client.get_course_announcements = Mock(
        return_value=[
            {
                "id": 8,
                "title": "시험 공지",
                "message": "<p>다음 주 시험</p><a class='instructure_file_link' href='/courses/42/files/123/download'>강의안.pdf</a>",
            }
        ]
    )
    try:
        result = asyncio.run(server.handle_list_announcements(client, "42", 1))
        assert "다음 주 시험" in result[0].text
        assert "discussion_topics/8" in result[0].text
        assert "123" in result[0].text
    finally:
        client.close()
        clear_cache()


def test_session_refresh_rebuilds_client_and_clears_cache(monkeypatch):
    old = Mock()
    auth = SimpleNamespace(last_auth_time=1, session=requests.Session())

    def refresh():
        auth.last_auth_time = 2
        return True

    auth.ensure_authenticated = refresh
    monkeypatch.setattr(server, "_authenticator", auth)
    monkeypatch.setattr(server, "_cau_on_client", old)
    new = Mock()
    monkeypatch.setattr(server, "CAUOnClient", lambda session: new)
    set_cached("private", "old account data")
    assert server.get_cau_on_client() is new
    old.close.assert_called_once()
    assert get_cached("private") is None


def test_cookie_domains_are_preserved():
    session = requests.Session()
    session.cookies.set("school-secret", "never-send-to-ocs", domain="eclass3.cau.ac.kr", path="/")
    session.cookies.set("shared-cookie", "shared", domain=".cau.ac.kr", path="/")
    client = CAUOnClient(session)
    client._session_initialized = True
    seen = []

    def respond(request):
        seen.append(request.headers.get("cookie", ""))
        return httpx.Response(200, json={})

    client.http2_client.close()
    client.http2_client = httpx.Client(transport=httpx.MockTransport(respond))
    try:
        client._make_request("GET", "https://ocs.cau.ac.kr/test")
        assert "school-secret" not in seen[0]
        assert "shared-cookie" in seen[0]
    finally:
        client.close()

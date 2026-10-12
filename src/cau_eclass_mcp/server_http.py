"""Single-owner, OAuth-protected Streamable HTTP MCP service.

The authorization server is an existing OAuth provider. CAU's portal login
is a separate backend session and is never exposed as a tool argument.
"""

import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from urllib.parse import urlsplit

import anyio
import jwt
import uvicorn
from fastapi import FastAPI
from mcp.server.auth.middleware.auth_context import AuthContextMiddleware
from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend, RequireAuthMiddleware
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.routes import create_protected_resource_routes
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.responses import HTMLResponse
from starlette.routing import Route

from . import server

logger = logging.getLogger(__name__)
READ_SCOPE = "eclass:read"


@dataclass(frozen=True)
class RemoteSettings:
    public_url: str
    issuer: str
    jwks_url: str
    owner_subject: str

    def __post_init__(self):
        for name in ("public_url", "issuer", "jwks_url"):
            value = getattr(self, name)
            parsed = urlsplit(value)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    f"{name} must be an absolute HTTPS URL without credentials, query, or fragment"
                )
        if urlsplit(self.public_url).path not in ("", "/"):
            raise ValueError("CAU_MCP_PUBLIC_URL must be an origin, without /mcp")
        if not self.owner_subject.strip():
            raise ValueError("CAU_MCP_OWNER_SUB must identify the permitted OAuth user")

    @property
    def resource(self):
        return self.public_url.rstrip("/") + "/mcp"

    @classmethod
    def from_env(cls):
        names = (
            "CAU_MCP_PUBLIC_URL",
            "CAU_MCP_OAUTH_ISSUER",
            "CAU_MCP_JWKS_URL",
            "CAU_MCP_OWNER_SUB",
        )
        missing = [name for name in names if not os.environ.get(name)]
        if missing:
            raise ValueError("Missing remote connection settings: " + ", ".join(missing))
        return cls(*(os.environ[name] for name in names))


class OwnerTokenVerifier(TokenVerifier):
    """Validate JWTs from one configured provider and allow exactly one user."""

    def __init__(self, settings: RemoteSettings):
        self.settings = settings
        self.jwks = jwt.PyJWKClient(settings.jwks_url, timeout=5)

    async def verify_token(self, token: str) -> AccessToken | None:
        def verify():
            key = self.jwks.get_signing_key_from_jwt(token).key
            return jwt.decode(
                token,
                key,
                algorithms=["RS256", "ES256"],
                audience=self.settings.resource,
                issuer=self.settings.issuer,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )

        try:
            claims = await anyio.to_thread.run_sync(verify)
            scope = claims.get("scope", "")
            if not isinstance(scope, str) or claims["sub"] != self.settings.owner_subject:
                return None
            scopes = scope.split()
            if READ_SCOPE not in scopes:
                return None
            return AccessToken(
                token=token,
                client_id=claims.get("client_id") or claims.get("azp") or claims["sub"],
                subject=claims["sub"],
                scopes=scopes,
                expires_at=claims["exp"],
                resource=self.settings.resource,
            )
        except (jwt.PyJWTError, ValueError, TypeError, OSError):
            logger.debug("OAuth token validation failed")
            return None


class RemoteTransport:
    def __init__(self, manager):
        self.manager = manager

    async def __call__(self, scope, receive, send):
        token = server.remote_mode.set(True)
        try:
            await self.manager.handle_request(scope, receive, send)
        finally:
            server.remote_mode.reset(token)


def create_app(
    settings: RemoteSettings | None = None, *, token_verifier: TokenVerifier | None = None
) -> FastAPI:
    settings = settings or RemoteSettings.from_env()
    verifier = token_verifier or OwnerTokenVerifier(settings)
    parsed = urlsplit(settings.public_url)
    manager = StreamableHTTPSessionManager(
        app=server.app,
        stateless=True,
        json_response=True,
        security_settings=TransportSecuritySettings(
            allowed_hosts=[parsed.netloc, "127.0.0.1:*", "localhost:*"],
            allowed_origins=[settings.public_url.rstrip("/")],
        ),
        max_request_body_size=1024 * 1024,
    )

    @asynccontextmanager
    async def lifespan(app):
        async with manager.run():
            yield

        def close():
            with server._client_lock:
                server.reset_client()

        await anyio.to_thread.run_sync(close)

    app = FastAPI(
        title="CAU e-class MCP",
        version="0.2.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(AuthContextMiddleware)
    app.add_middleware(
        AuthenticationMiddleware,
        backend=BearerAuthBackend(verifier, resource_server_url=AnyHttpUrl(settings.resource)),
    )

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "cau-eclass-mcp", "version": "0.2.0"}

    @app.get("/", response_class=HTMLResponse)
    async def home():
        return "<!doctype html><html lang='ko'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>CAU e-class</title><body><h1>CAU e-class</h1><p>중앙대 수강 과목, 과제, 공지, 강의자료를 대화로 확인하는 개인용 플러그인입니다.</p><p>ChatGPT 플러그인 연결 주소는 이 서버의 /mcp 입니다. 연결에는 등록된 사용자 계정이 필요합니다.</p></body></html>"

    metadata_url = AnyHttpUrl(
        settings.public_url.rstrip("/") + "/.well-known/oauth-protected-resource/mcp"
    )
    app.router.routes.extend(
        create_protected_resource_routes(
            resource_url=AnyHttpUrl(settings.resource),
            authorization_servers=[AnyHttpUrl(settings.issuer)],
            scopes_supported=[READ_SCOPE],
            resource_name="CAU e-class",
        )
    )
    app.router.routes.append(
        Route(
            "/mcp",
            endpoint=RequireAuthMiddleware(
                RemoteTransport(manager),
                required_scopes=[READ_SCOPE],
                resource_metadata_url=metadata_url,
            ),
            methods=["GET", "POST", "DELETE"],
        )
    )
    return app


async def main(host: str = "127.0.0.1", port: int = 8000):
    config = uvicorn.Config(create_app(), host=host, port=port, log_level="info")
    await uvicorn.Server(config).serve()

"""
CAU e-class MCP Server - SSE transport with Web UI
Entry point for SSE mode (for web clients and non-developer setup)
"""

import uvicorn
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.sse import SseServerTransport
from starlette.requests import Request

from .server import app as mcp_app
from .web_api import router as web_router
from .utils.credentials import CredentialManager


def create_app(port: int = 8000) -> FastAPI:
    """Create FastAPI application with dynamic CORS based on port"""
    app = FastAPI(
        title="CAU e-class MCP Server",
        description="MCP server for CAU e-class integration with SSE transport and Web UI",
        version="0.1.0"
    )

    # Dynamic CORS: only allow localhost on the actual port
    allowed_origins = [
        f"http://localhost:{port}",
        f"http://127.0.0.1:{port}",
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "Accept"],
    )

    # Mount web API endpoints
    app.include_router(web_router, prefix="/api")

    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint"""
        return {"status": "ok", "service": "cau-eclass-mcp"}

    # Serve web UI at root
    @app.get("/")
    async def serve_ui():
        """Serve the web UI HTML page"""
        static_dir = Path(__file__).parent / "static"
        index_path = static_dir / "index.html"

        if not index_path.exists():
            return {
                "error": "Web UI not found",
                "message": "index.html is missing from static directory"
            }

        return FileResponse(index_path)

    # Mount static files for CSS/JS if needed
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # MCP SSE endpoint
    @app.get("/mcp/sse")
    async def handle_sse_info():
        """MCP SSE endpoint info"""
        return {
            "message": "MCP SSE endpoint",
            "note": "Full SSE transport implementation coming soon. Use stdio mode for now.",
            "stdio_mode": "python -m cau_eclass_mcp"
        }

    return app


async def main(host: str = "127.0.0.1", port: int = 8000):
    """Main entry point for SSE transport with web UI"""

    # Security warning for non-localhost binding
    is_exposed = host != "127.0.0.1" and host != "localhost"

    # Check credentials and display startup message
    cred_manager = CredentialManager()
    credentials_configured = cred_manager.check_credentials_exist()

    print("")
    print("=" * 70)
    print("CAU e-class MCP Server - SSE Mode")
    print("=" * 70)
    print(f"Server starting on http://{host}:{port}")

    if is_exposed:
        print("")
        print("⚠️  WARNING: Server is exposed to the network!")
        print("   Credential endpoints are restricted to localhost,")
        print("   but consider using 127.0.0.1 for maximum security.")
        print("")

    if not credentials_configured:
        print("\n[!] No credentials configured!")
        print(f"    Open http://{host}:{port} in your browser to set up credentials")
    else:
        print("\n[OK] Credentials configured")

    print(f"\nEndpoints:")
    print(f"  - Web UI: http://{host}:{port}")
    print(f"  - API Docs: http://{host}:{port}/docs")
    print(f"  - MCP SSE: http://{host}:{port}/mcp/sse")
    print(f"\nPress Ctrl+C to stop the server")
    print("=" * 70)
    print("")

    # Create app with correct port for CORS
    app = create_app(port=port)

    # Start uvicorn server
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()

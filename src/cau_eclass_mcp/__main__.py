"""
Entry point for running MCP server as a module

Usage:
    python -m cau_eclass_mcp              # stdio mode (default, for Claude Code)
    python -m cau_eclass_mcp --sse        # SSE mode with web UI
    python -m cau_eclass_mcp --sse --port 9000  # Custom port
"""

import argparse
import asyncio


def main():
    """Main entry point with CLI argument parsing"""
    parser = argparse.ArgumentParser(
        description="CAU e-class MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m cau_eclass_mcp                    # stdio mode (default)
  python -m cau_eclass_mcp --sse              # SSE mode with web UI
  python -m cau_eclass_mcp --sse --port 9000  # Custom port
  python -m cau_eclass_mcp --sse --host 0.0.0.0  # Allow external connections
        """
    )

    parser.add_argument(
        "--sse",
        action="store_true",
        help="Run in SSE mode with web UI (default: stdio mode)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for SSE server (default: 8000)"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host for SSE server (default: 127.0.0.1)"
    )

    args = parser.parse_args()

    if args.sse:
        # Import SSE server
        from .server_sse import main as sse_main
        asyncio.run(sse_main(host=args.host, port=args.port))
    else:
        # Import stdio server (default)
        from .server_stdio import main as stdio_main
        asyncio.run(stdio_main())


if __name__ == "__main__":
    main()

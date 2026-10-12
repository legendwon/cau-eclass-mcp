"""Build a self-contained local package, or a verified remote MCP package."""

import argparse
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent


def verify_endpoint(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path != "/mcp"
    ):
        raise ValueError("Remote URL must be the actual HTTPS /mcp endpoint")
    metadata_url = f"https://{parsed.netloc}/.well-known/oauth-protected-resource/mcp"
    with urlopen(metadata_url, timeout=10) as response:
        metadata = json.load(response)
    if metadata.get("resource") != url or not metadata.get("authorization_servers"):
        raise ValueError("Server must advertise matching OAuth protected resource metadata")


def build(output, remote_url=None):
    if remote_url:
        verify_endpoint(remote_url)
    with tempfile.TemporaryDirectory() as temp:
        package = Path(temp) / "cau-eclass"
        shutil.copytree(ROOT / "plugin", package)
        if remote_url:
            entry = {
                "type": "streamable-http",
                "url": remote_url,
                "extensions": {"com.openai": {"auth": {"type": "oauth"}}},
            }
        else:
            # uv creates the dependency environment from the bundled project;
            # user credentials remain in the local keyring/environment.
            entry = {
                "type": "stdio",
                "command": "uv",
                "args": [
                    "run",
                    "--project",
                    "${PLUGIN_ROOT}/server",
                    "python",
                    "-m",
                    "cau_eclass_mcp",
                ],
                "cwd": "${PLUGIN_ROOT}/server",
            }
            project = package / "server"
            project.mkdir()
            shutil.copytree(
                ROOT / "src",
                project / "src",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"),
            )
            for filename in ("pyproject.toml", "README.md", "LICENSE", "uv.lock"):
                if (ROOT / filename).exists():
                    shutil.copy2(ROOT / filename, project / filename)
        config = {
            "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
            "mcpServers": {"cau-eclass": entry},
        }
        (package / "mcp.json").write_text(
            json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        manifest = json.loads((package / "plugin.json").read_text())
        interface = manifest["extensions"]["com.openai"]["interface"]
        if len(interface["shortDescription"]) > 30:
            raise ValueError("Plugin shortDescription exceeds 30 characters")
        if not remote_url:
            (package / "LOCAL_ONLY.txt").write_text(
                "This package runs a local Python MCP process. It is for clients with local stdio support. Uploading it does not make it available to ChatGPT web/mobile. Install uv and configure the school keyring locally with cau-eclass-mcp --setup.\n"
            )
        output = Path(output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(package.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(package.parent))
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--remote-url",
        help="Actual deployed HTTPS /mcp URL; OAuth metadata is verified before packaging",
    )
    parser.add_argument("--output", default="dist/cau-eclass-local.zip")
    args = parser.parse_args()
    try:
        print(build(args.output, args.remote_url))
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()

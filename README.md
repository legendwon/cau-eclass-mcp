# CAU e-class MCP

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

MCP (Model Context Protocol) server for integrating CAU e-class platform with Claude Code. Access your courses, announcements, assignments, and lecture modules directly through Claude.

> **Note**: This is an unofficial tool created by students for students. Use at your own risk.

## Features

- **Dashboard Access**: View all active courses with metadata (names, IDs, terms)
- **Announcements**: Read course announcements without opening a browser
- **Assignments**: Check assignments and submission status with due dates
- **Lecture Modules**: View weekly lecture modules with attendance tracking
- **Dual Transport**: stdio mode (for Claude Code) + SSE mode (web UI)
- **Web UI**: Browser-based credential setup and server monitoring
- **Cross-Platform**: Works on Windows, macOS, and Linux
- **Secure Credentials**: Uses OS keyring for secure credential storage

## Quick Start

### Prerequisites

- Python 3.10 or higher
- CAU student account with e-class access
- [Claude Code](https://claude.com/code) installed

### Installation

Install directly from GitHub:

```bash
pip install git+https://github.com/legendwon/-cau-eclass-mcp.git
```

Or clone and install for development:

```bash
git clone https://github.com/legendwon/-cau-eclass-mcp.git
cd -cau-eclass-mcp
pip install -e .[dev]
```

### Configuration

#### Option 1: System Keyring (Recommended)

Run the setup command to save credentials to your OS keyring:

```bash
python -c "from cau_eclass_mcp.utils.credentials import CredentialManager; m = CredentialManager(); m.prompt_for_credentials()"
```

This stores credentials securely in:
- Windows: Credential Manager
- macOS: Keychain
- Linux: Secret Service (GNOME Keyring, KWallet, etc.)

#### Option 2: Environment Variables

Set environment variables (useful for CI/CD or temporary usage):

```bash
# Linux/macOS
export CAU_USERNAME="your_student_id"
export CAU_PASSWORD="your_password"

# Windows (PowerShell)
$env:CAU_USERNAME="your_student_id"
$env:CAU_PASSWORD="your_password"
```

#### Option 3: Interactive Prompt

If no credentials are found, the MCP server will prompt you interactively on first run.

### Claude Code Setup

Add the MCP server to your Claude Code configuration:

**For global access**, edit `~/.claude/claude.json` (or `C:\Users\YourName\.claude\claude.json` on Windows):

```json
{
  "mcpServers": {
    "cau-eclass": {
      "command": "python",
      "args": ["-m", "cau_eclass_mcp"]
    }
  }
}
```

**For project-specific access**, create `.mcp.json` in your project root:

```json
{
  "cau-eclass": {
    "command": "python",
    "args": ["-m", "cau_eclass_mcp"]
  }
}
```

Restart Claude Code after configuration.

## SSE Server Mode (Web UI)

For users who prefer a graphical interface or want to set up credentials without command line tools, you can run the server in SSE (Server-Sent Events) mode with a web UI.

### Starting the SSE Server

```bash
# Default: runs on http://127.0.0.1:8000
python -m cau_eclass_mcp --sse

# Custom port
python -m cau_eclass_mcp --sse --port 9000

# Allow external connections (not recommended for security)
python -m cau_eclass_mcp --sse --host 0.0.0.0 --port 8000
```

### Web UI Features

Once the server is running, open http://localhost:8000 in your browser to access:

1. **Credential Setup**
   - Save CAU credentials to OS keyring via web form
   - Check credential configuration status
   - Delete stored credentials

2. **Server Status Dashboard**
   - Real-time server status monitoring
   - Authentication status
   - Server uptime tracking
   - Automatic status updates every 5 seconds

3. **API Documentation**
   - Interactive Swagger UI at http://localhost:8000/docs
   - Test API endpoints directly in browser

### Available Endpoints

When running in SSE mode:

- `http://localhost:8000/` - Web UI
- `http://localhost:8000/api/credentials` - Credential management
- `http://localhost:8000/api/status` - Server status
- `http://localhost:8000/health` - Health check
- `http://localhost:8000/docs` - API documentation

### Security Notes

- Server binds to `127.0.0.1` (localhost) by default
- No network exposure unless `--host 0.0.0.0` is used
- Credentials are stored in OS keyring, never exposed via API
- CORS restricted to localhost origins only

### Stopping the Server

Press `Ctrl+C` in the terminal where the server is running.

## Usage with Claude Code

Once configured, you can ask Claude to access your e-class data:

```
You: "Show my e-class dashboard"
Claude: [Lists your 8 courses with IDs and terms]

You: "List announcements for 암호와-인증 course"
Claude: [Shows recent announcements with dates and content]

You: "What assignments are due this week?"
Claude: [Lists assignments with due dates and submission status]

You: "Show lecture modules for 공공기관NCS분석"
Claude: [Displays weekly modules with attendance status]
```

## Architecture

### CAU-ON Platform

CAU uses a proprietary LMS platform called **CAU-ON** (not standard Canvas/Moodle). This MCP server:

1. Authenticates via CAU SSO portal using RSA-encrypted password
2. Obtains API-enabled session cookies
3. Interacts with Canvas-like REST APIs (`/api/v1/...`)

### Authentication Flow

```
User Input → SSO Login → RSA Password Encryption → Canvas Session
         → API-Enabled Cookie → CAU-ON API Requests
```

**Key technical details**:
- Client-side RSA decryption (server provides private key!)
- PKCS1v15 padding for password encryption
- HTTP/2 protocol support required
- Critical `Referer` header for session upgrade
- Session cookies: 208 chars (basic) → 421 chars (API-enabled)

## MCP Tools

### 1. `mcp__cau-eclass__get_dashboard`

Get overview of all active courses.

**Parameters**: None

**Returns**: List of courses with IDs, names, terms, and enrollment status

### 2. `mcp__cau-eclass__list_course_announcements`

List announcements for a specific course.

**Parameters**:
- `course_id` (string, required): Course ID from dashboard
- `limit` (integer, optional): Max announcements to return (default: 20)

**Returns**: Announcements with titles, dates, authors, and content

### 3. `mcp__cau-eclass__list_assignments`

List assignments with submission status.

**Parameters**:
- `course_id` (string, required): Course ID

**Returns**: Assignments with due dates, submission status, and scores

### 4. `mcp__cau-eclass__get_lecture_modules`

View weekly lecture modules with attendance tracking.

**Parameters**:
- `course_id` (string, required): Course ID
- `include_attendance` (boolean, optional): Include detailed attendance (slower, default: false)

**Returns**: Weekly modules with completion status and lecture items

## Usage Modes

### stdio Mode (Default)

For Claude Code integration:

```bash
python -m cau_eclass_mcp
```

This runs the server in stdio mode, communicating via standard input/output. Credentials must be configured via command line or environment variables before use.

### SSE Mode (Web UI)

For graphical credential setup and monitoring:

```bash
python -m cau_eclass_mcp --sse
```

Open http://localhost:8000 in your browser to configure credentials and monitor server status.

## Troubleshooting

### "Failed to authenticate with CAU SSO"

- Verify your student ID and password are correct
- **Web UI method**: Navigate to http://localhost:8000 (if using SSE mode) and update credentials
- **Command line method**: Delete and re-enter credentials:
  ```bash
  python -c "from cau_eclass_mcp.utils.credentials import CredentialManager; m = CredentialManager(); m.delete_credentials()"
  ```

### "Keyring not available"

If keyring fails, use environment variables instead:
```bash
export CAU_USERNAME="your_id"
export CAU_PASSWORD="your_password"
```

### MCP server not responding

1. Test the server manually:
   ```bash
   # stdio mode
   python -m cau_eclass_mcp

   # SSE mode (should show startup message)
   python -m cau_eclass_mcp --sse
   ```
2. Check Claude Code logs for errors
3. Verify `.mcp.json` or `claude.json` configuration

### Web UI not loading

If running `--sse` mode but web UI doesn't load:

1. Check if the server started successfully (should show "Server starting on...")
2. Verify the port is not in use: `netstat -an | findstr :8000` (Windows) or `lsof -i :8000` (macOS/Linux)
3. Try a different port: `python -m cau_eclass_mcp --sse --port 9000`
4. Check browser console for errors

### Session expired errors

Sessions are cached for 1 hour. If you see session errors, restart Claude Code to trigger re-authentication.

## Development

### Running Tests

```bash
pip install -e .[dev]
pytest tests/ -v
```

### Code Formatting

```bash
black src/ tests/
ruff check src/ tests/
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Security

This tool stores credentials securely using OS keyring. However:

- Never commit credentials to version control
- Use strong CAU portal passwords
- Report security issues via GitHub Issues (privately if needed)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built with [Model Context Protocol (MCP)](https://modelcontextprotocol.io/)
- Powered by [Claude Code](https://claude.com/code)
- Developed through 13 hours of debugging CAU-ON's proprietary API

## Disclaimer

This is an **unofficial** tool created by students. It is not affiliated with, endorsed by, or supported by Chung-Ang University. Use at your own risk.

The tool accesses e-class data through the same APIs used by the official web interface, but:
- CAU may change their APIs without notice (breaking this tool)
- Excessive API usage may trigger rate limiting
- Always comply with CAU's acceptable use policies

---

**Questions or Issues?** Open an issue on [GitHub](https://github.com/legendwon/-cau-eclass-mcp/issues)

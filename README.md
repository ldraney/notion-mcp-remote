# notion-mcp-remote

A remote MCP (Model Context Protocol) connector that exposes [notion-mcp](https://pypi.org/project/notion-mcp/) over Streamable HTTP with Notion OAuth 2.0 — making it available as a custom connector in Claude.ai, including mobile.

## Why This Exists

Anthropic's built-in Notion connector uses an older API surface. The `notion-mcp` package provides significantly better coverage of Notion's API (v2025-05-09), including:

- Full database CRUD with data source management
- Block-level operations (append, update, delete)
- Page property retrieval and pagination
- Comment threading
- User and team lookups
- Enhanced Markdown content support

**This repo** is a thin deployment wrapper that:
1. Imports all tools from `notion-mcp`
2. Serves them over Streamable HTTP (required for remote MCP)
3. Handles Notion's public OAuth 2.0 flow (per-user authentication)
4. Deploys behind ngrok for free, stable HTTPS

```
┌─────────────────────────────────────────────────┐
│  Claude.ai / Claude Mobile                      │
│  (adds connector via Settings → Connectors)     │
└──────────────────┬──────────────────────────────┘
                   │ Streamable HTTP
                   ▼
┌─────────────────────────────────────────────────┐
│  notion-mcp-remote (this repo)                  │
│  ┌───────────────┐  ┌────────────────────────┐  │
│  │ OAuth 2.0     │  │ FastMCP HTTP Transport │  │
│  │ (Notion flow) │  │ (Streamable HTTP)      │  │
│  └───────┬───────┘  └───────────┬────────────┘  │
│          │                      │               │
│          ▼                      ▼               │
│  ┌──────────────────────────────────────────┐   │
│  │  notion-mcp (PyPI package)               │   │
│  │  All Notion API tools & domain logic     │   │
│  └──────────────────────────────────────────┘   │
└──────────────────┬──────────────────────────────┘
                   │ ngrok tunnel
                   ▼
          https://ldraney.ngrok-free.app
```

## Prerequisites

- Python 3.11+
- [ngrok account](https://ngrok.com/) (free tier — 1 static domain)
- [Notion public integration](https://www.notion.so/profile/integrations) (OAuth client credentials)
- A machine to host on (always-on Linux box, Raspberry Pi, etc.)

## Notion OAuth Setup

Before deploying, you need a **public** Notion integration (not an internal one):

1. Go to [notion.so/profile/integrations](https://www.notion.so/profile/integrations)
2. Click **"New integration"**
3. Choose **"Public"** integration type
4. Fill in required fields:
   - **Integration name**: e.g. "Notion MCP Remote"
   - **Redirect URI**: `https://ldraney.ngrok-free.app/oauth/callback`
   - **Company name**, **Website**, **Privacy policy URL**, **Terms of use URL**
   - (These can point to your GitHub repo pages for now)
5. Under **Capabilities**, enable everything you want to expose
6. Save and note your **OAuth client ID** and **OAuth client secret**

> **Note**: Notion requires company info and policy URLs even for free/hobby integrations. A simple GitHub Pages site or even raw markdown files in your repo work fine.

## Installation

```bash
git clone https://github.com/ldraney/notion-mcp-remote.git
cd notion-mcp-remote
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Copy the example env file and fill in your values:

```bash
cp .env.example .env
```

```env
# Notion OAuth (from your public integration)
NOTION_OAUTH_CLIENT_ID=your_client_id
NOTION_OAUTH_CLIENT_SECRET=your_client_secret

# Server
HOST=127.0.0.1
PORT=8000
BASE_URL=https://ldraney.ngrok-free.app

# Session secret (generate with: python -c "import secrets; print(secrets.token_hex(32))")
SESSION_SECRET=your_random_secret

# Optional: Redis URL for token storage (defaults to local file-based storage)
# REDIS_URL=redis://localhost:6379
```

## Project Structure

```
notion-mcp-remote/
├── server.py              # Main entrypoint — FastMCP HTTP server
├── auth/
│   ├── __init__.py
│   ├── oauth.py           # Notion OAuth 2.0 flow handlers
│   └── storage.py         # Per-user token storage (file or Redis)
├── requirements.txt
├── .env.example
├── systemd/
│   └── notion-mcp-remote.service
├── Makefile
└── README.md
```

## Running Locally

### 1. Start the MCP server

```bash
source .venv/bin/activate
python server.py
```

Server starts on `http://127.0.0.1:8000`.

### 2. Start the ngrok tunnel

In a separate terminal:

```bash
# First time: set up your free static domain at https://dashboard.ngrok.com/domains
ngrok http 8000 --url=ldraney.ngrok-free.app
```

Your server is now reachable at `https://ldraney.ngrok-free.app`.

### 3. Verify

```bash
# Health check
curl https://ldraney.ngrok-free.app/health

# MCP endpoint should be at:
# https://ldraney.ngrok-free.app/mcp
```

## Deployment (Systemd)

For always-on hosting on a Linux box:

### Install ngrok

```bash
# Arch Linux
yay -S ngrok
# or download from https://ngrok.com/download

# Authenticate
ngrok config add-authtoken YOUR_TOKEN
```

### Set up systemd services

```bash
# Copy service files
sudo cp systemd/notion-mcp-remote.service /etc/systemd/system/
sudo cp systemd/ngrok-notion.service /etc/systemd/system/

# Edit paths in service files to match your setup
sudo systemctl daemon-reload

# Enable and start
sudo systemctl enable --now notion-mcp-remote
sudo systemctl enable --now ngrok-notion

# Check status
sudo systemctl status notion-mcp-remote
sudo systemctl status ngrok-notion
```

### systemd service files

**notion-mcp-remote.service:**
```ini
[Unit]
Description=Notion MCP Remote Server
After=network.target

[Service]
Type=simple
User=ldraney
WorkingDirectory=/home/ldraney/notion-mcp-remote
EnvironmentFile=/home/ldraney/notion-mcp-remote/.env
ExecStart=/home/ldraney/notion-mcp-remote/.venv/bin/python server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**ngrok-notion.service:**
```ini
[Unit]
Description=ngrok tunnel for Notion MCP Remote
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ldraney
ExecStart=/usr/bin/ngrok http 8000 --url=ldraney.ngrok-free.app --log=stdout
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## Adding to Claude.ai

Once your server is running and the tunnel is active:

1. Go to [claude.ai](https://claude.ai) → **Settings** → **Connectors**
2. Click **"Add custom connector"**
3. Paste your MCP server URL: `https://ldraney.ngrok-free.app/mcp`
4. Claude will initiate the OAuth flow — you'll be redirected to Notion
5. Select the Notion pages/databases you want Claude to access
6. Authorize and you're connected

The connector will automatically be available on Claude iOS and Android apps as well.

> **Requires**: Claude Pro, Max, Team, or Enterprise plan

## Architecture Notes

### OAuth Flow

The three-party OAuth dance works like this:

```
Claude.ai                    This Server                    Notion
   │                            │                              │
   │  1. User adds connector    │                              │
   │ ─────────────────────────► │                              │
   │                            │                              │
   │  2. Redirect to Notion     │                              │
   │ ◄───────────────────────── │                              │
   │                            │                              │
   │  3. User authorizes ──────────────────────────────────► │
   │                            │                              │
   │                            │  4. Callback with auth code  │
   │                            │ ◄──────────────────────────  │
   │                            │                              │
   │                            │  5. Exchange for token       │
   │                            │ ─────────────────────────►   │
   │                            │                              │
   │                            │  6. Access token             │
   │                            │ ◄─────────────────────────   │
   │                            │                              │
   │  7. MCP tools now work     │  8. API calls with token     │
   │ ◄────────────────────────► │ ◄──────────────────────────► │
```

### Token Storage

Per-user Notion access tokens are stored locally by default (encrypted at rest using the `SESSION_SECRET`). For multi-instance deployments, configure `REDIS_URL` for shared token storage.

### Stateless HTTP Mode

The server uses FastMCP's stateless HTTP mode — no WebSocket connections, no session state on the server. Each request includes authentication context, making it horizontally scalable if needed.

## Development

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests
pytest

# Run with auto-reload
python server.py --reload

# Lint
ruff check .
```

## Makefile

```bash
make run          # Start the server
make tunnel       # Start ngrok tunnel
make dev          # Start both (requires tmux)
make test         # Run tests
make lint         # Run linter
make install      # Install dependencies
```

## Troubleshooting

### "Connector failed to connect" in Claude.ai
- Verify ngrok tunnel is running: `curl https://ldraney.ngrok-free.app/health`
- Check server logs: `journalctl -u notion-mcp-remote -f`
- Ensure your Notion OAuth redirect URI matches exactly

### OAuth callback errors
- Confirm `BASE_URL` in `.env` matches your ngrok domain exactly
- Check that your Notion integration is set to **Public** (not Internal)
- Verify redirect URI in Notion integration settings matches `{BASE_URL}/oauth/callback`

### Token refresh issues
- Notion access tokens don't expire by default, but users can revoke access
- If a user revokes, they'll need to re-authorize through Claude's connector settings

### ngrok free tier limits
- 1 static domain (sufficient for this use case)
- Rate limits apply but are generous for MCP connector traffic
- If you hit limits, consider upgrading or switching to Cloudflare Tunnel with a custom domain

## Roadmap

- [ ] Core HTTP wrapper with FastMCP Streamable HTTP transport
- [ ] Notion public OAuth 2.0 flow
- [ ] Per-user token storage and injection
- [ ] Claude.ai connector integration testing
- [ ] Encrypted token storage at rest
- [ ] Redis adapter for multi-instance deployments
- [ ] Health check and monitoring endpoints
- [ ] Rate limiting and abuse prevention
- [ ] Docker deployment option
- [ ] One-click deploy templates (Railway, Render)

## Related Projects

- [notion-mcp](https://pypi.org/project/notion-mcp/) — The underlying MCP server with full Notion API coverage (also by [@ldraney](https://github.com/ldraney))
- [FastMCP](https://gofastmcp.com) — The MCP framework powering the HTTP transport
- [MCP Specification](https://modelcontextprotocol.io) — The Model Context Protocol standard

## License

MIT

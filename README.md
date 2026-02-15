# notion-mcp-remote

A remote MCP connector for [notion-mcp](https://pypi.org/project/notion-mcp-ldraney/) — connect Claude.ai to your Notion workspace in one step.

## For Users

Paste this URL into Claude.ai to connect:

```
https://archbox.tail5b443a.ts.net/mcp
```

1. Go to [claude.ai](https://claude.ai) → **Settings** → **Connectors**
2. Click **"Add custom connector"**
3. Paste the URL above
4. You'll be redirected to Notion — authorize access to **your own** workspace
5. Done. Claude can now read and write your Notion pages, databases, and blocks.

Works on desktop, iOS, and Android. Requires Claude Pro, Max, Team, or Enterprise.

### What you get

Full Notion API coverage via [notion-mcp](https://pypi.org/project/notion-mcp-ldraney/) (v2025-05-09):

- Page and database CRUD
- Block-level operations (append, update, delete)
- Property retrieval and pagination
- Comment threading
- Search across your workspace
- User and team lookups

### How it works

When you add this connector, Claude.ai initiates a standard OAuth 2.0 flow with Notion. **You authenticate directly with Notion and choose which pages to share.** Your access token is stored encrypted on the server and used only to make Notion API calls on your behalf. The operator of this server never sees your Notion credentials — only the OAuth token Notion issues.

```
Claude.ai                    This Server                    Notion
   │                            │                              │
   │  1. Add connector (URL)    │                              │
   │ ─────────────────────────► │                              │
   │                            │                              │
   │  2. Redirect to Notion     │                              │
   │ ◄───────────────────────── │                              │
   │                            │                              │
   │  3. You authorize ─────────────────────────────────────► │
   │     (your workspace,       │                              │
   │      your pages)           │                              │
   │                            │  4. Callback with auth code  │
   │                            │ ◄──────────────────────────  │
   │                            │                              │
   │                            │  5. Exchange for token       │
   │                            │ ─────────────────────────►   │
   │                            │                              │
   │                            │  6. Your access token        │
   │                            │ ◄─────────────────────────   │
   │                            │                              │
   │  7. MCP tools now work     │  8. API calls to YOUR data   │
   │ ◄────────────────────────► │ ◄──────────────────────────► │
```

---

## For Operators

Everything below is for deploying your own instance of this connector.

### Why This Exists

Anthropic's built-in Notion connector uses an older API surface. `notion-mcp` provides significantly better coverage. This repo is a thin deployment wrapper that:

1. Imports all tools from `notion-mcp`
2. Serves them over Streamable HTTP (required for Claude.ai connectors)
3. Handles Notion's public OAuth 2.0 flow (per-user authentication)
4. Deploys behind any HTTPS tunnel (Tailscale Funnel, ngrok, Cloudflare Tunnel, etc.)

Each user who adds your connector authenticates with **their own** Notion workspace. You provide the infrastructure; they bring their own data.

### Prerequisites

- Python 3.11+
- An HTTPS tunnel ([Tailscale Funnel](https://tailscale.com/kb/1223/funnel) (free), [ngrok](https://ngrok.com/), or [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/))
- [Notion public integration](https://www.notion.so/profile/integrations) (OAuth client credentials)
- A machine to host on (always-on Linux box, Raspberry Pi, etc.)

### Notion OAuth Setup

You need a **public** Notion integration. This is what lets users OAuth into **their own** workspaces through your connector — the "public" label means your app can be authorized by any Notion user, not that their data becomes public.

1. Go to [notion.so/profile/integrations](https://www.notion.so/profile/integrations)
2. Click **"New integration"**
3. Choose **"Public"** integration type
4. Fill in required fields:
   - **Integration name**: e.g. "Notion MCP Remote"
   - **Redirect URI**: `https://<your-domain>/oauth/callback`
   - **Company name**, **Website**, **Privacy policy URL**, **Terms of use URL** — Notion requires these even for hobby projects. Your GitHub repo URL and a simple privacy statement work fine.
5. Under **Capabilities**, enable everything you want to expose
6. Save and note your **OAuth client ID** and **OAuth client secret**

### Installation

```bash
git clone https://github.com/ldraney/notion-mcp-remote.git
cd notion-mcp-remote
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configuration

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
BASE_URL=https://your-public-domain

# Session secret (generate with: python -c "import secrets; print(secrets.token_hex(32))")
SESSION_SECRET=your_random_secret

# Optional: Redis URL for token storage (defaults to local file-based storage)
# REDIS_URL=redis://localhost:6379
```

### Running

```bash
# Terminal 1: Start the MCP server
source .venv/bin/activate
python server.py

# Terminal 2: Expose via HTTPS tunnel (pick one)
sudo tailscale funnel --bg 8000          # Tailscale Funnel (free, stable URL)
ngrok http 8000 --url=your-domain        # ngrok (requires paid plan for static domain)
```

Verify:

```bash
curl https://your-public-domain/health
```

Then share your connector URL with users: `https://your-public-domain/mcp`

### Deployment (Systemd)

For always-on hosting on a Linux box:

```bash
# Copy and enable service file
sudo cp systemd/notion-mcp-remote.service /etc/systemd/system/
# Edit paths in the service file to match your setup
sudo systemctl daemon-reload
sudo systemctl enable --now notion-mcp-remote
```

For the HTTPS tunnel, set up a separate systemd service or use your tunnel provider's daemon mode (e.g. `tailscale funnel --bg`, `ngrok service install`).

### Project Structure

```
notion-mcp-remote/
├── server.py              # Main entrypoint — FastMCP HTTP server
├── auth/
│   ├── __init__.py
│   ├── provider.py        # Notion OAuth 2.0 flow handlers
│   └── storage.py         # Per-user token storage (file or Redis)
├── requirements.txt
├── .env.example
├── systemd/
│   └── notion-mcp-remote.service
├── Makefile
└── README.md
```

### Development

```bash
pip install -r requirements-dev.txt
pytest
python server.py --reload
ruff check .
```

### Makefile

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
- Verify tunnel is running: `curl https://your-public-domain/health`
- Check server logs: `journalctl -u notion-mcp-remote -f`
- Ensure your Notion OAuth redirect URI matches exactly

### 421 Misdirected Request
- The server automatically adds `BASE_URL`'s hostname to the MCP transport security `allowed_hosts`. Make sure `BASE_URL` in `.env` matches your public domain exactly.

### OAuth callback errors
- Confirm `BASE_URL` in `.env` matches your public domain exactly
- Check that your Notion integration is set to **Public** (not Internal)
- Verify redirect URI in Notion integration settings matches `{BASE_URL}/oauth/callback`

### Token refresh issues
- Notion access tokens don't expire by default, but users can revoke access
- If a user revokes, they'll need to re-authorize through Claude's connector settings

## Roadmap

- [x] Core HTTP wrapper with FastMCP Streamable HTTP transport
- [x] Notion public OAuth 2.0 flow
- [x] Per-user token storage and injection
- [x] Claude.ai connector integration testing
- [x] Encrypted token storage at rest
- [ ] Redis adapter for multi-instance deployments
- [ ] Health check and monitoring endpoints
- [ ] Rate limiting and abuse prevention
- [ ] Docker deployment option
- [ ] One-click deploy templates (Railway, Render)

## Related Projects

- [notion-mcp](https://pypi.org/project/notion-mcp-ldraney/) — The underlying MCP server with full Notion API coverage (also by [@ldraney](https://github.com/ldraney))
- [FastMCP](https://gofastmcp.com) — The MCP framework powering the HTTP transport
- [MCP Specification](https://modelcontextprotocol.io) — The Model Context Protocol standard

## License

MIT

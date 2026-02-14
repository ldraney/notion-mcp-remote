# notion-mcp-remote

Remote MCP connector wrapping `ldraney-notion-mcp` with Notion OAuth 2.0 over Streamable HTTP.

## Architecture

Three-party OAuth proxy: Claude.ai ↔ this server ↔ Notion OAuth.

- **server.py** — Main entrypoint. Imports `mcp` from `notion_mcp`, configures auth, adds custom routes, runs Streamable HTTP.
- **auth/provider.py** — `NotionOAuthProvider` implementing `OAuthAuthorizationServerProvider`. Proxies Notion OAuth.
- **auth/storage.py** — `TokenStore` for encrypted file-based persistence of tokens, auth codes, and client registrations.
- **client_patch.py** — Monkey-patches `get_client()` in all `notion_mcp` tool modules to use a per-request `ContextVar`-based `NotionClient`.

## Key Patterns

- The `mcp` FastMCP instance is imported from `notion_mcp` and reconfigured at runtime (auth settings, host/port, stateless mode).
- `load_access_token()` in the provider sets the `ContextVar` so tool handlers get the correct per-user `NotionClient`.
- All 6 tool modules (`blocks`, `comments`, `databases`, `pages`, `search`, `users`) import `get_client` from `notion_mcp.server` — the patch replaces it in each module's namespace.
- `BASE_URL` hostname is added to `transport_security.allowed_hosts` — without this, MCP rejects requests with 421 Misdirected Request.

## Running

```bash
cp .env.example .env   # fill in values
make install
make run               # start server on :8000

# Expose via any HTTPS tunnel (Tailscale Funnel, ngrok, Cloudflare Tunnel, etc.)
```

## Testing

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/.well-known/oauth-authorization-server
curl -X POST http://127.0.0.1:8000/mcp  # should 401
```

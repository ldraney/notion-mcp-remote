"""Method-aware auth middleware for MCP StreamableHTTP.

Allows GET requests (SSE notification streams) through without OAuth
authentication. The MCP SDK's StreamableHTTP handler validates session IDs
on GET /mcp internally — a GET without a valid session_id is rejected by
the SDK, so skipping the OAuth bearer check here is safe.

POST and all other methods still go through full OAuth bearer auth.
"""

from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send

from mcp.server.auth.middleware.bearer_auth import RequireAuthMiddleware


class MethodAwareAuthMiddleware(RequireAuthMiddleware):
    """Drop-in replacement for RequireAuthMiddleware that bypasses auth for
    GET requests so claude.ai can establish the SSE notification stream.

    Usage:
        Monkey-patch into ``mcp.server.fastmcp.server`` before ``mcp.run()``
        so the SDK picks it up when building the Starlette app::

            import mcp.server.fastmcp.server as _fm
            _fm.RequireAuthMiddleware = MethodAwareAuthMiddleware
    """

    def __init__(self, app: ASGIApp, *args, **kwargs):
        super().__init__(app, *args, **kwargs)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        method = scope.get("method", "")

        # For GET requests (SSE listener), let the MCP SDK handle session
        # validation — no Bearer token required at this layer.
        if method == "GET":
            await self.app(scope, receive, send)
            return

        # Everything else (POST, DELETE, …) requires full OAuth bearer auth.
        await super().__call__(scope, receive, send)

"""ASGI middleware logging REST traffic into the activity log.

Covers the "what came in, what went back out" view for the JSON API. Tool calls
are *not* logged here — ``mcp_logging.ActivityMiddleware`` records those with
their arguments and results, and double-logging would show every model action
twice in the timeline.
"""

from __future__ import annotations

import json
import time
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from event_log import log

# Never buffered: /mcp is a long-lived MCP session and the events stream is
# infinite, so consuming their bodies here would hang the response.
_SKIP_PREFIXES = ("/mcp", "/api/events/stream", "/static/")
_SKIP_EXACT = ("/", "/favicon.ico")

# The UI polls these to draw itself. Logging them buries the model's actual tool
# calls under a wall of identical GETs, which is the opposite of what the
# timeline is for. Mutations (POST/DELETE) are always logged.
_SKIP_POLLING_GETS = frozenset({"/health", "/bots", "/api/tools", "/api/events"})

# Bodies larger than this are recorded as a placeholder instead of in full.
_MAX_BODY_BYTES = 4096


def _decode(raw: bytes) -> Any:
    if not raw:
        return None
    if len(raw) > _MAX_BODY_BYTES:
        return f"<{len(raw)} bytes>"
    try:
        return json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return raw[:_MAX_BODY_BYTES].decode("utf-8", "replace")


class HTTPActivityMiddleware:
    """Record one ``http`` event per REST request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "?")
        if (
            path.startswith(_SKIP_PREFIXES)
            or path in _SKIP_EXACT
            or (method == "GET" and path in _SKIP_POLLING_GETS)
        ):
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        request_body = bytearray()
        response_body = bytearray()
        status = {"code": 0}

        async def receive_logging() -> Message:
            message = await receive()
            if message["type"] == "http.request":
                chunk = message.get("body", b"")
                if len(request_body) <= _MAX_BODY_BYTES:
                    request_body.extend(chunk)
            return message

        async def send_logging(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            elif message["type"] == "http.response.body":
                chunk = message.get("body", b"")
                if len(response_body) <= _MAX_BODY_BYTES:
                    response_body.extend(chunk)
            await send(message)

        try:
            await self.app(scope, receive_logging, send_logging)
        finally:
            query = scope.get("query_string", b"").decode("latin-1")
            log.append(
                source="human",
                kind="http",
                name=f"{method} {path}" + (f"?{query}" if query else ""),
                arguments=_decode(bytes(request_body)),
                result=_decode(bytes(response_body)),
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
                error=None if status["code"] < 400 else f"HTTP {status['code']}",
            )

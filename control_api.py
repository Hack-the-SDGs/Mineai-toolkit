"""HTTP API and static UI, served from the same app as the MCP endpoint.

Routes are registered onto the FastMCP instance via ``custom_route`` so
``/mcp``, ``/api/*`` and the web UI all share one port and one process. That
shared process is the point: bots live in a module-global ``BotManager``, so any
second process would have its own empty one and the model would see no bots.

``BotManager`` is synchronous (minethon's Bot API is), so every call into it is
pushed to a worker thread to keep the event loop free.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from anyio import to_thread
from fastmcp import Client, FastMCP
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse

from bot_manager import manager
from event_log import log
from mcp_logging import SOURCE

STATIC_DIR = Path(__file__).with_name("static")

# How often the SSE handler checks for new events. Fast enough to feel live in a
# classroom, slow enough that an idle browser tab costs nothing.
_STREAM_POLL_SECONDS = 0.25
# Comment lines keep proxies and browsers from dropping an idle SSE connection.
_STREAM_KEEPALIVE_SECONDS = 15.0


def _error(exc: Exception, status: int = 400) -> JSONResponse:
    return JSONResponse(
        {"error": type(exc).__name__, "message": str(exc)},
        status_code=status,
    )


async def _json_body(request: Request) -> dict[str, Any]:
    raw = await request.body()
    if not raw:
        return {}
    body = json.loads(raw)
    if not isinstance(body, dict):
        msg = "JSON body must be an object."
        raise ValueError(msg)
    return body


def register_routes(mcp: FastMCP) -> None:
    """Attach the REST API, the activity feed, and the static UI to ``mcp``."""

    # --- bot lifecycle (used by the Bots tab) ------------------------------

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_request: Request) -> Response:
        bots = await to_thread.run_sync(manager.list_bots)
        return JSONResponse(
            {
                "healthy": True,
                "active_bot": manager.get_active_bot(),
                "bots": bots,
            },
        )

    @mcp.custom_route("/bots", methods=["GET"])
    async def list_bots(_request: Request) -> Response:
        return JSONResponse({"bots": await to_thread.run_sync(manager.list_bots)})

    @mcp.custom_route("/bots", methods=["POST"])
    async def create_bot(request: Request) -> Response:
        try:
            body = await _json_body(request)
            name = str(body.pop("name", "")).strip()
            account = body.pop("account", None)
            account = str(account).strip() if account is not None else None
            wait_spawn = bool(body.pop("wait_spawn", True))
            height = body.pop("height", None)
            nested = body.pop("options", {})
            if nested:
                if not isinstance(nested, dict):
                    msg = "options must be a JSON object."
                    raise ValueError(msg)
                body = {**nested, **body}
            if height is not None:
                height = int(height)

            snapshot = await to_thread.run_sync(
                lambda: manager.create_bot(
                    name,
                    account=account or None,
                    wait_spawn=wait_spawn,
                    height=height,
                    **body,
                ),
            )
        except Exception as exc:
            return _error(exc)
        return JSONResponse(snapshot, status_code=201)

    # Registered before the /bots/{name} patterns: Starlette matches in
    # registration order, so a later literal route would be swallowed by the
    # placeholder and read as a bot named "closed".
    @mcp.custom_route("/bots/closed", methods=["DELETE"])
    async def forget_closed(_request: Request) -> Response:
        """Drop every closed bot from the list in one go."""
        removed = await to_thread.run_sync(manager.forget_closed)
        return JSONResponse({"removed": removed})

    @mcp.custom_route("/bots/{name}", methods=["GET"])
    async def bot_health(request: Request) -> Response:
        name = request.path_params["name"]
        try:
            return JSONResponse(
                await to_thread.run_sync(lambda: manager.check_bot_health(name)),
            )
        except Exception as exc:
            return _error(exc, status=404)

    @mcp.custom_route("/bots/{name}/health", methods=["GET"])
    async def bot_health_alias(request: Request) -> Response:
        return await bot_health(request)

    @mcp.custom_route("/bots/{name}", methods=["DELETE"])
    async def close_bot(request: Request) -> Response:
        name = request.path_params["name"]
        try:
            return JSONResponse(
                await to_thread.run_sync(lambda: manager.close_bot(name)),
            )
        except Exception as exc:
            return _error(exc)

    @mcp.custom_route("/bots/{name}/record", methods=["DELETE"])
    async def forget_bot(request: Request) -> Response:
        """Remove a bot from the list. Closes it first if still connected."""
        name = request.path_params["name"]
        try:
            return JSONResponse(
                await to_thread.run_sync(lambda: manager.forget_bot(name)),
            )
        except Exception as exc:
            return _error(exc)

    @mcp.custom_route("/active_bot", methods=["POST"])
    async def set_active(request: Request) -> Response:
        try:
            body = await _json_body(request)
            name = str(body.get("name", "")).strip()
            return JSONResponse(
                await to_thread.run_sync(lambda: manager.set_active_bot(name)),
            )
        except Exception as exc:
            return _error(exc)

    @mcp.custom_route("/bots/{name}/activate", methods=["POST"])
    async def activate_bot(request: Request) -> Response:
        name = request.path_params["name"]
        try:
            return JSONResponse(
                await to_thread.run_sync(lambda: manager.set_active_bot(name)),
            )
        except Exception as exc:
            return _error(exc)

    # --- tool catalogue + manual invocation (the Console tab) --------------

    @mcp.custom_route("/api/tools", methods=["GET"])
    async def list_tools(_request: Request) -> Response:
        """Expose every MCP tool with its JSON schema.

        The console builds its forms from this, so it always matches the tools
        the model actually has — nothing to keep in sync by hand.
        """
        tools = await mcp._list_tools()  # noqa: SLF001 — no public equivalent
        payload = [
            {
                "name": tool.name,
                "description": tool.description or "",
                "category": _category_for(tool),
                "schema": tool.parameters,
            }
            for tool in tools
        ]
        payload.sort(key=lambda item: (item["category"], item["name"]))
        return JSONResponse({"tools": payload})

    @mcp.custom_route("/api/tools/{name}/invoke", methods=["POST"])
    async def invoke_tool(request: Request) -> Response:
        """Run one tool on the student's behalf.

        SOURCE must be set before the Client is created: the in-memory client
        copies the current context when it starts its server task, so setting it
        afterwards would tag the call as coming from the model.
        """
        name = request.path_params["name"]
        try:
            arguments = await _json_body(request)
        except Exception as exc:
            return _error(exc)

        SOURCE.set("human")
        try:
            async with Client(mcp) as client:
                result = await client.call_tool(name, arguments)
        except Exception as exc:
            return _error(exc)
        finally:
            SOURCE.set("model")

        blocks = [
            getattr(block, "text", None)
            for block in (result.content or [])
            if getattr(block, "text", None) is not None
        ]
        # Tools returning a list or dict produce structured content and no text
        # blocks at all (an empty list_bots is the common case), so fall back to
        # it rather than showing the student an empty result.
        if blocks:
            rendered: Any = blocks[0] if len(blocks) == 1 else blocks
        else:
            structured = result.structured_content or {}
            rendered = structured.get("result", structured)
        return JSONResponse(
            {
                "tool": name,
                "arguments": arguments,
                "result": rendered,
                "structured": result.structured_content,
            },
        )

    # --- activity feed ----------------------------------------------------

    @mcp.custom_route("/api/events", methods=["GET"])
    async def events(request: Request) -> Response:
        since = int(request.query_params.get("since", "0") or 0)
        rows = log.since(since) if since else log.recent()
        return JSONResponse(
            {"events": [event.as_dict() for event in rows], "last_id": log.last_id()},
        )

    @mcp.custom_route("/api/events/stream", methods=["GET"])
    async def events_stream(request: Request) -> Response:
        """Server-sent events feed of the activity log."""
        since = int(request.query_params.get("since", "0") or 0)

        async def publish():
            last_id = since
            last_ping = time.monotonic()
            # Replay recent history so a freshly opened tab isn't blank.
            if not last_id:
                for event in log.recent(50):
                    last_id = event.id
                    yield f"data: {json.dumps(event.as_dict())}\n\n"
            while True:
                if await request.is_disconnected():
                    return
                for event in log.since(last_id):
                    last_id = event.id
                    yield f"data: {json.dumps(event.as_dict())}\n\n"
                    last_ping = time.monotonic()
                if time.monotonic() - last_ping > _STREAM_KEEPALIVE_SECONDS:
                    last_ping = time.monotonic()
                    yield ": keepalive\n\n"
                await asyncio.sleep(_STREAM_POLL_SECONDS)

        return StreamingResponse(
            publish(),
            media_type="text/event-stream",
            headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
        )

    @mcp.custom_route("/api/events", methods=["DELETE"])
    async def clear_events(_request: Request) -> Response:
        log.clear()
        return JSONResponse({"cleared": True})

    # --- static UI --------------------------------------------------------

    @mcp.custom_route("/", methods=["GET"])
    async def index(_request: Request) -> Response:
        return FileResponse(STATIC_DIR / "index.html")

    @mcp.custom_route("/static/{filename}", methods=["GET"])
    async def static_file(request: Request) -> Response:
        filename = request.path_params["filename"]
        path = (STATIC_DIR / filename).resolve()
        if STATIC_DIR.resolve() not in path.parents or not path.is_file():
            return JSONResponse({"error": "not_found"}, status_code=404)
        return FileResponse(path)


def _category_for(tool: Any) -> str:
    """Group tools by the module that defines them.

    Taken from ``tools/<name>.py`` rather than matched on name prefixes, so a
    tool added to an existing module is grouped correctly with no change here.
    """
    module = getattr(getattr(tool, "fn", None), "__module__", "") or ""
    return module.rsplit(".", 1)[-1] if module.startswith("tools.") else "other"

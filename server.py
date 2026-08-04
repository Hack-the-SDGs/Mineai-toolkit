"""Build the single control service: MCP endpoint + REST API + web UI.

One process owns everything. ``bot_manager.manager`` is a module global, so a
second process would hold a second, empty BotManager — which is exactly the
failure students hit before: bots created in the web UI were invisible to the
model, because the model was talking to a different process.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastmcp import FastMCP
from starlette.middleware import Middleware as ASGIMiddleware

from bot_manager import manager
from control_api import register_routes
from event_log import log
from http_logging import HTTPActivityMiddleware
from mcp_logging import ActivityMiddleware
from tools import interaction, lifecycle, movement, pathfinder, prompts, sensors

# Where the MCP endpoint lives. opencode connects to http://<host>:<port>/mcp.
MCP_PATH = "/mcp"


@asynccontextmanager
async def lifespan(_server: FastMCP):
    """Announce startup in the timeline and close bots on shutdown."""
    log.append(source="system", kind="bot", name="service_started")
    try:
        yield
    finally:
        manager.close_all()


def init_server() -> FastMCP:
    """Create the mineai MCP server with all model-facing tools registered."""
    mcp_server = FastMCP(name="mineai", lifespan=lifespan)
    mcp_server.add_middleware(ActivityMiddleware())

    lifecycle.register(mcp_server)
    sensors.register(mcp_server)
    movement.register(mcp_server)
    interaction.register(mcp_server)
    pathfinder.register(mcp_server)
    prompts.register(mcp_server)

    register_routes(mcp_server)
    return mcp_server


def build_app():
    """Return the Starlette app serving /mcp, /api/* and the UI on one port."""
    return init_server().http_app(
        path=MCP_PATH,
        middleware=[ASGIMiddleware(HTTPActivityMiddleware)],
    )

"""Build the FastMCP server and register every tool module."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastmcp import FastMCP

from bot_manager import manager
from control_api import MineAIControlServer
from tools import interaction, lifecycle, movement, pathfinder, sensors


@asynccontextmanager
async def lifespan(_server: FastMCP):
    """Start optional UI control API and clean up bots on shutdown."""
    control: MineAIControlServer | None = None
    if os.environ.get("MINEAI_CONTROL_API", "1") != "0":
        host = os.environ.get("MINEAI_CONTROL_HOST", "127.0.0.1")
        port = int(os.environ.get("MINEAI_CONTROL_PORT", "8765"))
        control = MineAIControlServer(host, port)
        control.start()
    try:
        yield
    finally:
        if control is not None:
            control.stop()
        manager.close_all()


def init_server() -> FastMCP:
    """Create the mineai MCP server and all model-facing tools."""
    mcp_server = FastMCP(name="mineai", lifespan=lifespan)
    lifecycle.register(mcp_server)
    sensors.register(mcp_server)
    movement.register(mcp_server)
    interaction.register(mcp_server)
    pathfinder.register(mcp_server)
    return mcp_server

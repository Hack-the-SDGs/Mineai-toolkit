"""Build the FastMCP server and register every tool module."""

from __future__ import annotations

from fastmcp import FastMCP

from bot_session import lifespan
from tools import interaction, movement, sensors


def init_server() -> FastMCP:
    """Create the mineai MCP server with the bot lifespan and all tools."""
    mcp_server = FastMCP(name="mineai", lifespan=lifespan)
    sensors.register(mcp_server)
    movement.register(mcp_server)
    interaction.register(mcp_server)
    return mcp_server

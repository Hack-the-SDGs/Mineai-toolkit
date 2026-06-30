"""Interaction tools: holding items, digging, placing, using, and chatting."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bot_session import call

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """Register interaction tools on ``mcp``."""

    @mcp.tool
    async def hold(name: str, bot_name: str | None = None) -> str:
        """Equip the item named ``name`` from inventory; True on success."""
        return await call("hold", name, bot_name=bot_name)

    @mcp.tool
    async def dig(bot_name: str | None = None) -> str:
        """Dig the targeted block; returns 'coords, name' or 'none'."""
        return await call("dig", bot_name=bot_name)

    @mcp.tool
    async def place(bot_name: str | None = None) -> str:
        """Place the held block against the targeted face; 'coords, name' or 'none'."""
        return await call("place", bot_name=bot_name)

    @mcp.tool
    async def use(bot_name: str | None = None) -> str:
        """Use/activate the held item; True on success."""
        return await call("use", bot_name=bot_name)

    @mcp.tool
    async def chat(message: str, bot_name: str | None = None) -> str:
        """Send a chat message to the server."""
        await call("chat", message, bot_name=bot_name)
        return "sent"

    @mcp.tool
    async def set_height(level: int, bot_name: str | None = None) -> str:
        """Set bot size level from 1 to 5."""
        await call("set_height", level, bot_name=bot_name)
        return "set"

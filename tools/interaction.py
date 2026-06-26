"""Interaction tools: holding items, digging, placing, using, and chatting."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bot_session import call

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """Register interaction tools on ``mcp``."""

    @mcp.tool
    async def hold(name: str) -> str:
        """Equip the item named ``name`` from inventory; True on success."""
        return await call("hold", name)

    @mcp.tool
    async def dig() -> str:
        """Dig the targeted block; returns 'coords, name' or 'none'."""
        return await call("dig")

    @mcp.tool
    async def place() -> str:
        """Place the held block against the targeted face; 'coords, name' or 'none'."""
        return await call("place")

    @mcp.tool
    async def use() -> str:
        """Use/activate the held item; True on success."""
        return await call("use")

    @mcp.tool
    async def chat(message: str) -> str:
        """Send a chat message to the server."""
        await call("chat", message)
        return "sent"

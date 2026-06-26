"""Read-only sensor tools: where the bot is and what is around it."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bot_session import call

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """Register sensor tools on ``mcp``."""

    @mcp.tool
    async def get_pos() -> str:
        """Current (x, y, z) position of the bot."""
        return await call("get_pos")

    @mcp.tool
    async def get_block(x: int, y: int, z: int) -> str:
        """Name of the block at the given world coordinates, or 'none'."""
        return await call("get_block", x, y, z)

    @mcp.tool
    async def look_block() -> str:
        """The block the bot is currently looking at, as 'coords, name'."""
        return await call("look_block")

    @mcp.tool
    async def find_block(name: str) -> str:
        """Coordinates of the nearest block named ``name`` (e.g. 'oak_log')."""
        return await call("find_block", name)

    @mcp.tool
    async def get_hand() -> str:
        """The item currently held in hand as 'name, count', or 'none'."""
        return await call("get_hand")

"""Read-only sensor tools: where the bot is and what is around it."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bot_session import call

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """Register sensor tools on ``mcp``."""

    @mcp.tool
    async def get_pos(bot_name: str | None = None) -> str:
        """Current (x, y, z) position of the bot."""
        return await call("get_pos", bot_name=bot_name)

    @mcp.tool
    async def get_block(x: int, y: int, z: int, bot_name: str | None = None) -> str:
        """Name of the block at the given world coordinates, or 'none'."""
        return await call("get_block", x, y, z, bot_name=bot_name)

    @mcp.tool
    async def look_block(bot_name: str | None = None) -> str:
        """The block the bot is currently looking at, as 'coords, name'."""
        return await call("look_block", bot_name=bot_name)

    @mcp.tool
    async def find_block(name: str, bot_name: str | None = None) -> str:
        """Coordinates of the nearest block named ``name`` (e.g. 'oak_log')."""
        return await call("find_block", name, bot_name=bot_name)

    @mcp.tool
    async def get_hand(bot_name: str | None = None) -> str:
        """The item currently held in hand as 'name, count', or 'none'."""
        return await call("get_hand", bot_name=bot_name)

    @mcp.tool
    async def get_height(bot_name: str | None = None) -> str:
        """Current bot size level, from 1 to 5."""
        return await call("get_height", bot_name=bot_name)

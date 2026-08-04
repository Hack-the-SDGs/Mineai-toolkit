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
    async def find_blocks(
        name: str,
        max: int = 16,  # noqa: A002 — mirrors minethon's public find_blocks(max=...)
        bot_name: str | None = None,
    ) -> str:
        """Up to ``max`` nearest blocks named ``name``, closest first; 'empty' if none."""
        return await call("find_blocks", name, max, bot_name=bot_name)

    @mcp.tool
    async def get_block_in_front(bot_name: str | None = None) -> str:
        """Name of the solid block one step ahead, or 'none' if nothing solid.

        No coordinates — it is always one step along the facing axis; use
        ``look_block`` when you also need the aimed block's position. Non-solid
        cells (air/water/lava) read as 'none'.
        """
        # minethon names this method get_front_block; the tool keeps the clearer,
        # model-facing name. (Calling the wrong name forwards to the JS bot,
        # returns None, and raises "NoneType is not callable" when invoked.)
        return await call("get_front_block", bot_name=bot_name)

    @mcp.tool
    async def get_block_property(
        x: int,
        y: int,
        z: int,
        property_name: str,
        bot_name: str | None = None,
    ) -> str:
        """A block-state property at the given coords (e.g. 'lit', 'facing', 'powered').

        Returns the property value, or 'none' if the block is unloaded or has no
        such property.
        """
        return await call(
            "get_block_property", x, y, z, property_name, bot_name=bot_name
        )

    @mcp.tool
    async def get_hand(bot_name: str | None = None) -> str:
        """The item currently held in hand as 'name, count', or 'none'."""
        return await call("get_hand", bot_name=bot_name)

    @mcp.tool
    async def get_height(bot_name: str | None = None) -> str:
        """Current bot size level, from 1 to 5."""
        return await call("get_height", bot_name=bot_name)

    @mcp.tool
    async def get_orientation(bot_name: str | None = None) -> str:
        """Current facing as 'yaw, pitch' in degrees (yaw 0 = north/-Z)."""
        yaw = await call("get_yaw", bot_name=bot_name)
        pitch = await call("get_pitch", bot_name=bot_name)
        return f"{yaw}, {pitch}"

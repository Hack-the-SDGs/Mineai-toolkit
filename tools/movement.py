"""Locomotion tools: walking, jumping, and turning."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bot_session import call

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """Register movement tools on ``mcp``."""

    @mcp.tool
    async def move_forward(blocks: float = 1.0, bot_name: str | None = None) -> str:
        """Walk forward ``blocks`` blocks; returns the new position."""
        return await call("move_forward", blocks, bot_name=bot_name)

    @mcp.tool
    async def move_backward(blocks: float = 1.0, bot_name: str | None = None) -> str:
        """Walk backward ``blocks`` blocks; returns the new position."""
        return await call("move_backward", blocks, bot_name=bot_name)

    @mcp.tool
    async def move_left(blocks: float = 1.0, bot_name: str | None = None) -> str:
        """Strafe left ``blocks`` blocks; returns the new position."""
        return await call("move_left", blocks, bot_name=bot_name)

    @mcp.tool
    async def move_right(blocks: float = 1.0, bot_name: str | None = None) -> str:
        """Strafe right ``blocks`` blocks; returns the new position."""
        return await call("move_right", blocks, bot_name=bot_name)

    @mcp.tool
    async def jump(bot_name: str | None = None) -> str:
        """Jump once; returns the new position."""
        return await call("jump", bot_name=bot_name)

    @mcp.tool
    async def turn(degrees: float, bot_name: str | None = None) -> str:
        """Turn by ``degrees`` (relative); returns the new (yaw, pitch)."""
        return await call("turn", degrees, bot_name=bot_name)

    @mcp.tool
    async def look_at(x: int, y: int, z: int, bot_name: str | None = None) -> str:
        """Face the given world coordinates; returns the new (yaw, pitch)."""
        return await call("look_at", x, y, z, bot_name=bot_name)

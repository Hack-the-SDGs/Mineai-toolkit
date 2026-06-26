"""Locomotion tools: walking, jumping, and turning."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bot_session import call

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """Register movement tools on ``mcp``."""

    @mcp.tool
    async def move_forward(blocks: float = 1.0) -> str:
        """Walk forward ``blocks`` blocks; returns the new position."""
        return await call("move_forward", blocks)

    @mcp.tool
    async def move_backward(blocks: float = 1.0) -> str:
        """Walk backward ``blocks`` blocks; returns the new position."""
        return await call("move_backward", blocks)

    @mcp.tool
    async def move_left(blocks: float = 1.0) -> str:
        """Strafe left ``blocks`` blocks; returns the new position."""
        return await call("move_left", blocks)

    @mcp.tool
    async def move_right(blocks: float = 1.0) -> str:
        """Strafe right ``blocks`` blocks; returns the new position."""
        return await call("move_right", blocks)

    @mcp.tool
    async def jump() -> str:
        """Jump once; returns the new position."""
        return await call("jump")

    @mcp.tool
    async def turn(degrees: float) -> str:
        """Turn by ``degrees`` (relative); returns the new (yaw, pitch)."""
        return await call("turn", degrees)

    @mcp.tool
    async def look_at(x: int, y: int, z: int) -> str:
        """Face the given world coordinates; returns the new (yaw, pitch)."""
        return await call("look_at", x, y, z)

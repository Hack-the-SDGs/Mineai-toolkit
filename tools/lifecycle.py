"""Bot lifecycle inspection tools exposed to the model."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bot_session import check_bot_health as health_for
from bot_session import get_active_bot as active_name
from bot_session import list_bot_statuses, set_active_bot as activate

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """Register bot health and selection tools on ``mcp``."""

    @mcp.tool
    async def list_bots() -> list[dict[str, Any]]:
        """List bot names and health snapshots. Use names from here as bot_name."""
        return await list_bot_statuses()

    @mcp.tool
    async def check_bot_health(bot_name: str) -> dict[str, Any]:
        """Check health for one bot name returned by list_bots."""
        return await health_for(bot_name)

    @mcp.tool
    async def get_active_bot() -> str:
        """Return the bot currently used when action tools omit bot_name."""
        return await active_name() or "none"

    @mcp.tool
    async def set_active_bot(bot_name: str) -> dict[str, Any]:
        """Select which existing bot action tools should use by default."""
        return await activate(bot_name)

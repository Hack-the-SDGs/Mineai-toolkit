"""Async adapter around the shared BotManager for FastMCP tools."""

from __future__ import annotations

from typing import Any

from anyio import to_thread

from bot_manager import manager


async def call(method: str, *args: object, bot_name: str | None = None) -> str:
    """Dispatch a Bot method on a worker thread and format the result."""
    return await to_thread.run_sync(
        lambda: manager.call(method, *args, bot_name=bot_name),
    )


async def list_bot_statuses() -> list[dict[str, Any]]:
    """Return health snapshots for every known bot."""
    return await to_thread.run_sync(manager.list_bots)


async def check_bot_health(bot_name: str) -> dict[str, Any]:
    """Return a health snapshot for one named bot."""
    return await to_thread.run_sync(lambda: manager.check_bot_health(bot_name))


async def set_active_bot(bot_name: str) -> dict[str, Any]:
    """Select the bot used by action tools when no bot_name is passed."""
    return await to_thread.run_sync(lambda: manager.set_active_bot(bot_name))


async def get_active_bot() -> str | None:
    """Return the current active bot name."""
    return await to_thread.run_sync(manager.get_active_bot)

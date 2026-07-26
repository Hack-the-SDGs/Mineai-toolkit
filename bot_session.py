"""Async adapter around the shared BotManager for FastMCP tools."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

import anyio
from anyio import get_cancelled_exc_class, to_thread

from bot_manager import manager

# MCP-layer command timeout. The work runs on a worker thread inside a
# JSPyBridge call with no reliable cancel, so on expiry we abandon the thread
# and clear any pathfinder goal instead of blocking the model forever. Kept
# generous because legitimate actions (a walk across terrain) take a while;
# override with MINEAI_TOOL_TIMEOUT (seconds).
TOOL_TIMEOUT_SECONDS = float(os.environ.get("MINEAI_TOOL_TIMEOUT", "180"))


async def _clear_goal_shielded(bot_name: str | None) -> None:
    """Stop the bot's pathfinder, surviving a cancel that is already unwinding."""
    with anyio.CancelScope(shield=True):
        await to_thread.run_sync(lambda: manager.clear_pathfinder_goal(bot_name))


async def run_with_timeout(
    fn: Callable[[], Any],
    *,
    bot_name: str | None,
    timeout: float | None = None,
    on_timeout: str = "command",
) -> Any:
    """Run ``fn`` on a worker thread, stopping the bot if it doesn't finish.

    Two ways the work gets cut short, both of which must leave the bot stopped:

    * our own ``move_on_after`` timer fires — we return a timeout message; or
    * the MCP client / HTTP transport cancels the request first (its timeout is
      often shorter than ours) — we clear the goal, then re-raise the cancel.

    The second case is the one that used to leave a bot walking forever: the
    cleanup only ran for our own timer. Normal exceptions from ``fn`` propagate
    untouched and do *not* clear a background goal.
    """
    limit = TOOL_TIMEOUT_SECONDS if timeout is None else timeout
    result: Any = None
    try:
        with anyio.move_on_after(limit) as scope:
            result = await to_thread.run_sync(fn, abandon_on_cancel=True)
    except get_cancelled_exc_class():
        # move_on_after swallows *its own* expiry, so reaching here means an
        # outside cancellation. Stop the bot, then let the cancel propagate.
        await _clear_goal_shielded(bot_name)
        raise
    if scope.cancelled_caught:
        await _clear_goal_shielded(bot_name)
        return (
            f"timeout after {limit:.0f}s: {on_timeout} did not finish; "
            "pathfinder goal cleared"
        )
    return result


async def call(method: str, *args: object, bot_name: str | None = None) -> str:
    """Dispatch a Bot method on a worker thread and format the result."""
    return await run_with_timeout(
        lambda: manager.call(method, *args, bot_name=bot_name),
        bot_name=bot_name,
        on_timeout=method,
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

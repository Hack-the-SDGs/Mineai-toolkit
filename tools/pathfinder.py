"""Pathfinder tools for larger navigation tasks."""

from __future__ import annotations

import os
import time
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from anyio import to_thread

from bot_manager import manager
from bot_session import run_with_timeout

if TYPE_CHECKING:
    from fastmcp import FastMCP

# How long a goto waits before giving up and stopping the bot. Longer than the
# general command timeout because a real navigation across terrain legitimately
# takes a while; override with MINEAI_PATHFINDER_TIMEOUT (seconds).
PATHFINDER_TIMEOUT = float(os.environ.get("MINEAI_PATHFINDER_TIMEOUT", "300"))

# How often the goto loop polls the pathfinder for arrival, in seconds.
_POLL_INTERVAL = 0.25

# run_with_timeout's own ceiling sits a little above PATHFINDER_TIMEOUT so the
# in-thread deadline in _goto (which can stop the bot on the same thread) is the
# normal path; the outer timeout is only a backstop for a wedged bridge read.
_BACKSTOP_MARGIN_SECONDS = 15.0


def register(mcp: FastMCP) -> None:
    """Register pathfinder tools on ``mcp``."""

    @mcp.tool
    async def load_pathfinder(bot_name: str | None = None) -> str:
        """Ensure mineflayer-pathfinder is loaded on the selected bot."""
        return await to_thread.run_sync(lambda: manager.load_pathfinder(bot_name))

    @mcp.tool
    async def pathfinder_status(bot_name: str | None = None) -> dict[str, Any]:
        """Return pathfinder movement/mining/building status."""
        return await to_thread.run_sync(lambda: _status(bot_name))

    @mcp.tool
    async def pathfinder_stop(bot_name: str | None = None) -> str:
        """Cancel the current pathfinder task and stop moving."""
        return await to_thread.run_sync(lambda: _stop(bot_name))

    @mcp.tool
    async def pathfinder_clear_goal(bot_name: str | None = None) -> str:
        """Clear the current pathfinder goal."""
        return await to_thread.run_sync(lambda: _clear_goal(bot_name))

    @mcp.tool
    async def pathfinder_goto_near(
        x: float,
        y: float,
        z: float,
        radius: float = 1.0,
        bot_name: str | None = None,
    ) -> str:
        """Block until the bot reaches within ``radius`` of ``(x, y, z)``."""
        return await _run_goto(
            lambda: _goto(_goal_near(bot_name, x, y, z, radius), bot_name),
            bot_name,
        )

    @mcp.tool
    async def pathfinder_goto_block(
        x: float,
        y: float,
        z: float,
        bot_name: str | None = None,
    ) -> str:
        """Block until the bot reaches exactly the target block."""
        return await _run_goto(
            lambda: _goto(_goal_block(bot_name, x, y, z), bot_name),
            bot_name,
        )

    @mcp.tool
    async def pathfinder_goto_get_to_block(
        x: float,
        y: float,
        z: float,
        bot_name: str | None = None,
    ) -> str:
        """Block until the bot reaches beside the target block."""
        return await _run_goto(
            lambda: _goto(_goal_get_to_block(bot_name, x, y, z), bot_name),
            bot_name,
        )

    @mcp.tool
    async def pathfinder_goto_xz(
        x: float,
        z: float,
        bot_name: str | None = None,
    ) -> str:
        """Block until the bot reaches the target X/Z column; Y is unrestricted."""
        return await _run_goto(lambda: _goto(_goal_xz(bot_name, x, z), bot_name), bot_name)

    @mcp.tool
    async def pathfinder_goto_near_xz(
        x: float,
        z: float,
        radius: float = 1.0,
        bot_name: str | None = None,
    ) -> str:
        """Block until the bot reaches within ``radius`` on the X/Z plane."""
        return await _run_goto(
            lambda: _goto(_goal_near_xz(bot_name, x, z, radius), bot_name),
            bot_name,
        )

    @mcp.tool
    async def pathfinder_goto_y(y: float, bot_name: str | None = None) -> str:
        """Block until the bot reaches the target Y height."""
        return await _run_goto(lambda: _goto(_goal_y(bot_name, y), bot_name), bot_name)

    @mcp.tool
    async def pathfinder_set_goal_near(
        x: float,
        y: float,
        z: float,
        radius: float = 1.0,
        dynamic: bool = False,
        bot_name: str | None = None,
    ) -> str:
        """Set a background pathfinder goal near ``(x, y, z)``."""
        return await to_thread.run_sync(
            lambda: _set_goal(_goal_near(bot_name, x, y, z, radius), dynamic, bot_name),
        )

    @mcp.tool
    async def pathfinder_set_goal_block(
        x: float,
        y: float,
        z: float,
        dynamic: bool = False,
        bot_name: str | None = None,
    ) -> str:
        """Set a background pathfinder goal for an exact block."""
        return await to_thread.run_sync(
            lambda: _set_goal(_goal_block(bot_name, x, y, z), dynamic, bot_name),
        )


def _status(bot_name: str | None) -> dict[str, Any]:
    manager.load_pathfinder(bot_name)
    bot = manager.resolve_bot(bot_name)
    pathfinder = bot.pathfinder
    return {
        "moving": bool(pathfinder.isMoving()),
        "mining": bool(pathfinder.isMining()),
        "building": bool(pathfinder.isBuilding()),
        "goal": str(pathfinder.goal) if pathfinder.goal is not None else None,
    }


def _stop(bot_name: str | None) -> str:
    manager.load_pathfinder(bot_name)
    manager.resolve_bot(bot_name).pathfinder.stop()
    return "stopped"


def _clear_goal(bot_name: str | None) -> str:
    manager.load_pathfinder(bot_name)
    manager.resolve_bot(bot_name).pathfinder.setGoal(None)
    return "cleared"


async def _run_goto(fn: Any, bot_name: str | None) -> str:
    """Run a goto under the outer backstop timeout + goal cleanup."""
    return await run_with_timeout(
        fn,
        bot_name=bot_name,
        timeout=PATHFINDER_TIMEOUT + _BACKSTOP_MARGIN_SECONDS,
        on_timeout="pathfinder goto",
    )


def _pathing(pathfinder: Any) -> bool:
    """Whether the pathfinder still has a goal to pursue.

    On arrival mineflayer-pathfinder nulls its goal and stops moving (index.js
    goal_reached: ``stateGoal = null; fullStop()``), so this drops to False.
    Right after setGoal — goal set but no path computed yet — the goal check
    keeps it True, so the loop never exits before the first tick.
    """
    if pathfinder.goal is not None:
        return True
    return bool(pathfinder.isMoving())


def _goto(goal: object, bot_name: str | None) -> str:
    """Drive to ``goal`` and block until arrival or the pathfinder timeout.

    Uses non-blocking setGoal + a Python poll loop rather than the blocking
    goto() Promise, so the worker thread never sits inside a bridge call: the
    deadline below can stop the bot on this same thread, and if the request is
    cancelled from outside, clearing the goal from another thread isn't queued
    behind a pending goto. Both are why a timed-out goto used to keep walking.
    """
    bot = manager.resolve_bot(bot_name)
    pathfinder = bot.pathfinder
    pathfinder.setGoal(goal)
    deadline = time.monotonic() + PATHFINDER_TIMEOUT
    while _pathing(pathfinder):
        if time.monotonic() >= deadline:
            pathfinder.setGoal(None)
            return (
                f"timeout after {PATHFINDER_TIMEOUT:.0f}s: goal not reached; "
                "bot stopped"
            )
        time.sleep(_POLL_INTERVAL)
    return _fmt(bot.get_pos())


def _set_goal(goal: object, dynamic: bool, bot_name: str | None) -> str:
    manager.resolve_bot(bot_name).pathfinder.setGoal(goal, dynamic)
    return "set"


def _goal_near(
    bot_name: str | None,
    x: float,
    y: float,
    z: float,
    radius: float,
) -> object:
    goals = manager.pathfinder_module(bot_name).goals
    return goals.GoalNear(x, y, z, radius)


def _goal_block(bot_name: str | None, x: float, y: float, z: float) -> object:
    goals = manager.pathfinder_module(bot_name).goals
    return goals.GoalBlock(x, y, z)


def _goal_get_to_block(bot_name: str | None, x: float, y: float, z: float) -> object:
    goals = manager.pathfinder_module(bot_name).goals
    return goals.GoalGetToBlock(x, y, z)


def _goal_xz(bot_name: str | None, x: float, z: float) -> object:
    goals = manager.pathfinder_module(bot_name).goals
    return goals.GoalXZ(x, z)


def _goal_near_xz(
    bot_name: str | None,
    x: float,
    z: float,
    radius: float,
) -> object:
    goals = manager.pathfinder_module(bot_name).goals
    return goals.GoalNearXZ(x, z, radius)


def _goal_y(bot_name: str | None, y: float) -> object:
    goals = manager.pathfinder_module(bot_name).goals
    return goals.GoalY(y)


def _fmt(value: object) -> str:
    if value is None:
        return "none"
    if isinstance(value, tuple):
        return ", ".join(_fmt(v) for v in value)
    if isinstance(value, Iterable) and not isinstance(value, str):
        return "; ".join(_fmt(v) for v in value) or "empty"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)

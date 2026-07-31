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
        """Block until the bot reaches within ``radius`` of ``(x, y, z)``.

        This is the **travel** goto: use it to *get somewhere*, not to line up on
        a block you will act on. A radius goal is satisfied by any cell within
        range, so it does not guarantee the bot ends up on or facing ``(x, y,
        z)`` — for dig/use/place, use ``pathfinder_goto_look_at_block`` instead.
        """
        return await _run_goto(
            lambda: _goto(_goal_near(bot_name, x, y, z, radius), bot_name),
            bot_name,
        )

    @mcp.tool
    async def pathfinder_goto_look_at_block(
        x: float,
        y: float,
        z: float,
        bot_name: str | None = None,
    ) -> str:
        """Block until the bot is in reach of AND facing the target block.

        Prefer this over ``pathfinder_goto_near`` when you intend to act on a
        specific block (dig/use/place). ``goto_near(radius)`` is satisfied by any
        cell within ``radius`` — for a 3x3 with the target at the centre a corner
        cell counts, so the bot stops in the corner, not aimed at the block, and
        still reports "arrived". This goal instead ends with the bot positioned
        within reach and already looking at the block face, so the follow-up
        dig/use/place has a valid aim. Still verify with ``get_block_in_front``.
        """
        return await _run_goto(
            lambda: _goto(_goal_look_at_block(bot_name, x, y, z), bot_name),
            bot_name,
        )

    @mcp.tool
    async def pathfinder_check_path(
        x: float,
        y: float,
        z: float,
        goal_type: str = "near",
        radius: float = 1.0,
        timeout_ms: float = 5000.0,
        include_path: bool = True,
        bot_name: str | None = None,
    ) -> dict[str, Any]:
        """Plan (but do NOT walk) a route to a target and report reachability.

        Runs the same A* the bot navigates with (``canDig=False``), so a fence
        or wall between the bot and the target counts as a real obstacle. Use
        this before a goto to confirm a spot is actually reachable instead of
        merely close in x/y/z — e.g. a one-block ledge walled off by fences: the
        coordinates match but no path exists, and a blind goto would stall
        trying to reach a block it can't.

        ``goal_type`` mirrors the two goto tools: ``near`` (travel — within
        ``radius`` of the point, pairs with ``pathfinder_goto_near``) or
        ``look_at_block`` (in reach of and facing the block, pairs with
        ``pathfinder_goto_look_at_block``). Check the *same* goal you will
        execute so the answer matches what the goto will do.

        Returns ``reachable`` plus the raw pathfinder ``status``
        (``success`` = full path found, ``partial``/``timeout``/``noPath`` = it
        could not fully reach), the path length, cost, and the ``end`` position
        the planned path stops at — for a ``partial`` result that ``end`` is how
        far it gets before the obstacle blocks it. ``path`` holds the full list
        of ``[x, y, z]`` waypoints the bot would walk; set ``include_path=False``
        to omit it and keep the reply small.
        """
        return await to_thread.run_sync(
            lambda: _check_path(
                bot_name, x, y, z, goal_type, radius, timeout_ms, include_path
            ),
        )

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


def _goal_for(
    bot_name: str | None,
    goal_type: str,
    x: float,
    y: float,
    z: float,
    radius: float,
) -> object:
    """Build the goal a check/goto should use for the named ``goal_type``."""
    if goal_type == "near":
        return _goal_near(bot_name, x, y, z, radius)
    if goal_type == "look_at_block":
        return _goal_look_at_block(bot_name, x, y, z)
    raise ValueError(
        f"unknown goal_type {goal_type!r}; use near or look_at_block"
    )


def _check_path(
    bot_name: str | None,
    x: float,
    y: float,
    z: float,
    goal_type: str,
    radius: float,
    timeout_ms: float,
    include_path: bool,
) -> dict[str, Any]:
    """Plan a route with the bot's no-dig movements and summarise reachability.

    ``getPathTo`` runs A* to completion (or ``timeout_ms``) without moving the
    bot and returns a Result whose ``status`` is ``success`` only when a full
    path was found; ``partial`` means it got as close as it could but the goal
    is blocked off (the fence-separated-block case), ``noPath`` means nothing,
    ``timeout`` means it ran out of thinking time.
    """
    bot = manager.resolve_bot(bot_name)
    movements = manager.pathfinder_movements(bot_name)
    goal = _goal_for(bot_name, goal_type, x, y, z, radius)
    result = bot.pathfinder.getPathTo(movements, goal, timeout_ms)
    status = str(result.status)
    nodes = [_node_xyz(result.path[i]) for i in range(int(result.path.length))]
    cost = getattr(result, "cost", None)
    summary: dict[str, Any] = {
        "reachable": status == "success",
        "status": status,
        "goal_type": goal_type,
        "path_length": len(nodes),
        "cost": round(float(cost), 2) if cost is not None else None,
        "end": nodes[-1] if nodes else None,
    }
    if include_path:
        summary["path"] = nodes
    return summary


def _node_xyz(node: Any) -> list[float]:
    """Extract a Move node's block position as rounded ``[x, y, z]``."""
    return [round(float(node.x), 2), round(float(node.y), 2), round(float(node.z), 2)]


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


def _goal_look_at_block(bot_name: str | None, x: float, y: float, z: float) -> object:
    """Goal that ends with the bot in reach of and looking at ``(x, y, z)``.

    ``GoalLookAtBlock(pos, world, options)`` needs the bot's world for its
    line-of-sight/reach checks. The constructor only reads ``pos.x/.y/.z`` (it
    copies them into its own Vec3), so a plain dict is enough across the bridge.
    Options are left at the library defaults (reach 4.5, entityHeight 1.6).
    """
    bot = manager.resolve_bot(bot_name)
    goals = manager.pathfinder_module(bot_name).goals
    return goals.GoalLookAtBlock({"x": x, "y": y, "z": z}, bot.world)


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

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
    async def pathfinder_goto(
        x: float,
        y: float,
        z: float,
        bot_name: str | None = None,
    ) -> dict[str, Any] | str:
        """Reach ``(x, y, z)`` by following the real route — never a radius.

        The single goto. It plans the actual A* route to the target, then drives
        with an **exact** goal to the last node of that route, so the bot always
        stops on a cell the planner proved reachable — no "within radius" cell on
        the wrong side of a fence, no corner stop.

        Two outcomes depending on the target cell:

        * **Empty cell** (air) → stands **on** it (``mode: "on"``). Use for
          travelling to a spot.
        * **Occupied cell** (a block to dig/use/place) → stands **beside** it via
          the route and turns to face it (``mode: "beside"``, ``facing_target``),
          so the follow-up dig/use/place already has aim. Still confirm with
          ``get_block_in_front`` before acting.

        If no route reaches the target the bot does **not** move: returns
        ``arrived: False`` with ``stalled_at`` (how far a route would get). Treat
        that as "unreachable — pick another target", not "retry". Run
        ``pathfinder_check_path`` first if you want to test without moving.
        """
        return await _run_goto(lambda: _goto_reach(bot_name, x, y, z), bot_name)

    @mcp.tool
    async def pathfinder_check_path(
        x: float,
        y: float,
        z: float,
        timeout_ms: float = 5000.0,
        include_path: bool = True,
        bot_name: str | None = None,
    ) -> dict[str, Any]:
        """Plan (but do NOT walk) the route to ``(x, y, z)`` and report reach.

        Mirrors ``pathfinder_goto`` exactly — same on/beside decision, same
        no-dig A* — but never moves the bot. Runs with ``canDig=False``, so a
        fence or wall between the bot and the target counts as a real obstacle.
        Use it before a goto to confirm a spot is reachable instead of merely
        close in x/y/z — e.g. a one-block ledge walled off by fences: the
        coordinates match but no route exists, and a blind goto would stall.

        Returns ``reachable`` plus ``mode`` (``on`` for an empty target cell,
        ``beside`` for an occupied one — matching what ``pathfinder_goto`` would
        do), the raw pathfinder ``status`` (``success`` = full route found,
        ``partial``/``timeout``/``noPath`` = it could not fully reach), the path
        length, cost, and ``end`` — the cell the route stops at, i.e. where the
        bot would stand (for a ``partial`` result, how far it gets before the
        obstacle). ``path`` holds the full ``[x, y, z]`` waypoint list; set
        ``include_path=False`` to omit it and keep the reply small.
        """
        return await to_thread.run_sync(
            lambda: _check_path(bot_name, x, y, z, timeout_ms, include_path),
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


async def _run_goto(fn: Any, bot_name: str | None) -> Any:
    """Run a goto under the outer backstop timeout + goal cleanup.

    Returns whatever ``fn`` returns (a result dict for the reach goto), or a
    timeout string if the outer backstop fires.
    """
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


# get_block names that mean an empty cell the bot can stand *in*; anything else
# is an occupied block to approach from beside rather than stand inside.
_EMPTY_BLOCKS = {None, "", "air", "cave_air", "void_air"}

# Planning budget (ms) for the goto's own reachability plan before it drives.
_PLAN_TIMEOUT_MS = 5000.0


def _is_empty(name: object) -> bool:
    """Whether a ``get_block`` name means an empty, standable-in cell.

    Normalises so it works whether the name carries a ``minecraft:`` namespace
    or not (``"minecraft:air"`` and ``"air"`` both count as empty).
    """
    if name is None:
        return True
    short = str(name).split(":")[-1].lower()
    return short in _EMPTY_BLOCKS


def _plan_reach(
    bot: Any,
    bot_name: str | None,
    x: float,
    y: float,
    z: float,
    timeout_ms: float,
) -> dict[str, Any]:
    """Plan the real route to ``(x, y, z)`` without moving; classify on/beside.

    An empty target cell means "stand on it" (``GoalBlock``); an occupied one
    means "stand beside it" (``GoalGetToBlock``). Choosing by occupancy avoids
    A* burning the whole ``timeout_ms`` trying to stand inside a solid block.
    The route's last node is the cell the bot would actually stand on — proven
    reachable — which is what the goto then drives to with an exact goal.
    """
    goals = manager.pathfinder_module(bot_name).goals
    movements = manager.pathfinder_movements(bot_name)
    mode = "on" if _is_empty(bot.get_block(int(x), int(y), int(z))) else "beside"
    goal = (
        goals.GoalBlock(int(x), int(y), int(z))
        if mode == "on"
        else goals.GoalGetToBlock(int(x), int(y), int(z))
    )
    result = bot.pathfinder.getPathTo(movements, goal, timeout_ms)
    nodes = [_node_xyz(result.path[i]) for i in range(int(result.path.length))]
    cost = getattr(result, "cost", None)
    return {
        "mode": mode,
        "status": str(result.status),
        "nodes": nodes,
        "cost": round(float(cost), 2) if cost is not None else None,
    }


def _check_path(
    bot_name: str | None,
    x: float,
    y: float,
    z: float,
    timeout_ms: float,
    include_path: bool,
) -> dict[str, Any]:
    """Plan-only reachability that mirrors what ``pathfinder_goto`` would do.

    ``getPathTo`` runs A* to completion (or ``timeout_ms``) without moving the
    bot: ``status`` is ``success`` only when a full route was found; ``partial``
    means it got as close as it could but the target is blocked off (the
    fence-separated case), ``noPath`` nothing, ``timeout`` ran out of thinking.
    """
    bot = manager.resolve_bot(bot_name)
    plan = _plan_reach(bot, bot_name, x, y, z, timeout_ms)
    nodes = plan["nodes"]
    summary: dict[str, Any] = {
        "reachable": plan["status"] == "success",
        "status": plan["status"],
        "mode": plan["mode"],
        "path_length": len(nodes),
        "cost": plan["cost"],
        "end": nodes[-1] if nodes else None,
    }
    if include_path:
        summary["path"] = nodes
    return summary


def _goto_reach(bot_name: str | None, x: float, y: float, z: float) -> dict[str, Any]:
    """Drive to ``(x, y, z)`` along its real route, then face it when beside.

    Plans the route, drives with an exact ``GoalBlock`` to the route's terminal
    node (proven reachable — no radius, no wrong-side-of-a-fence cell), and for
    an occupied target approached from beside, turns to look at it so the caller
    can immediately dig/use/place. Never moves when there is no route: reports
    where a route would stall so the caller switches target instead of retrying.
    """
    bot = manager.resolve_bot(bot_name)
    plan = _plan_reach(bot, bot_name, x, y, z, _PLAN_TIMEOUT_MS)
    nodes = plan["nodes"]
    if plan["status"] != "success" or not nodes:
        return {
            "arrived": False,
            "status": plan["status"],
            "mode": plan["mode"],
            "reason": "no route onto or beside the target (walled off?)",
            "stalled_at": nodes[-1] if nodes else None,
        }
    stand = nodes[-1]
    goals = manager.pathfinder_module(bot_name).goals
    drive = _goto(goals.GoalBlock(int(stand[0]), int(stand[1]), int(stand[2])), bot_name)
    if isinstance(drive, str) and drive.startswith("timeout"):
        return {
            "arrived": False,
            "status": "timeout",
            "mode": plan["mode"],
            "reason": drive,
        }
    result: dict[str, Any] = {
        "arrived": True,
        "status": "success",
        "mode": plan["mode"],
        "stood_at": stand,
        "pos": _fmt(bot.get_pos()),
    }
    if plan["mode"] == "beside":
        bot.look_at(int(x), int(y), int(z))
        looked = bot.look_block()
        result["facing_target"] = _is_target(looked, x, y, z)
        result["aimed_block"] = _fmt(looked) if looked is not None else None
    return result


def _is_target(looked: Any, x: float, y: float, z: float) -> bool:
    """Whether ``look_block()``'s ``((x, y, z), name)`` result is the target."""
    if not looked:
        return False
    coords = looked[0]
    return (
        int(coords[0]) == int(x)
        and int(coords[1]) == int(y)
        and int(coords[2]) == int(z)
    )


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

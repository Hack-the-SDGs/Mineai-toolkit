"""Pathfinder tools for larger navigation tasks.

Navigation uses ``mineflayer-pathfinder``: ``getPathTo`` plans the route (no
movement), and every plan — success or failure — is logged with its full path
array, status and search stats, so a failed goto can be diagnosed from the log
instead of guessed at.
"""

from __future__ import annotations

import math
import os
import time
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from anyio import to_thread

from bot_manager import manager
from bot_session import run_with_timeout
from logging_setup import get_logger

if TYPE_CHECKING:
    from fastmcp import FastMCP

# How long a goto waits before giving up and stopping the bot. Longer than the
# general command timeout because a real navigation across terrain legitimately
# takes a while; override with MINEAI_PATHFINDER_TIMEOUT (seconds).
PATHFINDER_TIMEOUT = float(os.environ.get("MINEAI_PATHFINDER_TIMEOUT", "300"))

# How often the goto loop polls the pathfinder for arrival, in seconds.
_POLL_INTERVAL = 0.25

# If the bot's block cell hasn't changed for this long while a goal is still
# set, the pathfinder has stopped short — it only nulls its goal on exact
# arrival, so a goal it can't fully satisfy (a fence between, a blocked final
# step) otherwise leaves us polling until the full timeout. Long enough not to
# trip during the first path computation after setGoal, or while walking (a
# block is crossed well under a second). Override with
# MINEAI_PATHFINDER_STALL_SECONDS.
_STALL_SECONDS = float(os.environ.get("MINEAI_PATHFINDER_STALL_SECONDS", "2.0"))

# run_with_timeout's own ceiling sits a little above PATHFINDER_TIMEOUT so the
# in-thread deadline in _goto (which can stop the bot on the same thread) is the
# normal path; the outer timeout is only a backstop for a wedged bridge read.
_BACKSTOP_MARGIN_SECONDS = 15.0

# How long getPathTo may think when planning (ms), before it returns whatever it
# has (status 'timeout'). Override with MINEAI_PATHFINDER_PLAN_MS.
_PLAN_TIMEOUT_MS = float(os.environ.get("MINEAI_PATHFINDER_PLAN_MS", "5000"))

# get_block names that mean an empty cell the bot can stand *in*; anything else
# is an occupied block to approach from beside rather than stand inside.
_EMPTY_BLOCKS = {"", "air", "cave_air", "void_air"}

# Logs the planned route to stderr (and the file when MINEAI_LOG_FILE is set),
# so the path is visible outside the browser timeline. get_logger — not
# logging.getLogger — so the handlers are actually attached.
_log = get_logger("pathfinder")


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
        """Walk to ``(x, y, z)`` via mineflayer-pathfinder; logs the planned path.

        Plans the route with ``getPathTo`` (no digging), **logs the full path
        array + status** so a failure is diagnosable, then drives to the route's
        last node with an exact goal. Two outcomes by target cell, in ``mode``:

        * **Empty cell** (``on``) → stands on it. For travel.
        * **Occupied cell** (``beside`` — a block to dig/use/place) → stands
          beside it and faces it (``facing_target``), ready to act.

        No route → the bot does **not** move: ``arrived: False`` with ``status``
        (``partial``/``noPath``/``timeout``) and ``stalled_at``. That means
        "unreachable, switch target", not "retry". Run ``pathfinder_check_path``
        to inspect the plan without moving.
        """
        return await _run_goto(lambda: _goto_reach(bot_name, x, y, z), bot_name)

    @mcp.tool
    async def pathfinder_check_path(
        x: float,
        y: float,
        z: float,
        include_path: bool = True,
        bot_name: str | None = None,
    ) -> dict[str, Any]:
        """Plan (but do NOT walk) the route to ``(x, y, z)`` and log it.

        Mirrors ``pathfinder_goto``'s planning exactly — same on/beside decision,
        same no-dig ``getPathTo`` — but never moves the bot, and logs the result.
        Use it to see *why* a goto would fail: ``status`` distinguishes a wall
        (``noPath``), a partly-blocked route (``partial``, with ``end`` showing
        how far it gets) and a search that ran out of budget (``timeout``).

        Returns ``reachable``, ``mode``, ``status``, ``path_length``, ``cost``,
        ``end`` (where the route stops), and — unless ``include_path=False`` —
        the full ``path`` array of ``[x, y, z]`` nodes.
        """
        return await to_thread.run_sync(
            lambda: _check_path(bot_name, x, y, z, include_path),
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
    """Drive to ``goal`` and block until arrival, a stall, or the timeout.

    Uses non-blocking setGoal + a Python poll loop rather than the blocking
    goto() Promise, so the worker thread never sits inside a bridge call: the
    deadline below can stop the bot on this same thread, and if the request is
    cancelled from outside, clearing the goal from another thread isn't queued
    behind a pending goto. Both are why a timed-out goto used to keep walking.

    Exits three ways: the pathfinder nulls its goal on exact arrival (loop
    condition drops), our hard deadline fires, or — the important one — the
    bot's block cell stops changing while a goal is still set. That last case is
    a pathfinder that got as close as it can but can't satisfy the goal (a fence
    between, a blocked final step); it stops moving yet never nulls the goal, so
    without this we would poll uselessly until the full timeout.
    """
    bot = manager.resolve_bot(bot_name)
    pathfinder = bot.pathfinder
    pathfinder.setGoal(goal)
    deadline = time.monotonic() + PATHFINDER_TIMEOUT
    last_sig = _progress_sig(bot)
    still_since = time.monotonic()
    while _pathing(pathfinder):
        now = time.monotonic()
        if now >= deadline:
            pathfinder.setGoal(None)
            return (
                f"timeout after {PATHFINDER_TIMEOUT:.0f}s: goal not reached; "
                "bot stopped"
            )
        sig = _progress_sig(bot)
        if sig != last_sig:
            last_sig, still_since = sig, now
        elif now - still_since > _STALL_SECONDS:
            pathfinder.setGoal(None)
            return f"stopped near {_fmt(bot.get_pos())}: pathfinder could not reach the goal"
        time.sleep(_POLL_INTERVAL)
    return _fmt(bot.get_pos())


def _cell(pos: Any) -> tuple[int, int, int]:
    """Floored block cell of a ``(x, y, z)`` position."""
    return (math.floor(pos[0]), math.floor(pos[1]), math.floor(pos[2]))


def _progress_sig(bot: Any) -> tuple[int, int, int, int]:
    """A signature that changes while the bot walks **or** turns.

    Block cell plus a coarse yaw bucket, so rotating in place — turning at a
    corner, or a grid server's discrete server-authoritative turn — counts as
    progress and does not trip the stall check. Only a bot that is neither
    crossing cells nor turning is treated as stopped short. Yaw is bucketed to
    ~5 degrees so sub-degree jitter while genuinely stuck still reads as still.
    """
    pos = bot.get_pos()
    yaw_bucket = round(float(bot.get_yaw()) / 5.0)
    return (math.floor(pos[0]), math.floor(pos[1]), math.floor(pos[2]), yaw_bucket)


def _is_empty(name: object) -> bool:
    """Whether a ``get_block`` name means an empty, standable-in cell.

    Normalises so it works whether the name carries a ``minecraft:`` namespace
    or not (``"minecraft:air"`` and ``"air"`` both count as empty).
    """
    if name is None:
        return True
    return str(name).split(":")[-1].lower() in _EMPTY_BLOCKS


def _plan_reach(
    bot: Any,
    bot_name: str | None,
    x: float,
    y: float,
    z: float,
) -> dict[str, Any]:
    """Plan the route to ``(x, y, z)`` with getPathTo (no movement), and log it.

    An empty target cell means "stand on it" (``GoalBlock``); an occupied one
    means "stand beside it" (``GoalGetToBlock``). Choosing by occupancy avoids
    A* burning the whole budget trying to stand inside a solid block. The route
    is logged in full — status, cost, search counts and the node array — so a
    failure (``partial``/``noPath``/``timeout``) is visible in the log.
    """
    goals = manager.pathfinder_module(bot_name).goals
    movements = manager.pathfinder_movements(bot_name)
    mode = "on" if _is_empty(bot.get_block(int(x), int(y), int(z))) else "beside"
    goal = (
        goals.GoalBlock(int(x), int(y), int(z))
        if mode == "on"
        else goals.GoalGetToBlock(int(x), int(y), int(z))
    )
    result = bot.pathfinder.getPathTo(movements, goal, _PLAN_TIMEOUT_MS)
    status = str(result.status)
    nodes = [_node_xyz(result.path[i]) for i in range(int(result.path.length))]
    plan = {
        "mode": mode,
        "status": status,
        "nodes": nodes,
        "cost": _round(getattr(result, "cost", None)),
        "visited": _int_or_none(getattr(result, "visitedNodes", None)),
        "generated": _int_or_none(getattr(result, "generatedNodes", None)),
    }
    _log_plan(x, y, z, plan)
    return plan


def _log_plan(x: float, y: float, z: float, plan: dict[str, Any]) -> None:
    """Log a getPathTo plan: full path array plus the stats that explain failure."""
    nodes = plan["nodes"]
    fields = (
        int(x),
        int(y),
        int(z),
        plan["mode"],
        plan["status"],
        len(nodes),
        plan["cost"],
        nodes[-1] if nodes else None,
        plan["visited"],
        plan["generated"],
        nodes,
    )
    line = (
        "plan -> (%s,%s,%s) mode=%s status=%s len=%s cost=%s end=%s "
        "visited=%s generated=%s path=%s"
    )
    if plan["status"] == "success":
        _log.info(line, *fields)
    else:
        _log.warning(line + "  <- did NOT fully reach target", *fields)


def _check_path(
    bot_name: str | None,
    x: float,
    y: float,
    z: float,
    include_path: bool,
) -> dict[str, Any]:
    """Plan-only reachability that mirrors what ``pathfinder_goto`` would do."""
    bot = manager.resolve_bot(bot_name)
    plan = _plan_reach(bot, bot_name, x, y, z)
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
    """Drive to ``(x, y, z)`` along its planned route, finishing the last step.

    Plans (and logs) the route, drives with an exact ``GoalBlock`` to the
    route's terminal node, then — for a stand-on target the planner stopped
    short of — tries one manual step onto it. mineflayer-pathfinder refuses some
    diagonal squeezes (past a fence corner, over a half-slab) that the bot can
    physically walk; that manual step recovers them. For an occupied target it
    faces the block so the caller can dig/use/place. Never moves when there is no
    route at all.
    """
    bot = manager.resolve_bot(bot_name)
    plan = _plan_reach(bot, bot_name, x, y, z)
    nodes = plan["nodes"]
    tx, ty, tz = int(x), int(y), int(z)
    mode = plan["mode"]
    if not nodes:
        _log.warning(
            "goto -> (%s,%s,%s) NOT started: status=%s (no route from here)",
            tx,
            ty,
            tz,
            plan["status"],
        )
        return {
            "arrived": False,
            "status": plan["status"],
            "mode": mode,
            "reason": "no route from current position",
            "stalled_at": None,
        }

    # Drive to the closest reachable node — the target itself on success, or the
    # nearest the planner could reach on a partial plan (so the manual last step
    # below starts from right beside the target).
    stand = nodes[-1]
    goals = manager.pathfinder_module(bot_name).goals
    drive = _goto(
        goals.GoalBlock(int(stand[0]), int(stand[1]), int(stand[2])), bot_name
    )
    if isinstance(drive, str) and drive.startswith(("timeout", "stopped near")):
        _log.warning("goto -> (%s,%s,%s) %s", tx, ty, tz, drive)
        return {
            "arrived": False,
            "status": "timeout" if drive.startswith("timeout") else "stopped_short",
            "mode": mode,
            "reason": drive,
        }

    if mode == "beside":
        bot.look_at(tx, ty, tz)
        looked = bot.look_block()
        facing = _is_target(looked, x, y, z)
        if not facing and plan["status"] != "success":
            _log.warning(
                "goto -> (%s,%s,%s) beside NOT reached (status=%s)",
                tx,
                ty,
                tz,
                plan["status"],
            )
            return {
                "arrived": False,
                "status": plan["status"],
                "mode": "beside",
                "reason": "could not get beside/facing the target",
                "stalled_at": stand,
            }
        _log.info(
            "goto -> (%s,%s,%s) arrived mode=beside facing=%s", tx, ty, tz, facing
        )
        return {
            "arrived": True,
            "status": "success",
            "mode": "beside",
            "stood_at": stand,
            "pos": _fmt(bot.get_pos()),
            "facing_target": facing,
            "aimed_block": _fmt(looked) if looked is not None else None,
        }

    # mode == "on": finish onto the target cell if the drive stopped short,
    # walking cardinal steps around obstacles the planner refused (fence corner,
    # half-slab). Full-block moves land the bot squarely in the cell.
    manual = False
    if tuple(_cell(bot.get_pos())) != (tx, ty, tz):
        manual = _cardinal_finish(bot, tx, ty, tz)
    cell = tuple(_cell(bot.get_pos()))
    if cell != (tx, ty, tz):
        _log.warning(
            "goto -> (%s,%s,%s) stopped short at %s (status=%s)",
            tx,
            ty,
            tz,
            list(cell),
            plan["status"],
        )
        return {
            "arrived": False,
            "status": "stopped_short",
            "mode": "on",
            "reason": "could not complete the final step onto the target",
            "stalled_at": list(cell),
        }
    _log.info("goto -> (%s,%s,%s) arrived mode=on manual=%s", tx, ty, tz, manual)
    return {
        "arrived": True,
        "status": "success_manual" if manual else "success",
        "mode": "on",
        "stood_at": list(cell),
        "pos": _fmt(bot.get_pos()),
    }


# How far (Manhattan, in cells) the cardinal finisher will search/walk from
# where the planner stopped. The finisher only runs after mineflayer-pathfinder
# got the bot close, so the gap is small; this bounds the get_block cost.
_FINISH_WINDOW = 8

# 4-connected cardinal neighbours for the finisher (the bot turns, then walks).
_STEPS_XZ: tuple[tuple[int, int], ...] = ((1, 0), (-1, 0), (0, 1), (0, -1))


def _xz(pos: Any) -> tuple[int, int]:
    """Floored X/Z cell — Y is ignored so a half-slab step doesn't fail a check."""
    return (math.floor(pos[0]), math.floor(pos[2]))


def _walkable_cell(bot: Any, x: int, y: int, z: int) -> bool:
    """A cell the bot can stand in: air at feet+head, solid floor below.

    A fence at feet fails the feet check, so the finisher routes around fences;
    a slab counts as a solid floor, so half-block steps are fine.
    """
    return (
        _is_empty(bot.get_block(x, y, z))
        and _is_empty(bot.get_block(x, y + 1, z))
        and not _is_empty(bot.get_block(x, y - 1, z))
    )


def _cardinal_route(
    bot: Any, start: tuple[int, int, int], tx: int, ty: int, tz: int
) -> list[tuple[int, int, int]] | None:
    """Shortest 4-connected walkable route (cells after start) to the target.

    Searches the bot's feet plane within ``_FINISH_WINDOW`` of the target, using
    the bot's own block reads, so it plans exactly what plain move_forward can
    walk. ``None`` if no cardinal route reaches the target in the window.
    """
    from collections import deque

    sx, _sy, sz = start
    if (sx, sz) == (tx, tz):
        return []
    seen = {(sx, sz)}
    queue: deque[tuple[tuple[int, int], list[tuple[int, int, int]]]] = deque(
        [((sx, sz), [])]
    )
    while queue:
        (cx, cz), path = queue.popleft()
        for dx, dz in _STEPS_XZ:
            nx, nz = cx + dx, cz + dz
            if (nx, nz) in seen or abs(nx - tx) + abs(nz - tz) > _FINISH_WINDOW:
                continue
            seen.add((nx, nz))
            if not _walkable_cell(bot, nx, ty, nz):
                continue
            step_path = [*path, (nx, ty, nz)]
            if (nx, nz) == (tx, tz):
                return step_path
            queue.append(((nx, nz), step_path))
    return None


def _cardinal_finish(bot: Any, tx: int, ty: int, tz: int) -> bool:
    """Walk cardinal steps from where the planner parked onto the target.

    Implements the "walk, turn, walk" approach: a small BFS to the target over
    walkable cells, then ``look_at`` + ``move_forward(1)`` per cell, checking the
    bot reached each one (X/Z only, so a slab's half-step doesn't fail it).
    Returns whether the bot's X/Z cell is the target afterwards.
    """
    start = _cell(bot.get_pos())
    route = _cardinal_route(bot, start, tx, ty, tz)
    if not route:
        return False
    for nx, ny, nz in route:
        bot.look_at(nx, ny, nz)
        bot.move_forward(1)
        if _xz(bot.get_pos()) != (nx, nz):
            return False  # a step failed to land — stop rather than wander
    return _xz(bot.get_pos()) == (tx, tz)


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


def _node_xyz(node: Any) -> list[int]:
    """Extract a Move node's block position as integer ``[x, y, z]``."""
    return [int(node.x), int(node.y), int(node.z)]


def _round(value: object) -> float | None:
    return round(float(value), 2) if value is not None else None


def _int_or_none(value: object) -> int | None:
    return int(value) if value is not None else None


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

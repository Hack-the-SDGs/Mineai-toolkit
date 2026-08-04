"""RETAINED, NOT REGISTERED — the mineflayer-pathfinder navigator.

This is the previous navigator, kept for reference and reuse on open-terrain
(normal-physics) servers where mineflayer-pathfinder's diagonals/parkour/digging
are an advantage. It is **not** wired into ``server.py``, so its tools are not
exposed to the model. The default navigator is now the grid walker in
``tools/pathfinder.py``, which handles the fence-lattice quest worlds this
mineflayer-based one cannot (it refuses to stand on fences and drops cells with
head-height fence rails). To re-enable this one, import it in ``server.py`` and
call ``register``.

Pathfinder tools for larger navigation tasks.

Navigation uses ``mineflayer-pathfinder`` on a normal-physics server. The design
goal here is **precision**: ``pathfinder_goto`` lands the bot on the exact block
you name, never a radius and never "somewhere beside it".

The coordinates you pass are resolved to a single standable *feet cell*:

* you name an **air** cell with solid floor below → the bot stands **in** it;
* you name a **solid** block (a road/floor tile) with air above → the bot stands
  **on top** of it (feet at ``y + 1``).

Either way the bot ends up on the block you meant. Standing *beside* a block to
dig/use/place it is a separate, explicit tool (``pathfinder_goto_beside``) so the
travel path never quietly parks the bot next to the target instead of on it.

``getPathTo`` plans the route (no movement) and every plan — success or failure —
is logged with its full path array, status and search stats, so a failed goto can
be diagnosed from the log instead of guessed at.
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
# is an occupied block — a floor to stand on, or a wall to route around.
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
        """Walk to the block ``(x, y, z)`` and stand **on it**, precisely.

        The coordinates are resolved to one exact standable cell and driven with
        an exact goal — no radius, so the bot does not stop a few blocks short or
        past the target:

        * name an **air** cell (floor below) → stands **in** it (``kind: in``);
        * name a **solid** tile (road/floor) → stands **on top** of it
          (``kind: on_top``, feet at ``y + 1``).

        The last step onto the cell is finished with plain cardinal walking when
        ``mineflayer-pathfinder`` refuses a squeeze it could physically make (a
        one-wide fenced corridor, a half-slab), so a fenced road still lands.

        Returns ``arrived``, ``kind``, ``status``, ``requested`` (what you
        passed), ``stand_cell`` (the feet cell reached) and ``pos``. A target
        that is not standable (no floor, or blocked overhead) returns
        ``arrived: False`` with ``status: not_standable`` — pick another cell. No
        route returns ``arrived: False`` and the bot does **not** move: that
        means "unreachable, switch target", not "retry". To stand *beside* a
        block to dig/use/place it, use ``pathfinder_goto_beside``.
        """
        return await _run_goto(lambda: _goto_on(bot_name, x, y, z), bot_name)

    @mcp.tool
    async def pathfinder_goto_beside(
        x: float,
        y: float,
        z: float,
        bot_name: str | None = None,
    ) -> dict[str, Any] | str:
        """Walk to a cell **beside** ``(x, y, z)`` and face it, ready to act.

        For interacting with a block — dig/use/place — rather than standing on
        it. Drives an exact ``GoalGetToBlock`` (stand in a cell adjacent to the
        target), then aims at the block. Returns ``arrived``, ``facing_target``,
        ``stood_at``, ``aimed_block`` and ``pos``. Confirm ``facing_target``
        before you dig/use/place. No route → ``arrived: False`` and no movement.
        """
        return await _run_goto(lambda: _goto_beside(bot_name, x, y, z), bot_name)

    @mcp.tool
    async def pathfinder_check_path(
        x: float,
        y: float,
        z: float,
        beside: bool = False,
        include_path: bool = True,
        bot_name: str | None = None,
    ) -> dict[str, Any]:
        """Plan (but do NOT walk) the route to ``(x, y, z)`` and log it.

        Mirrors the planning of the matching goto exactly — same target-cell
        resolution, same no-dig ``getPathTo`` — but never moves the bot. Pass
        ``beside=True`` to check the ``pathfinder_goto_beside`` route instead of
        the stand-on one. Use it to see *why* a goto would fail: ``status``
        distinguishes a wall (``noPath``), a partly-blocked route (``partial``,
        with ``end`` showing how far it gets) and a search that ran out of budget
        (``timeout``).

        Returns ``reachable``, ``kind``, ``status``, ``path_length``, ``cost``,
        ``stand_cell`` (resolved feet cell), ``end`` (where the route stops) and —
        unless ``include_path=False`` — the full ``path`` array of ``[x, y, z]``.
        """
        return await to_thread.run_sync(
            lambda: _check_path(bot_name, x, y, z, beside, include_path),
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
        """Set a background pathfinder goal near ``(x, y, z)`` (loose, radius)."""
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

    Returns whatever ``fn`` returns (a result dict), or a timeout string if the
    outer backstop fires.
    """
    return await run_with_timeout(
        fn,
        bot_name=bot_name,
        timeout=PATHFINDER_TIMEOUT + _BACKSTOP_MARGIN_SECONDS,
        on_timeout="pathfinder goto",
    )


# --------------------------------------------------------------------------- #
# Target resolution: turn the coordinates you named into one standable feet cell
# --------------------------------------------------------------------------- #


def _resolve_stand_cell(
    bot: Any, x: float, y: float, z: float
) -> tuple[int, int, int, str] | None:
    """Resolve ``(x, y, z)`` to the exact cell the bot's feet should occupy.

    This is what makes goto precise regardless of whether you name the air you
    walk in or the tile you walk on:

    * an **air** cell with a solid floor below and headroom → stand **in** it,
      returned as ``(x, y, z, "in")``;
    * a **solid** block with two air cells above → stand **on top**, returned as
      ``(x, y + 1, z, "on_top")``.

    Returns ``None`` when neither holds — air with nothing to stand on, or a
    solid block with no room to stand above it — i.e. the target is not a place
    a bot can stand, so goto should report rather than wander toward it.
    """
    x, y, z = math.floor(x), math.floor(y), math.floor(z)
    here_empty = _is_empty(bot.get_block(x, y, z))
    head_empty = _is_empty(bot.get_block(x, y + 1, z))
    if here_empty:
        floor_solid = not _is_empty(bot.get_block(x, y - 1, z))
        if floor_solid and head_empty:
            return (x, y, z, "in")
        return None
    # Solid block: stand on top if the two cells above are clear (feet + head).
    above2_empty = _is_empty(bot.get_block(x, y + 2, z))
    if head_empty and above2_empty:
        return (x, y + 1, z, "on_top")
    return None


# --------------------------------------------------------------------------- #
# Planning (getPathTo, no movement) + logging
# --------------------------------------------------------------------------- #


def _plan_to_cell(
    bot: Any,
    bot_name: str | None,
    cell: tuple[int, int, int],
    goal: object,
    label: str,
) -> dict[str, Any]:
    """Plan the no-dig route to ``goal`` (which targets ``cell``), and log it.

    The route is logged in full — status, cost, search counts and the node
    array — so a failure (``partial``/``noPath``/``timeout``) is visible in the
    log rather than inferred.
    """
    movements = manager.pathfinder_movements(bot_name)
    result = bot.pathfinder.getPathTo(movements, goal, _PLAN_TIMEOUT_MS)
    status = str(result.status)
    nodes = [_node_xyz(result.path[i]) for i in range(int(result.path.length))]
    plan = {
        "label": label,
        "cell": list(cell),
        "status": status,
        "nodes": nodes,
        "cost": _round(getattr(result, "cost", None)),
        "visited": _int_or_none(getattr(result, "visitedNodes", None)),
        "generated": _int_or_none(getattr(result, "generatedNodes", None)),
    }
    _log_plan(plan)
    return plan


def _log_plan(plan: dict[str, Any]) -> None:
    """Log a getPathTo plan: full path array plus the stats that explain failure."""
    nodes = plan["nodes"]
    fields = (
        plan["label"],
        plan["cell"],
        plan["status"],
        len(nodes),
        plan["cost"],
        nodes[-1] if nodes else None,
        plan["visited"],
        plan["generated"],
        nodes,
    )
    line = (
        "plan %s -> %s status=%s len=%s cost=%s end=%s "
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
    beside: bool,
    include_path: bool,
) -> dict[str, Any]:
    """Plan-only reachability that mirrors what the matching goto would do."""
    bot = manager.resolve_bot(bot_name)
    goals = manager.pathfinder_module(bot_name).goals

    if beside:
        tx, ty, tz = math.floor(x), math.floor(y), math.floor(z)
        plan = _plan_to_cell(
            bot, bot_name, (tx, ty, tz), goals.GoalGetToBlock(tx, ty, tz), "beside"
        )
        kind: str | None = "beside"
        stand_cell: list[int] | None = None
    else:
        resolved = _resolve_stand_cell(bot, x, y, z)
        if resolved is None:
            return {
                "reachable": False,
                "status": "not_standable",
                "kind": None,
                "stand_cell": None,
                "path_length": 0,
                "cost": None,
                "end": None,
            }
        fx, fy, fz, kind = resolved
        stand_cell = [fx, fy, fz]
        plan = _plan_to_cell(
            bot, bot_name, (fx, fy, fz), goals.GoalBlock(fx, fy, fz), f"on:{kind}"
        )

    nodes = plan["nodes"]
    summary: dict[str, Any] = {
        "reachable": plan["status"] == "success",
        "status": plan["status"],
        "kind": kind,
        "stand_cell": stand_cell,
        "path_length": len(nodes),
        "cost": plan["cost"],
        "end": nodes[-1] if nodes else None,
    }
    if include_path:
        summary["path"] = nodes
    return summary


# --------------------------------------------------------------------------- #
# Driving to a goal (non-blocking setGoal + poll loop)
# --------------------------------------------------------------------------- #


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


def _drive_failed(drive: object) -> str | None:
    """Map a ``_goto`` return to a failure status, or ``None`` if it arrived."""
    if isinstance(drive, str) and drive.startswith("timeout"):
        return "timeout"
    if isinstance(drive, str) and drive.startswith("stopped near"):
        return "stopped_short"
    return None


# --------------------------------------------------------------------------- #
# The two gotos
# --------------------------------------------------------------------------- #


def _goto_on(bot_name: str | None, x: float, y: float, z: float) -> dict[str, Any]:
    """Precisely land the bot on the block ``(x, y, z)``.

    Resolves the target to an exact standable feet cell (stand-in or
    stand-on-top), plans + logs the route, drives there with an exact
    ``GoalBlock``, then — if the planner parked a step short of a squeeze it
    refuses but the bot can walk (a fenced one-wide corridor, a half-slab) —
    finishes with plain cardinal steps. Never moves when the target is not
    standable or has no route.
    """
    bot = manager.resolve_bot(bot_name)
    requested = [math.floor(x), math.floor(y), math.floor(z)]

    resolved = _resolve_stand_cell(bot, x, y, z)
    if resolved is None:
        _log.warning(
            "goto -> %s NOT started: target is not standable (no floor / blocked overhead)",
            requested,
        )
        return {
            "arrived": False,
            "status": "not_standable",
            "kind": None,
            "requested": requested,
            "stand_cell": None,
            "reason": "target is not a standable cell (no floor below, or no room above)",
        }
    fx, fy, fz, kind = resolved
    stand_cell = [fx, fy, fz]

    goals = manager.pathfinder_module(bot_name).goals
    plan = _plan_to_cell(
        bot, bot_name, (fx, fy, fz), goals.GoalBlock(fx, fy, fz), f"on:{kind}"
    )
    nodes = plan["nodes"]
    if not nodes:
        _log.warning(
            "goto -> %s (cell %s) NOT started: status=%s (no route from here)",
            requested,
            stand_cell,
            plan["status"],
        )
        return {
            "arrived": False,
            "status": plan["status"],
            "kind": kind,
            "requested": requested,
            "stand_cell": stand_cell,
            "reason": "no route from current position",
        }

    # Drive to the closest reachable node — the target itself on success, or the
    # nearest the planner reached on a partial plan, so the cardinal finish below
    # starts right beside the target cell.
    parked = nodes[-1]
    drive = _goto(
        goals.GoalBlock(int(parked[0]), int(parked[1]), int(parked[2])), bot_name
    )
    failed = _drive_failed(drive)

    # Finish onto the exact feet cell if the drive stopped short, walking cardinal
    # steps around the obstacles the planner refused (fence corner, half-slab).
    manual = False
    if tuple(_cell(bot.get_pos())) != (fx, fy, fz):
        manual = _cardinal_finish(bot, fx, fy, fz)
    cell = tuple(_cell(bot.get_pos()))

    if cell != (fx, fy, fz):
        status = failed or "stopped_short"
        _log.warning(
            "goto -> %s stopped short at %s (status=%s)",
            requested,
            list(cell),
            status,
        )
        return {
            "arrived": False,
            "status": status,
            "kind": kind,
            "requested": requested,
            "stand_cell": stand_cell,
            "stalled_at": list(cell),
            "reason": drive if isinstance(drive, str) else "could not reach the target cell",
        }

    _log.info("goto -> %s arrived kind=%s manual=%s", requested, kind, manual)
    return {
        "arrived": True,
        "status": "success_manual" if manual else "success",
        "kind": kind,
        "requested": requested,
        "stand_cell": stand_cell,
        "pos": _fmt(bot.get_pos()),
    }


def _goto_beside(bot_name: str | None, x: float, y: float, z: float) -> dict[str, Any]:
    """Stand in a cell beside ``(x, y, z)`` and face it, for dig/use/place."""
    bot = manager.resolve_bot(bot_name)
    tx, ty, tz = math.floor(x), math.floor(y), math.floor(z)
    goals = manager.pathfinder_module(bot_name).goals

    plan = _plan_to_cell(
        bot, bot_name, (tx, ty, tz), goals.GoalGetToBlock(tx, ty, tz), "beside"
    )
    nodes = plan["nodes"]
    if not nodes:
        _log.warning(
            "goto beside -> (%s,%s,%s) NOT started: status=%s (no route)",
            tx,
            ty,
            tz,
            plan["status"],
        )
        return {
            "arrived": False,
            "status": plan["status"],
            "kind": "beside",
            "reason": "no route from current position",
        }

    parked = nodes[-1]
    drive = _goto(
        goals.GoalBlock(int(parked[0]), int(parked[1]), int(parked[2])), bot_name
    )
    failed = _drive_failed(drive)

    bot.look_at(tx, ty, tz)
    looked = bot.look_block()
    facing = _is_target(looked, tx, ty, tz)
    if not facing and (failed or plan["status"] != "success"):
        _log.warning(
            "goto beside -> (%s,%s,%s) NOT reached (status=%s)",
            tx,
            ty,
            tz,
            failed or plan["status"],
        )
        return {
            "arrived": False,
            "status": failed or plan["status"],
            "kind": "beside",
            "reason": "could not get beside/facing the target",
            "stalled_at": parked,
        }

    _log.info("goto beside -> (%s,%s,%s) arrived facing=%s", tx, ty, tz, facing)
    return {
        "arrived": True,
        "status": "success",
        "kind": "beside",
        "stood_at": parked,
        "pos": _fmt(bot.get_pos()),
        "facing_target": facing,
        "aimed_block": _fmt(looked) if looked is not None else None,
    }


# --------------------------------------------------------------------------- #
# Cardinal finisher: walk the last step(s) the planner refused
# --------------------------------------------------------------------------- #

# How far (Manhattan, in cells) the cardinal finisher will search/walk from
# where the planner stopped. The finisher only runs after mineflayer-pathfinder
# got the bot close, so the gap is small; this bounds the get_block cost.
_FINISH_WINDOW = 8

# 4-connected cardinal neighbours for the finisher (the bot turns, then walks).
_STEPS_XZ: tuple[tuple[int, int], ...] = ((1, 0), (-1, 0), (0, 1), (0, -1))


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

    A small BFS to the target over walkable cells, then ``look_at`` +
    ``move_forward(1)`` per cell, checking the bot reached each one (X/Z only, so
    a slab's half-step doesn't fail it). Returns whether the bot's X/Z cell is
    the target afterwards.
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


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #


def _cell(pos: Any) -> tuple[int, int, int]:
    """Floored block cell of a ``(x, y, z)`` position."""
    return (math.floor(pos[0]), math.floor(pos[1]), math.floor(pos[2]))


def _xz(pos: Any) -> tuple[int, int]:
    """Floored X/Z cell — Y is ignored so a half-slab step doesn't fail a check."""
    return (math.floor(pos[0]), math.floor(pos[2]))


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

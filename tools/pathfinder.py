"""Grid navigator — our own pathfinder, driven through minethon.

Built for the fence-lattice quest worlds (e.g. ``world-g0``) where
mineflayer-pathfinder fails — it cuts diagonals straight through fence corners
(upstream #310) and its planning around fences is unreliable. This navigator is a
simple, deterministic cardinal-only A* over the bot's *own* block reads, so we
fully control walkability, facing and centering.

    a cell (x, y, z) is STANDABLE when
        feet   (x, y,   z)  is air
        head   (x, y+1, z)  is air
        floor  (x, y-1, z)  is a solid block — NOT air, and NOT a fence/wall

**Fences are pure obstacles**, routed *around*: never walked into (feet), never
walked under (head), and never stood on (floor). A fence is 1.5 blocks tall, so
its collision reaches into the cell above — a bot cannot walk horizontally onto a
fence top, it would have to jump. Counting a fence as floor made A* plan routes
over fence tops that the walk then stalled against; excluding it fixes that. The
floor check also keeps us on one level (we never step into a hole or off an edge),
which matches the "same level only, just make it work" scope.

Two tools, deliberately split:

* ``find_path(x, y, z)`` — plan a valid cell route from where the bot stands to
  the target, using A* over the 4-connected grid. **No movement.** Returns the
  route (or why there isn't one). Any valid route, not a fancy one.
* ``goto(x, y, z)`` — plan the same route, then **walk** it: face each next cell
  and step forward one cell, verifying the landing before the next step. Always
  moves forward (never strafes/reverses); facing the next cell absolutely means
  we never have to decide "turn left vs right".

Multi-level (jump up / drop down) is intentionally out of scope for now, but the
neighbour generator is written so enabling it later is flipping ``_MAX_STEP_UP`` /
``_MAX_DROP`` rather than rewriting the search.
"""

from __future__ import annotations

import heapq
import math
import os
from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING, Any

from bot_manager import manager
from bot_session import run_with_timeout
from logging_setup import get_logger
from tools.facing import facing_ok, yaw_for_direction

if TYPE_CHECKING:
    from fastmcp import FastMCP

# A* node budget. Each node costs up to three get_block reads over the bridge, so
# an unreachable target can't explode into thousands of reads — we give up and
# report "no path" instead. Override with MINEAI_GRID_MAX_NODES.
GRID_MAX_NODES = int(os.environ.get("MINEAI_GRID_MAX_NODES", "4096"))

# Backstop timeout for a whole find_path / goto call (seconds). A walk is bounded
# by the route length and each step verifies, so this only guards a wedged bridge
# read. Override with MINEAI_GRID_TIMEOUT.
GRID_TIMEOUT = float(os.environ.get("MINEAI_GRID_TIMEOUT", "120"))

# How close to a cell's middle (cx+0.5, cz+0.5) still counts as centered. On a
# physics server move_forward stops wherever progress crossed the block count, so
# the bot can finish off-center — bad in a fence corridor, where off-center clips
# the side fences and skews the next turn. Beyond this offset we nudge to the
# middle. Override with MINEAI_GRID_CENTER_TOL.
_CENTER_TOL = float(os.environ.get("MINEAI_GRID_CENTER_TOL", "0.2"))

# Vertical reach, in cells. Both 0 → same-level only (current scope). Raising
# _MAX_STEP_UP enables jump-up neighbours; raising _MAX_DROP enables walk-off
# drops. The search and walker already branch on these, so levels are a config
# change, not a rewrite.
_MAX_STEP_UP = 0
_MAX_DROP = 0

# 4-connected cardinal neighbours (dx, dz). No diagonals — that removes the whole
# fence-corner-cut failure mode by construction.
_STEPS_XZ: tuple[tuple[int, int], ...] = ((1, 0), (-1, 0), (0, 1), (0, -1))

# get_block names that mean an empty cell (air the bot can stand in / a non-floor).
_EMPTY_BLOCKS = {"", "air", "cave_air", "void_air"}

_log = get_logger("pathfinder")


def register(mcp: FastMCP) -> None:
    """Register the grid navigator tools on ``mcp``."""

    @mcp.tool
    async def find_path(
        x: float,
        y: float,
        z: float,
        bot_name: str | None = None,
    ) -> dict[str, Any]:
        """Plan a walkable route to ``(x, y, z)`` — but do NOT move.

        Searches the 4-connected grid from where the bot stands, treating a cell
        as walkable when its feet and head are air and it has a floor below
        (solid or fence). Returns any valid route, not an optimised one.

        Returns ``reachable``, ``target_cell`` (the feet cell you'd stand at —
        the cell itself if it's air, or on top of it if it's a block), ``route``
        (the list of ``[x, y, z]`` cells to walk, after the start), ``length``,
        and ``reason`` when unreachable. ``reachable: False`` means "pick another
        target", not "retry".
        """
        return await run_with_timeout(
            lambda: _find_path(bot_name, x, y, z),
            bot_name=bot_name,
            timeout=GRID_TIMEOUT,
            on_timeout="find_path",
        )

    @mcp.tool
    async def goto(
        x: float,
        y: float,
        z: float,
        bot_name: str | None = None,
    ) -> dict[str, Any]:
        """Walk to ``(x, y, z)``: plan a route, then step to it cell by cell.

        Plans the same route as ``find_path``, then walks it — facing each next
        cell and moving forward one cell, checking the bot actually landed before
        the next step. Always moves forward; never strafes or reverses.

        Returns ``arrived``, ``target_cell``, ``route``, ``walked`` (cells
        actually stepped), ``pos``, and — if a step failed to land —
        ``stalled_at`` with ``arrived: False``. No route → ``arrived: False`` and
        the bot does not move.
        """
        return await run_with_timeout(
            lambda: _goto(bot_name, x, y, z),
            bot_name=bot_name,
            timeout=GRID_TIMEOUT,
            on_timeout="goto",
        )


# --------------------------------------------------------------------------- #
# Planning
# --------------------------------------------------------------------------- #


def _find_path(bot_name: str | None, x: float, y: float, z: float) -> dict[str, Any]:
    """find_path tool body: plan and log a route, no movement."""
    bot = manager.resolve_bot(bot_name)
    cache: dict[tuple[int, int, int], Any] = {}
    plan = _plan(bot, cache, x, y, z)
    _log_plan(x, y, z, plan)
    if not plan["ok"]:
        return {
            "reachable": False,
            "reason": plan["reason"],
            "target_cell": list(plan["goal"]) if plan.get("goal") else None,
            "route": [],
            "length": 0,
        }
    return {
        "reachable": True,
        "target_cell": list(plan["goal"]),
        "kind": plan["kind"],
        "route": [list(c) for c in plan["route"]],
        "length": len(plan["route"]),
    }


def _goto(bot_name: str | None, x: float, y: float, z: float) -> dict[str, Any]:
    """goto tool body: plan, then walk the route cell by cell."""
    bot = manager.resolve_bot(bot_name)
    cache: dict[tuple[int, int, int], Any] = {}
    plan = _plan(bot, cache, x, y, z)
    _log_plan(x, y, z, plan)
    if not plan["ok"]:
        return {
            "arrived": False,
            "status": "unreachable",
            "reason": plan["reason"],
            "target_cell": list(plan["goal"]) if plan.get("goal") else None,
            "route": [],
            "walked": 0,
        }

    route = list(plan["route"])
    goal = plan["goal"]
    walked, fail = _walk(bot, plan["start"], route)
    if fail is not None:
        _log.warning(
            "goto -> %s stalled at %s after %s/%s cells (%s)",
            list(goal),
            fail["stalled_at"],
            walked,
            len(route),
            fail["reason"],
        )
        return {
            "arrived": False,
            "status": "stalled",
            "reason": fail["reason"],
            "target_cell": list(goal),
            "route": [list(c) for c in route],
            "walked": walked,
            "stalled_at": fail["stalled_at"],
            "pos": _fmt(bot.get_pos()),
        }

    _log.info("goto -> %s arrived (%s steps)", list(goal), walked)
    return {
        "arrived": True,
        "status": "success",
        "kind": plan["kind"],
        "target_cell": list(goal),
        "route": [list(c) for c in route],
        "walked": walked,
        "pos": _fmt(bot.get_pos()),
    }


def _plan(
    bot: Any, cache: dict[tuple[int, int, int], Any], x: float, y: float, z: float
) -> dict[str, Any]:
    """Resolve the target to a standable cell and A* a route to it.

    ``ok`` False carries a ``reason`` and, when the target resolved but no route
    was found, the ``goal`` cell (so the caller can report where it aimed).
    """
    start = _cell(bot.get_pos())
    resolved = _resolve_target(bot, cache, x, y, z)
    if resolved is None:
        return {
            "ok": False,
            "reason": "target is not a standable cell (no floor, or blocked overhead)",
            "start": start,
        }
    gx, gy, gz, kind = resolved
    goal = (gx, gy, gz)
    route = _astar(bot, cache, start, goal)
    if route is None:
        return {
            "ok": False,
            "reason": "no valid path found (blocked, or beyond the search budget)",
            "start": start,
            "goal": goal,
            "kind": kind,
        }
    return {"ok": True, "start": start, "goal": goal, "kind": kind, "route": route}


def _resolve_target(
    bot: Any, cache: dict[tuple[int, int, int], Any], x: float, y: float, z: float
) -> tuple[int, int, int, str] | None:
    """Resolve ``(x, y, z)`` to the feet cell the bot should end up in.

    * the cell itself if it is already standable (you named the air you'd stand
      in) → ``"in"``;
    * one above it if the cell is a block (fence/solid) and standing on top is
      valid (you named the tile you'd stand on) → ``"on_top"``.

    ``None`` when neither is standable — nothing to stand on, or no headroom.
    """
    x, y, z = math.floor(x), math.floor(y), math.floor(z)
    if _standable(bot, cache, x, y, z):
        return (x, y, z, "in")
    if not _is_empty(_block(bot, cache, x, y, z)) and _standable(bot, cache, x, y + 1, z):
        return (x, y + 1, z, "on_top")
    return None


def _astar(
    bot: Any,
    cache: dict[tuple[int, int, int], Any],
    start: tuple[int, int, int],
    goal: tuple[int, int, int],
) -> list[tuple[int, int, int]] | None:
    """A* over standable cells; returns the cells after ``start``, or ``None``.

    Uniform step cost with a Manhattan heuristic (admissible on this grid, so it
    expands few nodes → few bridge reads). ``None`` if the goal is unreachable or
    the node budget runs out. The bot's own start cell is assumed standable (it
    is standing there); every other cell is checked before being expanded into.
    """
    if start == goal:
        return []
    open_heap: list[tuple[int, int, tuple[int, int, int]]] = [
        (_manhattan(start, goal), 0, start)
    ]
    came_from: dict[tuple[int, int, int], tuple[int, int, int]] = {}
    g_score = {start: 0}
    closed: set[tuple[int, int, int]] = set()
    expanded = 0
    while open_heap:
        _f, g, cur = heapq.heappop(open_heap)
        if cur in closed:
            continue
        closed.add(cur)
        if cur == goal:
            return _reconstruct(came_from, cur)
        expanded += 1
        if expanded > GRID_MAX_NODES:
            return None
        for nb in _neighbors(bot, cache, cur):
            if nb in closed:
                continue
            tentative = g + 1
            if tentative < g_score.get(nb, 1 << 30):
                g_score[nb] = tentative
                came_from[nb] = cur
                heapq.heappush(open_heap, (tentative + _manhattan(nb, goal), tentative, nb))
    return None


def _neighbors(
    bot: Any, cache: dict[tuple[int, int, int], Any], cell: tuple[int, int, int]
) -> Iterator[tuple[int, int, int]]:
    """Standable cells reachable in one step from ``cell``.

    Same-level cardinal steps always. Jump-up (``+1``) and drop (``-1..``) steps
    are emitted only when ``_MAX_STEP_UP`` / ``_MAX_DROP`` allow — both 0 for now,
    so this yields the four cardinal neighbours on the same Y. The vertical
    branches are here so enabling levels later is a config change.
    """
    cx, cy, cz = cell
    for dx, dz in _STEPS_XZ:
        nx, nz = cx + dx, cz + dz
        # Same level.
        if _standable(bot, cache, nx, cy, nz):
            yield (nx, cy, nz)
            continue
        # Jump up one (future: _MAX_STEP_UP >= 1).
        stepped = False
        for up in range(1, _MAX_STEP_UP + 1):
            if _standable(bot, cache, nx, cy + up, nz):
                yield (nx, cy + up, nz)
                stepped = True
                break
        if stepped:
            continue
        # Drop down (future: _MAX_DROP >= 1).
        for down in range(1, _MAX_DROP + 1):
            if _standable(bot, cache, nx, cy - down, nz):
                yield (nx, cy - down, nz)
                break


def _reconstruct(
    came_from: dict[tuple[int, int, int], tuple[int, int, int]],
    end: tuple[int, int, int],
) -> list[tuple[int, int, int]]:
    """Rebuild the path to ``end`` and drop the start cell (bot already there)."""
    path = [end]
    while end in came_from:
        end = came_from[end]
        path.append(end)
    path.reverse()
    return path[1:]


# --------------------------------------------------------------------------- #
# Walking
# --------------------------------------------------------------------------- #


def _walk(
    bot: Any,
    start: tuple[int, int, int],
    route: list[tuple[int, int, int]],
) -> tuple[int, dict[str, Any] | None]:
    """Walk ``route`` in straight runs, facing each direction before moving.

    The cells are grouped into maximal straight segments (a corridor of five
    cells in one direction is one ``move_forward(5)``, not five calls). For each
    run: turn to face that cardinal direction and **verify the facing took**
    before stepping (a wrong turn otherwise walks the wrong way), move forward the
    run length, then confirm the bot's X/Z reached the run's end cell. Always
    moves forward — the facing is what changes at a corner, never the direction of
    travel.

    Every leg ends **in the middle of its cell**: we start centered and re-center
    at each corner and the destination, so cardinal integer moves stay aligned and
    the bot never hugs a corridor's side fences.

    Returns ``(cells_walked, failure)``. ``failure`` is ``None`` on full success,
    or ``{"stalled_at", "reason"}`` at the first run that could not face or land —
    we stop there rather than wander. Y is ignored in the landing check so a fence
    top's half-block rise doesn't read as a miss.
    """
    cells = [tuple(start), *(tuple(c) for c in route)]
    walked = 0
    i = 0
    _recenter(bot, cells[0][0], cells[0][2])  # begin aligned in the start cell
    while i < len(cells) - 1:
        dx, dz = _dir(cells[i], cells[i + 1])
        # Extend the run while the direction (and level) hold.
        j = i + 1
        while (
            j < len(cells) - 1
            and cells[j][1] == cells[i][1]
            and _dir(cells[j], cells[j + 1]) == (dx, dz)
        ):
            j += 1
        run_len = j - i
        end = cells[j]

        if not _face_and_verify(bot, dx, dz):
            return walked, {
                "stalled_at": list(cells[i + 1]),
                "reason": "could not face the travel direction",
            }
        bot.move_forward(run_len)
        if _xz(bot.get_pos()) != (end[0], end[2]):
            return walked, {
                "stalled_at": list(end),
                "reason": "forward move did not reach the run end (blocked or over/undershot)",
            }
        _recenter(bot, end[0], end[2])  # step into the middle of this corner/target cell
        walked += run_len
        i = j
    return walked, None


def _recenter(bot: Any, cx: int, cz: int) -> bool:
    """Nudge the bot to the middle of cell ``(cx, cz)`` — ``(cx+0.5, cz+0.5)``.

    Best-effort and mode-aware. On a physics server we face the cell centre and
    step the small remaining distance (toward the middle is always *away* from a
    side fence, so it's safe in a corridor). On a server-authoritative grid the
    bot is already placed exactly and fractional ``move_forward`` is rejected
    (``ValueError``) — we catch that and accept the server's placement. Returns
    whether the bot ended within ``_CENTER_TOL`` of the middle; the caller treats
    a miss as non-fatal (still in the right cell), so this never fails a walk.
    """
    tx, tz = cx + 0.5, cz + 0.5
    pos = bot.get_pos()
    if math.hypot(tx - pos[0], tz - pos[2]) <= _CENTER_TOL:
        return True
    try:
        bot.look_at(tx, pos[1], tz)
        bot.move_forward(math.hypot(tx - pos[0], tz - pos[2]))
    except ValueError:
        return True  # grid server places the bot exactly; nothing to nudge
    pos = bot.get_pos()
    return math.hypot(tx - pos[0], tz - pos[2]) <= _CENTER_TOL


def _face_and_verify(bot: Any, dx: int, dz: int) -> bool:
    """Turn to face cardinal ``(dx, dz)`` and confirm the bot actually faces it.

    Sets the absolute cardinal yaw and reads it back; a grid/quest server snaps
    the turn server-authoritatively, so we allow a tolerance. One retry, because
    a server-authoritative turn can need a beat to apply. Returns whether the
    facing landed within tolerance — the caller refuses to step forward if not,
    so a failed turn can never send the bot the wrong way.
    """
    target = yaw_for_direction(dx, dz)
    for _ in range(2):
        bot.set_turn(target)
        if facing_ok(float(bot.get_yaw()), target):
            return True
    return False


def _dir(a: tuple[int, int, int], b: tuple[int, int, int]) -> tuple[int, int]:
    """Unit cardinal step (dx, dz) from cell ``a`` to adjacent cell ``b``."""
    return (_sign(b[0] - a[0]), _sign(b[2] - a[2]))


def _sign(value: int) -> int:
    return (value > 0) - (value < 0)


# --------------------------------------------------------------------------- #
# Walkability + small helpers
# --------------------------------------------------------------------------- #


def _standable(
    bot: Any, cache: dict[tuple[int, int, int], Any], x: int, y: int, z: int
) -> bool:
    """Whether the bot can stand with its feet in cell ``(x, y, z)``.

    Feet and head must be air, and the floor below must be a **solid block** —
    non-air and NOT a fence/wall. Fences are obstacles the search routes around,
    never a surface to stand on: a fence's 1.5-block collision reaches into the
    cell above, so the bot can't walk horizontally onto a fence top and a route
    planned over one stalls. The floor requirement also confines the search to one
    level — a cell over a hole is not standable, so we never drop off.
    """
    floor = _block(bot, cache, x, y - 1, z)
    return (
        _is_empty(_block(bot, cache, x, y, z))
        and _is_empty(_block(bot, cache, x, y + 1, z))
        and not _is_empty(floor)
        and not _is_tall_block(floor)
    )


def _is_tall_block(name: object) -> bool:
    """Whether a block name is a fence/wall — taller than 1, so not a valid floor.

    Name-based because ``get_block`` returns only a name (no bounding box):
    ``*_fence``, ``*_fence_gate``, ``fence`` and ``*_wall`` are the 1.5-tall blocks
    a bot can't walk onto or through. Matching ``"fence"`` anywhere also covers
    ``nether_brick_fence`` and the gates; ``_wall`` covers the cobblestone-wall
    family (``wall_torch``/``wall_sign`` end in ``_torch``/``_sign``, not
    ``_wall``, so they're not caught).
    """
    n = str(name).split(":")[-1].lower()
    return "fence" in n or n.endswith("_wall")


def _block(
    bot: Any, cache: dict[tuple[int, int, int], Any], x: int, y: int, z: int
) -> Any:
    """``bot.get_block`` with a per-plan cache (the world is static while we plan).

    Neighbours share cells (a floor read here is a feet read there), so caching
    turns the search's block reads roughly O(cells) instead of O(cells x checks),
    which matters because every miss is a bridge round-trip.
    """
    key = (x, y, z)
    if key not in cache:
        cache[key] = bot.get_block(x, y, z)
    return cache[key]


def _is_empty(name: object) -> bool:
    """Whether a ``get_block`` name means an empty (air-like) cell.

    Normalises the ``minecraft:`` namespace so ``"minecraft:air"`` and ``"air"``
    both count as empty.
    """
    if name is None:
        return True
    return str(name).split(":")[-1].lower() in _EMPTY_BLOCKS


def _manhattan(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    """Manhattan distance including Y (Y term is 0 while we stay on one level)."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])


def _cell(pos: Any) -> tuple[int, int, int]:
    """Floored block cell of a ``(x, y, z)`` position."""
    return (math.floor(pos[0]), math.floor(pos[1]), math.floor(pos[2]))


def _xz(pos: Any) -> tuple[int, int]:
    """Floored X/Z cell — Y is ignored so a fence-top half-step isn't a miss."""
    return (math.floor(pos[0]), math.floor(pos[2]))


def _log_plan(x: float, y: float, z: float, plan: dict[str, Any]) -> None:
    """Log a plan: the route and where it goes, or why it failed."""
    target = (math.floor(x), math.floor(y), math.floor(z))
    if plan["ok"]:
        route = plan["route"]
        _log.info(
            "plan -> %s goal=%s kind=%s len=%s route=%s",
            list(target),
            list(plan["goal"]),
            plan["kind"],
            len(route),
            [list(c) for c in route],
        )
    else:
        _log.warning(
            "plan -> %s FAILED: %s goal=%s",
            list(target),
            plan["reason"],
            list(plan["goal"]) if plan.get("goal") else None,
        )


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

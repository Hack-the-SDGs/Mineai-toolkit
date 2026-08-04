"""Cardinal facing — one place for the direction↔yaw convention.

Movement vectors use Minecraft's world convention:
    north = -Z, south = +Z, east = +X, west = -X.

minethon's yaw (see movement.set_turn): ``0`` faces north (-Z) and yaw increases
**counter-clockwise** (``turn`` with a positive angle turns left). So, going CCW
from north: north 0°, west 90°, south 180°, east 270°.

If a live test shows every cardinal step stalling (the bot turns the *opposite*
way), this handedness is the thing to flip — swap the west/east yaws below. The
walker's post-move position check makes a wrong convention fail safe (a clean
stall), never a wandering bot.
"""

from __future__ import annotations

# Direction (dx, dz) → name.
NORTH = (0, -1)
SOUTH = (0, 1)
EAST = (1, 0)
WEST = (-1, 0)

_DIR_TO_YAW: dict[tuple[int, int], float] = {
    NORTH: 0.0,
    WEST: 90.0,
    SOUTH: 180.0,
    EAST: 270.0,
}
_NAME_TO_DIR: dict[str, tuple[int, int]] = {
    "north": NORTH,
    "south": SOUTH,
    "east": EAST,
    "west": WEST,
}

# How far off the target cardinal yaw still counts as "facing it". Generous
# because a grid/quest server snaps turns to its own cardinal and the readback
# may be a degree or two off, or carry the server's exact cardinal value.
FACING_TOLERANCE_DEG = 15.0


def yaw_for_direction(dx: int, dz: int) -> float:
    """Yaw that faces the cardinal step ``(dx, dz)`` (one axis ±1)."""
    return _DIR_TO_YAW[(dx, dz)]


def yaw_for_name(name: str) -> float:
    """Yaw that faces a named cardinal (``"north"``/``"south"``/``"east"``/``"west"``)."""
    return _DIR_TO_YAW[_NAME_TO_DIR[name]]


def facing_ok(
    current_yaw: float, target_yaw: float, tolerance: float = FACING_TOLERANCE_DEG
) -> bool:
    """Whether ``current_yaw`` is within ``tolerance`` of ``target_yaw``.

    Compares as a circular angle, so 359° and 1° read as 2° apart, not 358°.
    """
    diff = abs((current_yaw - target_yaw + 180.0) % 360.0 - 180.0)
    return diff <= tolerance

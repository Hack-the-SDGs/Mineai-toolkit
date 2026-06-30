"""Pathfinder tools for larger navigation tasks."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from anyio import to_thread

from bot_manager import manager

if TYPE_CHECKING:
    from fastmcp import FastMCP


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
        return await to_thread.run_sync(
            lambda: _goto(_goal_near(bot_name, x, y, z, radius), bot_name),
        )

    @mcp.tool
    async def pathfinder_goto_block(
        x: float,
        y: float,
        z: float,
        bot_name: str | None = None,
    ) -> str:
        """Block until the bot reaches exactly the target block."""
        return await to_thread.run_sync(
            lambda: _goto(_goal_block(bot_name, x, y, z), bot_name),
        )

    @mcp.tool
    async def pathfinder_goto_get_to_block(
        x: float,
        y: float,
        z: float,
        bot_name: str | None = None,
    ) -> str:
        """Block until the bot reaches beside the target block."""
        return await to_thread.run_sync(
            lambda: _goto(_goal_get_to_block(bot_name, x, y, z), bot_name),
        )

    @mcp.tool
    async def pathfinder_goto_xz(
        x: float,
        z: float,
        bot_name: str | None = None,
    ) -> str:
        """Block until the bot reaches the target X/Z column; Y is unrestricted."""
        return await to_thread.run_sync(lambda: _goto(_goal_xz(bot_name, x, z), bot_name))

    @mcp.tool
    async def pathfinder_goto_near_xz(
        x: float,
        z: float,
        radius: float = 1.0,
        bot_name: str | None = None,
    ) -> str:
        """Block until the bot reaches within ``radius`` on the X/Z plane."""
        return await to_thread.run_sync(
            lambda: _goto(_goal_near_xz(bot_name, x, z, radius), bot_name),
        )

    @mcp.tool
    async def pathfinder_goto_y(y: float, bot_name: str | None = None) -> str:
        """Block until the bot reaches the target Y height."""
        return await to_thread.run_sync(lambda: _goto(_goal_y(bot_name, y), bot_name))

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


def _goto(goal: object, bot_name: str | None) -> str:
    bot = manager.resolve_bot(bot_name)
    bot.pathfinder.goto(goal)
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

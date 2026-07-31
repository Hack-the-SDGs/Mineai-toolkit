"""Interaction tools: holding items, digging, placing, using, and chatting."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bot_session import call

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """Register interaction tools on ``mcp``."""

    @mcp.tool
    async def hold(name: str, bot_name: str | None = None) -> str:
        """Equip the item named ``name`` from inventory; True on success."""
        return await call("hold", name, bot_name=bot_name)

    @mcp.tool
    async def dig(bot_name: str | None = None) -> str:
        """Dig the targeted block; returns 'coords, name' or 'none'."""
        return await call("dig", bot_name=bot_name)

    @mcp.tool
    async def place(bot_name: str | None = None) -> str:
        """Place the held block against the targeted face; 'coords, name' or 'none'."""
        return await call("place", bot_name=bot_name)

    @mcp.tool
    async def unhold(bot_name: str | None = None) -> str:
        """Put the held item back into the inventory; False if hand was empty."""
        return await call("unhold", bot_name=bot_name)

    @mcp.tool
    async def drop(
        item: str | None = None,
        count: int | None = None,
        bot_name: str | None = None,
    ) -> str:
        """Throw items on the ground.

        With no ``item`` the held stack is tossed. Given an item name, matching
        inventory stacks are tossed; ``count`` limits how many (all when omitted
        or larger than the amount carried). Returns True on success, False if
        the hand is empty or the item is not carried.
        """
        return await call("drop", item, count, bot_name=bot_name)

    @mcp.tool
    async def use(bot_name: str | None = None) -> str:
        """Use/activate the held item; True on success."""
        return await call("use", bot_name=bot_name)

    @mcp.tool
    async def use_player(username: str, bot_name: str | None = None) -> str:
        """Right-click the named player's entity (e.g. to mount/stack); True on success.

        Aims at the center of the player's bounding box automatically. Errors if
        the player is offline, in another world, or outside the bot's range.
        """
        return await call("use_player", username, bot_name=bot_name)

    @mcp.tool
    async def sneak(on: bool, bot_name: str | None = None) -> str:
        """Hold (``on=True``) or release (``on=False``) sneak; returns the new state."""
        return await call("sneak", on, bot_name=bot_name)

    @mcp.tool
    async def action(
        name: str,
        value: int | None = None,
        bot_name: str | None = None,
    ) -> str:
        """Ask the quest server to run a named action (e.g. 'put out').

        Server-authoritative: sends a vanilla trigger and does nothing
        client-side. ``value`` is an optional integer payload for quests that
        take a parameter. The datapack validates and performs (or ignores) it.
        """
        await call("action", name, value, bot_name=bot_name)
        return "sent"

    @mcp.tool
    async def put_out(
        value: int | None = None,
        bot_name: str | None = None,
    ) -> str:
        """Run the 'put out' quest action (a fixed-name wrapper over ``action``).

        Equivalent to calling ``action`` with ``name='put out'``. ``value`` is an
        optional integer payload passed through to the quest.
        """
        await call("action", "put out", value, bot_name=bot_name)
        return "sent"

    @mcp.tool
    async def chat(message: str, bot_name: str | None = None) -> str:
        """Send a chat message to the server."""
        await call("chat", message, bot_name=bot_name)
        return "sent"

    @mcp.tool
    async def set_height(level: int, bot_name: str | None = None) -> str:
        """Set bot size level from 1 to 5."""
        await call("set_height", level, bot_name=bot_name)
        return "set"

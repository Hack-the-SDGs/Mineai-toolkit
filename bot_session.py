"""Bot lifecycle and call-dispatch shared by every tool module.

minethon's ``Bot`` is synchronous and talks to Node over JSPyBridge, while
FastMCP tool handlers are async. The helpers here bridge the two:

  * ``lifespan`` connects the bot once at server startup and blocks on
    ``wait_spawn()`` so no tool ever runs against a half-connected bot.
  * ``call`` dispatches a Bot method on a worker thread (so the asyncio loop
    stays responsive) and formats the result as model-friendly text.

Connection options come from the environment — see ``bot_options``.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from contextlib import asynccontextmanager
from typing import Any

from anyio import to_thread
from fastmcp import FastMCP
from minethon import Bot, create_bot

# One owned bot per process; set during ``lifespan``, read via ``_require``.
_BOT: Bot | None = None


def bot_options() -> dict[str, Any]:
    """Read mineflayer connection options from the environment.

    Mirrors ``create_bot`` kwargs. MINETHON_HOST and MINETHON_USERNAME are
    required; the rest fall back to localhost-friendly defaults.
    """
    host = os.environ.get("MINETHON_HOST")
    username = os.environ.get("MINETHON_USERNAME")
    if not host or not username:
        msg = "Set MINETHON_HOST and MINETHON_USERNAME before starting the server."
        raise RuntimeError(msg)
    options: dict[str, Any] = {
        "host": host,
        "port": int(os.environ.get("MINETHON_PORT", "25565")),
        "username": username,
    }
    if version := os.environ.get("MINETHON_VERSION"):
        options["version"] = version
    if auth := os.environ.get("MINETHON_AUTH"):
        options["auth"] = auth  # "offline" | "microsoft"
    return options


def _require() -> Bot:
    if _BOT is None:  # pragma: no cover - guarded by lifespan ordering
        msg = "Bot not initialised yet."
        raise RuntimeError(msg)
    return _BOT


@asynccontextmanager
async def lifespan(_server: FastMCP):
    """Connect the bot and wait for spawn before serving any tool calls."""
    global _BOT  # noqa: PLW0603 - single owned handle for the process
    bot = await to_thread.run_sync(lambda: create_bot(**bot_options()))
    await to_thread.run_sync(bot.wait_spawn)
    _BOT = bot
    try:
        yield
    finally:
        _BOT = None
        await to_thread.run_sync(lambda: bot.quit("mcp server shutting down"))


def _fmt(value: object) -> str:
    """Render bot return values as compact, model-friendly text."""
    if value is None:
        return "none"
    if isinstance(value, tuple):
        return ", ".join(_fmt(v) for v in value)
    if isinstance(value, Iterable) and not isinstance(value, str):
        return "; ".join(_fmt(v) for v in value) or "empty"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


async def call(method: str, *args: object) -> str:
    """Dispatch a Bot method on a worker thread and format the result."""
    fn = getattr(_require(), method)
    result = await to_thread.run_sync(fn, *args)
    return _fmt(result)

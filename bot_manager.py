"""Shared bot lifecycle state for MCP tools and external UI handlers.

This module is intentionally synchronous. minethon's Bot API is synchronous,
and MCP/HTTP adapters can decide whether to call these functions directly or
from a worker thread.
"""

from __future__ import annotations

import contextlib
import os
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from threading import RLock
from typing import Any

from minethon import Bot, EventAdaptor
from minethon._bridge import get_mineflayer
from minethon._event_login import resolve_account

from event_log import log as activity
from logging_setup import get_logger

CreateOptions = dict[str, Any]

# get_logger (not logging.getLogger) so handlers are attached — otherwise these
# records have nowhere to go and info-level lines are dropped silently.
logger = get_logger("bots")


def _record(name: str, **fields: Any) -> None:
    """Log a bot lifecycle moment to stderr and to the activity timeline.

    Connection failures are the hardest thing for a student to diagnose — a
    kicked bot otherwise just sits there looking idle. Surfacing the reason in
    the UI turns "nothing happened" into "unverified_username".
    """
    error = fields.pop("error", None)
    activity.append(
        source="system",
        kind="bot",
        name=name,
        arguments=fields or None,
        error=error,
    )
    if error:
        logger.warning("%s: %s (%s)", name, error, fields)
    else:
        logger.info("%s: %s", name, fields)


# Dev/test fallback: MC_* environment variables (loaded from a .env file by
# main.py) supply connection defaults when no account shorthand is used. Lets a
# developer keep server-wide settings in one file and type only a username and
# password in the UI. Explicit options always win; the shorthand path ignores
# these entirely so student machines behave identically with or without a .env.
_ENV_OPTION_KEYS: dict[str, str] = {
    "MC_HOST": "host",
    "MC_PORT": "port",
    "MC_USERNAME": "username",
    "MC_PASSWORD": "password",
    "MC_AUTH": "auth",
    "MC_AUTH_SERVER": "auth_server",
    "MC_SESSION_SERVER": "session_server",
    "MC_VERSION": "version",
}


@dataclass
class BotRecord:
    """Lifecycle metadata for one managed bot."""

    name: str
    bot: Bot
    account: str | None
    options: CreateOptions
    pathfinder_module: Any | None = None
    movements: Any | None = None
    created_at: float = field(default_factory=time.time)
    spawned: bool = False
    closed: bool = False
    end_reason: str | None = None
    kicked_reason: str | None = None
    last_error: str | None = None


class BotManager:
    """Owns named minethon bots and the currently active bot."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._bots: dict[str, BotRecord] = {}
        self._active: str | None = None

    def create_bot(
        self,
        name: str,
        *,
        account: str | None = None,
        wait_spawn: bool = True,
        height: int | None = None,
        **options: Any,
    ) -> dict[str, Any]:
        """Create a named bot and optionally wait until it has spawned.

        ``account`` supports minethon's event shorthand path, e.g. ``"g_swim"``
        or ``"swim"``. Explicit options override shorthand-resolved defaults.
        """
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Bot name is required.")

        with self._lock:
            if clean_name in self._bots and not self._bots[clean_name].closed:
                raise ValueError(f"Bot already exists: {clean_name}")

        bot_options = self._resolve_options(account, options)
        _record(
            "bot_connecting",
            bot=clean_name,
            account=account,
            **self._public_options(bot_options),
        )
        bot = self._create_managed_bot(bot_options)
        pathfinder_module = bot.load_plugin("mineflayer-pathfinder")
        record = BotRecord(
            name=clean_name,
            bot=bot,
            account=account,
            options=self._public_options(bot_options),
            pathfinder_module=pathfinder_module,
        )
        bot.bind(_LifecycleEvents(self, clean_name))

        with self._lock:
            self._bots[clean_name] = record
            if self._active is None:
                self._active = clean_name

        try:
            if wait_spawn:
                bot.wait_spawn()
                with self._lock:
                    record.spawned = True
                if height is not None:
                    bot.set_height(height)
        except Exception as exc:
            with self._lock:
                record.last_error = str(exc)
            _record("bot_create_failed", bot=clean_name, error=str(exc))
            raise

        _record("bot_created", bot=clean_name, username=_safe_str(bot.username))
        return self.check_bot_health(clean_name)

    def list_bots(self) -> list[dict[str, Any]]:
        """Return health snapshots for every known bot."""
        with self._lock:
            names = list(self._bots)
        return [self.check_bot_health(name) for name in names]

    def check_bot_health(self, name: str) -> dict[str, Any]:
        """Return a best-effort health snapshot for one bot."""
        record = self._require_record(name)
        bot = record.bot

        js_bot = getattr(bot, "_js", None)
        client = getattr(js_bot, "_client", None)
        ended = (
            bool(getattr(client, "ended", False))
            if client is not None
            else record.closed
        )
        spawned = (
            getattr(js_bot, "entity", None) is not None if js_bot is not None else False
        )

        snapshot: dict[str, Any] = {
            "name": record.name,
            "active": self.get_active_bot() == record.name,
            "account": record.account,
            "username": _safe_str(getattr(bot, "username", None)),
            "created_at": record.created_at,
            "spawned": bool(spawned or record.spawned),
            "connected": not ended and not record.closed,
            "closed": record.closed,
            "end_reason": record.end_reason,
            "kicked_reason": record.kicked_reason,
            "last_error": record.last_error,
            "options": record.options,
            "pathfinder_loaded": _has_pathfinder(bot),
        }

        if snapshot["spawned"] and snapshot["connected"]:
            snapshot["position"] = _safe_call(bot.get_pos)
            snapshot["height"] = _safe_call(bot.get_height)
            snapshot["health"] = _safe_float(getattr(bot, "health", None))
            snapshot["food"] = _safe_float(getattr(bot, "food", None))
            if snapshot["pathfinder_loaded"]:
                pathfinder = getattr(bot, "pathfinder", None)
                snapshot["pathfinder"] = {
                    "moving": _safe_call(pathfinder.isMoving),
                    "mining": _safe_call(pathfinder.isMining),
                    "building": _safe_call(pathfinder.isBuilding),
                    "goal": _safe_str(getattr(pathfinder, "goal", None)),
                }

        return snapshot

    def set_active_bot(self, name: str) -> dict[str, Any]:
        """Select which bot action tools use by default."""
        record = self._require_record(name)
        if record.closed:
            raise ValueError(f"Bot is closed: {name}")
        with self._lock:
            self._active = record.name
        _record("active_bot_changed", bot=record.name)
        return self.check_bot_health(record.name)

    def get_active_bot(self) -> str | None:
        """Name of the active bot, if any."""
        with self._lock:
            return self._active

    def close_bot(self, name: str, reason: str = "closed by user") -> dict[str, Any]:
        """Quit and mark one bot closed."""
        record = self._require_record(name)
        if not record.closed:
            try:
                record.bot.quit(reason)
            except Exception as exc:
                record.last_error = str(exc)
                raise
            finally:
                with self._lock:
                    record.closed = True
                    record.end_reason = record.end_reason or reason
                    if self._active == record.name:
                        self._active = self._next_open_bot(exclude=record.name)
                _record("bot_closed", bot=record.name, reason=reason)
        return self.check_bot_health(record.name)

    def forget_bot(self, name: str) -> dict[str, Any]:
        """Close the bot if needed, then drop it from the list entirely.

        Closing alone keeps the record so the card can still show *why* a bot
        died (a kick reason is often the only diagnostic available). Forgetting
        is the deliberate second step once that has been read.
        """
        record = self._require_record(name)
        if not record.closed:
            self.close_bot(name, "removed by user")

        with self._lock:
            self._bots.pop(record.name, None)
            if self._active == record.name:
                self._active = self._next_open_bot(exclude=record.name)
        _record("bot_removed", bot=record.name)
        return {"name": record.name, "removed": True}

    def forget_closed(self) -> list[str]:
        """Drop every closed bot. Returns the names removed."""
        with self._lock:
            names = [name for name, rec in self._bots.items() if rec.closed]
        for name in names:
            self.forget_bot(name)
        return names

    def close_all(self, reason: str = "mineai shutting down") -> None:
        """Best-effort cleanup for process shutdown."""
        with self._lock:
            names = list(self._bots)
        for name in names:
            try:
                self.close_bot(name, reason)
            except Exception:
                continue

    def resolve_bot(self, name: str | None = None) -> Bot:
        """Return an explicit bot, or the active bot when ``name`` is omitted."""
        target = name or self.get_active_bot()
        if not target:
            raise RuntimeError("No active bot. Create/select a bot first.")
        record = self._require_record(target)
        if record.closed:
            raise RuntimeError(f"Bot is closed: {target}")
        return record.bot

    def call(self, method: str, *args: object, bot_name: str | None = None) -> str:
        """Dispatch one Bot method and format the result for model use."""
        fn = getattr(self.resolve_bot(bot_name), method)
        return _fmt(fn(*args))

    def load_pathfinder(self, bot_name: str | None = None) -> str:
        """Ensure mineflayer-pathfinder is loaded, with digging disabled."""
        bot = self.resolve_bot(bot_name)
        record = self._require_record(bot_name or self.get_active_bot() or "")
        if _has_pathfinder(bot):
            if record.pathfinder_module is None:
                record.pathfinder_module = bot.require("mineflayer-pathfinder")
        else:
            record.pathfinder_module = bot.load_plugin("mineflayer-pathfinder")
        self._ensure_no_dig(record)
        return "loaded"

    def _ensure_no_dig(self, record: BotRecord) -> None:
        """Install a Movements profile that never digs, so paths route around.

        ``canDig`` is mineflayer-pathfinder's own switch for "break a block to
        open a path"; turning it off makes goto/setGoal navigate around
        obstacles instead of tunnelling through them. Built once and cached: a
        fresh Movements re-scans the block registry, and the pathfinder keeps
        whatever profile was last set. Needs a spawned bot (registry/world), so
        it runs lazily on first pathfinder use rather than at create time.
        """
        if record.movements is not None:
            return
        module = record.pathfinder_module or record.bot.require(
            "mineflayer-pathfinder"
        )
        js_bot = getattr(record.bot, "_js", None)
        # JSPyBridge treats calling a JS class as `new`, same as the GoalNear
        # construction in tools/pathfinder.py.
        movements = module.Movements(js_bot)
        movements.canDig = False
        record.bot.pathfinder.setMovements(movements)
        record.movements = movements

    def clear_pathfinder_goal(self, bot_name: str | None = None) -> None:
        """Best-effort stop + drop the pathfinder goal; no-op if unavailable.

        Called when an MCP tool times out: an abandoned goto or a background
        setGoal must not leave the bot wandering after the model has given up
        waiting. Every step is suppressed because the bridge may be mid-call on
        another thread, and a failure here must never mask the timeout itself.
        """
        try:
            bot = self.resolve_bot(bot_name)
        except Exception:
            return
        if not _has_pathfinder(bot):
            return
        with contextlib.suppress(Exception):
            bot.pathfinder.stop()
        with contextlib.suppress(Exception):
            bot.pathfinder.setGoal(None)

    def pathfinder_module(self, bot_name: str | None = None) -> Any:
        """Return the pathfinder npm module, loading it if needed."""
        self.load_pathfinder(bot_name)
        record = self._require_record(bot_name or self.get_active_bot() or "")
        if record.pathfinder_module is None:
            record.pathfinder_module = record.bot.require("mineflayer-pathfinder")
        return record.pathfinder_module

    def mark_spawned(self, name: str) -> None:
        with self._lock:
            if record := self._bots.get(name):
                record.spawned = True
        _record("bot_spawned", bot=name)

    def mark_ended(self, name: str, reason: object | None = None) -> None:
        with self._lock:
            if record := self._bots.get(name):
                record.closed = True
                record.end_reason = _safe_str(reason)
                if self._active == name:
                    self._active = self._next_open_bot(exclude=name)
        _record("bot_disconnected", bot=name, reason=_safe_str(reason))

    def mark_kicked(self, name: str, reason: object | None = None) -> None:
        with self._lock:
            if record := self._bots.get(name):
                record.kicked_reason = _safe_str(reason)
        # Usually the only clue for an auth misconfiguration, e.g.
        # "unverified_username" when the server is online-mode but auth is not set.
        _record("bot_kicked", bot=name, error=_safe_str(reason))

    def mark_error(self, name: str, error: object) -> None:
        with self._lock:
            if record := self._bots.get(name):
                record.last_error = _safe_str(error)
        _record("bot_error", bot=name, error=_safe_str(error))

    def _require_record(self, name: str) -> BotRecord:
        with self._lock:
            record = self._bots.get(name)
        if record is None:
            raise KeyError(f"Unknown bot: {name}")
        return record

    def _next_open_bot(self, *, exclude: str) -> str | None:
        for name, record in self._bots.items():
            if name != exclude and not record.closed:
                return name
        return None

    @staticmethod
    def _resolve_options(account: str | None, options: CreateOptions) -> CreateOptions:
        if account is not None:
            return {**resolve_account(account), **options}
        resolved = {**_env_options(), **options}
        # A password with no auth mode means offline mode in minecraft-protocol
        # (createClient.js: `case 'offline': default:`), which silently drops the
        # password and both Drasl URLs — an online-mode server then rejects the
        # bot for reasons that look nothing like a credentials problem. Anyone
        # supplying a password wants authenticated login, so assume it.
        if resolved.get("password") and not resolved.get("auth"):
            resolved["auth"] = "mojang"
        return resolved

    @staticmethod
    def _create_managed_bot(options: CreateOptions) -> Bot:
        """Create a Bot without minethon's student-script process exit hooks.

        ``minethon.create_bot`` is ideal for one-off student scripts, but it
        installs a disconnect handler that exits the Python process. A server
        needs to survive one bot disconnecting, so we create the mineflayer bot
        directly and wrap it with minethon's public ``Bot`` facade.
        """
        mineflayer = get_mineflayer()
        js_options = {_to_camel(key): value for key, value in options.items()}
        return Bot(mineflayer.createBot(js_options))

    @staticmethod
    def _public_options(options: CreateOptions) -> CreateOptions:
        hidden = {"password"}
        return {key: value for key, value in options.items() if key not in hidden}


class _LifecycleEvents(EventAdaptor):
    """Small non-blocking event bridge from minethon into BotManager."""

    def __init__(self, manager: BotManager, name: str) -> None:
        self._manager = manager
        self._name = name

    def on_spawn(self) -> None:
        self._manager.mark_spawned(self._name)

    def on_end(self, reason: object = None) -> None:
        self._manager.mark_ended(self._name, reason)

    def on_kicked(self, reason: object = None, *_: object) -> None:
        self._manager.mark_kicked(self._name, reason)

    def on_error(self, error: object) -> None:
        self._manager.mark_error(self._name, error)


def _env_options() -> CreateOptions:
    """Read connection defaults from MC_* environment variables.

    Blank values are skipped so an unfilled line in .env behaves the same as a
    missing one. A non-numeric MC_PORT is ignored rather than fatal — a typo
    there should surface as a connection failure, not a server crash.
    """
    options: CreateOptions = {}
    for env_name, key in _ENV_OPTION_KEYS.items():
        raw = (os.environ.get(env_name) or "").strip()
        if not raw:
            continue
        if key == "port":
            try:
                options[key] = int(raw)
            except ValueError:
                continue
        else:
            options[key] = raw
    return options


def _to_camel(snake: str) -> str:
    head, *tail = snake.split("_")
    return head + "".join(part.capitalize() for part in tail)


def _safe_call(fn: Any) -> Any:
    try:
        return fn()
    except Exception as exc:
        return {"error": str(exc)}


def _safe_str(value: object | None) -> str | None:
    if value is None:
        return None
    try:
        return str(value)
    except Exception:
        return "<unprintable>"


def _safe_float(value: object | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _has_pathfinder(bot: Bot) -> bool:
    try:
        getattr(bot, "pathfinder")
    except Exception:
        return False
    return True


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


manager = BotManager()

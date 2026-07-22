"""Logging for the control service: HTTP API, MCP tool calls, bot lifecycle.

Writes to stderr, and to a file as well when ``MINEAI_LOG_FILE`` is set. This is
the durable record; the Activity tab in the web UI is the live view of the same
events (see :mod:`event_log`).

Env knobs:
    MINEAI_LOG_LEVEL   DEBUG | INFO | WARNING | ERROR   (default INFO)
    MINEAI_LOG_FILE    path to append to               (default: stderr only)
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

LOGGER_NAME = "mineai"

# The pid is kept as a sanity check: there must only ever be one control
# service. Two pids in one log means a second instance got started somehow, and
# each would have its own bot list.
_FORMAT = "[mineai] %(asctime)s %(levelname)-5s pid=%(process)d %(name)s: %(message)s"
_DATEFMT = "%H:%M:%S"

# Substring match, so authServer/auth_server/MC_PASSWORD are all covered.
_SECRET_HINTS = ("password", "secret", "token", "apikey", "api_key")

_configured = False


def configure() -> None:
    """Attach handlers to the mineai logger. Safe to call more than once."""
    global _configured
    if _configured:
        return
    _configured = True

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(_level())
    # Don't hand records to the root logger: uvicorn and FastMCP configure their
    # own handlers and the records would be emitted twice.
    logger.propagate = False

    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    logger.addHandler(stderr_handler)

    if path := os.environ.get("MINEAI_LOG_FILE", "").strip():
        try:
            file_handler = logging.FileHandler(path, encoding="utf-8")
        except OSError as exc:
            logger.warning("cannot open MINEAI_LOG_FILE %s: %s", path, exc)
        else:
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)


def get_logger(component: str) -> logging.Logger:
    """Return the logger for one component, e.g. ``http`` or ``bots``."""
    configure()
    return logging.getLogger(f"{LOGGER_NAME}.{component}")


def _level() -> int:
    raw = os.environ.get("MINEAI_LOG_LEVEL", "INFO").strip().upper()
    return getattr(logging, raw, logging.INFO)


def redact(value: Any) -> Any:
    """Deep-copy ``value`` with secret-looking values replaced by ``***``.

    Applied to everything logged from a request body or bot options, so a
    password typed into the control UI never reaches a log file.
    """
    if isinstance(value, dict):
        return {
            key: "***"
            if any(hint in str(key).lower() for hint in _SECRET_HINTS)
            else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def summarize(value: Any, *, limit: int = 400) -> str:
    """Render a payload for one log line, trimmed so a big bot list stays readable."""
    text = repr(redact(value))
    if len(text) <= limit:
        return text
    return f"{text[:limit]}… (+{len(text) - limit} chars)"

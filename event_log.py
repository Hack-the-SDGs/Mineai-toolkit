"""In-memory activity log shared by the MCP middleware, the HTTP API, and the UI.

Everything the model does passes through here, so students can watch tool calls
arrive in real time. The log is deliberately bounded and in-memory: it is a
teaching view of the current session, not an audit trail.

Producers run on several threads (FastMCP's event loop, uvicorn's worker
threads, and JSPyBridge callback threads via ``bot_manager``), so appends take a
lock. Consumers poll :func:`since` rather than being pushed to — the SSE handler
turns that into a stream. Polling avoids bridging notifications from arbitrary
threads back into the event loop, which is the part that tends to deadlock.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import asdict, dataclass
from itertools import count
from threading import Lock
from typing import Any

from logging_setup import redact

# Roughly a full class session of activity. Old events are dropped silently.
MAX_EVENTS = 500

# Longest single value kept verbatim; beyond this the payload is truncated so a
# huge block scan can't push the whole timeline out of the ring buffer.
_MAX_VALUE_CHARS = 2000


@dataclass(frozen=True)
class Event:
    """One row in the activity timeline."""

    id: int
    timestamp: float
    source: str  # "model" | "human" | "system"
    kind: str  # "tool_call" | "http" | "bot"
    name: str
    arguments: Any = None
    result: Any = None
    duration_ms: float | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _truncate(value: Any) -> Any:
    """Trim oversized strings so one huge payload can't flush the ring buffer."""
    if isinstance(value, dict):
        return {key: _truncate(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_truncate(item) for item in value]
    if isinstance(value, str) and len(value) > _MAX_VALUE_CHARS:
        return value[:_MAX_VALUE_CHARS] + f"… (+{len(value) - _MAX_VALUE_CHARS} chars)"
    return value


def sanitize(value: Any) -> Any:
    """Blank out secrets, then truncate.

    Secret handling is shared with the file/stderr logs via
    :func:`logging_setup.redact` so the two can't drift apart. It matters here
    because the console posts real credentials to ``create_bot`` and this log is
    rendered in a browser tab a student may well be screen-sharing.
    """
    return _truncate(redact(value))


class EventLog:
    """Bounded, thread-safe ring buffer of :class:`Event`."""

    def __init__(self, maxlen: int = MAX_EVENTS) -> None:
        self._events: deque[Event] = deque(maxlen=maxlen)
        self._lock = Lock()
        self._ids = count(1)

    def append(
        self,
        *,
        source: str,
        kind: str,
        name: str,
        arguments: Any = None,
        result: Any = None,
        duration_ms: float | None = None,
        error: str | None = None,
    ) -> Event:
        """Record one event and return it."""
        event = Event(
            id=next(self._ids),
            timestamp=time.time(),
            source=source,
            kind=kind,
            name=name,
            arguments=sanitize(arguments),
            result=sanitize(result),
            duration_ms=duration_ms,
            error=error,
        )
        with self._lock:
            self._events.append(event)
        return event

    def since(self, event_id: int = 0) -> list[Event]:
        """Every event newer than ``event_id``, oldest first."""
        with self._lock:
            return [event for event in self._events if event.id > event_id]

    def recent(self, limit: int = 100) -> list[Event]:
        """The last ``limit`` events, oldest first."""
        with self._lock:
            events = list(self._events)
        return events[-limit:]

    def last_id(self) -> int:
        with self._lock:
            return self._events[-1].id if self._events else 0

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


log = EventLog()

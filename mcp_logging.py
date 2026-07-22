"""FastMCP middleware recording every tool call into the activity log.

One middleware covers both callers. The model reaches tools over HTTP at
``/mcp``; the web console reaches the same FastMCP instance through an
in-memory client. Both land in :meth:`ActivityMiddleware.on_call_tool`, so the
timeline shows them side by side — which is the whole point of the console.
"""

from __future__ import annotations

import contextvars
import time
from typing import Any

from fastmcp.server.middleware import Middleware

from event_log import log

# Who is calling. The HTTP transport leaves this at the default; the console
# handler sets it to "human" BEFORE opening its in-memory client.
#
# The ordering is not stylistic: the in-memory client copies the current context
# when it starts its server task, so a value set afterwards never reaches this
# middleware. See control_api.invoke_tool.
SOURCE: contextvars.ContextVar[str] = contextvars.ContextVar("source", default="model")


def _summarize(result: Any) -> Any:
    """Reduce a ToolResult to something JSON-friendly for the timeline."""
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        return structured

    content = getattr(result, "content", None) or []
    texts = [getattr(block, "text", None) for block in content]
    texts = [text for text in texts if text is not None]
    if not texts:
        return None
    return texts[0] if len(texts) == 1 else texts


class ActivityMiddleware(Middleware):
    """Append one ``tool_call`` event per invocation, success or failure."""

    async def on_call_tool(self, context, call_next):  # noqa: ANN001, ANN201
        source = SOURCE.get()
        name = context.message.name
        arguments = context.message.arguments or {}
        started = time.perf_counter()

        try:
            result = await call_next(context)
        except Exception as exc:
            log.append(
                source=source,
                kind="tool_call",
                name=name,
                arguments=arguments,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
                error=f"{type(exc).__name__}: {exc}",
            )
            raise

        log.append(
            source=source,
            kind="tool_call",
            name=name,
            arguments=arguments,
            result=_summarize(result),
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
        )
        return result

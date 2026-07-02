"""Build the FastMCP server and register every tool module."""

from __future__ import annotations

import os
import sys
import time
import webbrowser
from contextlib import asynccontextmanager
from threading import Thread

from fastmcp import FastMCP

from bot_manager import manager
from control_api import MineAIControlServer
from tools import interaction, lifecycle, movement, pathfinder, sensors


@asynccontextmanager
async def lifespan(_server: FastMCP):
    """Start the user-facing control UI and clean up bots on shutdown."""
    control = _start_control_server()
    try:
        yield
    finally:
        if control is not None:
            control.stop()
        manager.close_all()


def _start_control_server() -> MineAIControlServer | None:
    """Start the lifecycle control UI unless disabled, and open it once.

    Failing to bind the port is not fatal: in a multi-window setup another
    instance may already own it, so we log and keep the MCP server running.
    """
    if not _env_flag("MINEAI_CONTROL_API", default=True):
        return None

    host = os.environ.get("MINEAI_CONTROL_HOST", "127.0.0.1")
    port = int(os.environ.get("MINEAI_CONTROL_PORT", "8765"))

    try:
        control = MineAIControlServer(host, port)
    except OSError as exc:
        print(
            f"[mineai] control UI not started ({exc}); "
            f"another instance may already own http://{host}:{port}",
            file=sys.stderr,
        )
        return None

    control.start()
    url = f"http://{host}:{port}"
    print(f"[mineai] bot control UI: {url}", file=sys.stderr)
    if _env_flag("MINEAI_OPEN_UI", default=True):
        _open_browser_later(url)
    return control


def _open_browser_later(url: str) -> None:
    """Open the control UI in the default browser after the server is ready."""

    def _open() -> None:
        time.sleep(0.6)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    Thread(target=_open, daemon=True).start()


def _env_flag(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def init_server() -> FastMCP:
    """Create the mineai MCP server and all model-facing tools."""
    mcp_server = FastMCP(name="mineai", lifespan=lifespan)
    lifecycle.register(mcp_server)
    sensors.register(mcp_server)
    movement.register(mcp_server)
    interaction.register(mcp_server)
    pathfinder.register(mcp_server)
    return mcp_server

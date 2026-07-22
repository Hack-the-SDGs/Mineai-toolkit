"""Entry point: run the mineai control service (MCP + API + UI) over HTTP."""

from __future__ import annotations

import os
import sys
import webbrowser
from pathlib import Path
from threading import Thread

import uvicorn
from dotenv import load_dotenv

from logging_setup import configure as configure_logging
from server import MCP_PATH, build_app

# Pinned next to this file rather than discovered: the service may be launched
# from any cwd, and a relative search would pick up a different .env or none.
ENV_FILE = Path(__file__).with_name(".env")

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def _env_flag(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def _port_in_use(host: str, port: int) -> bool:
    """True when something already listens on ``host:port``."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex((host, port)) == 0


def _open_browser_later(url: str) -> None:
    """Open the control UI once uvicorn is accepting connections."""

    def _open() -> None:
        import time

        time.sleep(1.0)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    Thread(target=_open, daemon=True).start()


def main() -> None:
    """Start the control service."""
    load_dotenv(ENV_FILE)
    # After load_dotenv so MINEAI_LOG_LEVEL / MINEAI_LOG_FILE can live in .env.
    configure_logging()

    host = os.environ.get("MINEAI_CONTROL_HOST", DEFAULT_HOST)
    port = int(os.environ.get("MINEAI_CONTROL_PORT", str(DEFAULT_PORT)))
    url = f"http://{host}:{port}"

    print(f"[mineai] control UI:  {url}", file=sys.stderr)
    print(f"[mineai] MCP endpoint: {url}{MCP_PATH}", file=sys.stderr)
    print("[mineai] point opencode at the MCP endpoint with type 'remote'.", file=sys.stderr)

    # Checked before uvicorn starts: uvicorn logs its own bind failure and exits
    # without re-raising, so this is the only place a useful message fits. A
    # second instance would own a second, empty BotManager — the exact
    # split-state bug this architecture exists to prevent, so fail loudly.
    if _port_in_use(host, port):
        print(
            f"[mineai] {host}:{port} is already in use.\n"
            f"[mineai] the control service is probably already running — open "
            f"{url} instead of starting a second one.\n"
            f"[mineai] a second instance would have its own empty bot list.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    if _env_flag("MINEAI_OPEN_UI", default=True):
        _open_browser_later(url)

    uvicorn.run(build_app(), host=host, port=port, log_level="warning")


def stdio_removed() -> None:
    """Entry point for the retired `mineai-mcp` stdio command."""
    print(
        "mineai-mcp (stdio) has been replaced by the control service.\n"
        "\n"
        "  Run:  mineai-control\n"
        "\n"
        "Then point opencode at it as a remote MCP server:\n"
        '  "mineai-toolkit": { "type": "remote", '
        f'"url": "http://{DEFAULT_HOST}:{DEFAULT_PORT}{MCP_PATH}" }}\n'
        "\n"
        "Why: the stdio server ran one process per opencode window, each with "
        "its own bot list, so the model could not see bots created in the UI.",
        file=sys.stderr,
    )
    raise SystemExit(2)


if __name__ == "__main__":
    main()

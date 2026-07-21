"""Entry point: run the mineai MCP server over stdio."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from server import init_server

# Pinned next to this file rather than discovered: opencode launches the server
# with an arbitrary cwd, so a relative search would pick up a different .env
# (or none) depending on which folder the client happened to open.
ENV_FILE = Path(__file__).with_name(".env")


def main() -> None:
    """Start the MCP server (stdio transport)."""
    load_dotenv(ENV_FILE)
    init_server().run()


if __name__ == "__main__":
    main()

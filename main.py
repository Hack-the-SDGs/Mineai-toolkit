"""Entry point: run the mineai MCP server over stdio."""

from __future__ import annotations

from server import init_server


def main() -> None:
    """Start the MCP server (stdio transport)."""
    init_server().run()


if __name__ == "__main__":
    main()

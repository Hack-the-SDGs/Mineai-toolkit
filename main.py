"""Entry point: run the mineai MCP server over stdio."""

from __future__ import annotations

from dotenv import load_dotenv

from server import init_server


def main() -> None:
    load_dotenv()
    """Start the MCP server (stdio transport)."""
    init_server().run()


if __name__ == "__main__":
    main()

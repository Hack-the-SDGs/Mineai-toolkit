@echo off
REM Hack the SDGs 2026 -- start the mineai-toolkit MCP server.
REM Double-click this file, or run it from a terminal.
REM
REM uv run guarantees the project's environment (Python 3.14 + .venv from
REM `uv sync`), so this works regardless of how PyCharm is configured.

REM Run from this script's own folder, whatever the current directory is.
cd /d "%~dp0"

echo Starting mineai-toolkit MCP server...
echo Web UI + /mcp endpoint: http://127.0.0.1:8765
echo Press Ctrl+C to stop.
echo.

uv run mineai-control

REM Keep the window open after the server stops so errors stay readable.
echo.
echo Server stopped.
pause

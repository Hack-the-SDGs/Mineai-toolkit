"""Small JSON HTTP API for user-owned bot lifecycle controls."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.parse import unquote, urlparse

from bot_manager import manager

STATIC_DIR = Path(__file__).with_name("static")


class MineAIControlServer:
    """Background HTTP server wrapper used by the MCP process."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.host = host
        self.port = port
        self._server = ThreadingHTTPServer((host, port), _Handler)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)


class _Handler(BaseHTTPRequestHandler):
    server_version = "MineAIControl/0.1"

    def log_message(self, _format: str, *_args: object) -> None:
        """Keep stdout/stderr quiet for MCP stdio transports."""

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send_json({})

    def do_GET(self) -> None:  # noqa: N802
        try:
            path = self._path_parts()
            if path == [] or path == ["index.html"]:
                self._send_static("index.html")
                return
            if path == ["health"]:
                self._send_json(
                    {
                        "healthy": True,
                        "active_bot": manager.get_active_bot(),
                        "bots": manager.list_bots(),
                    },
                )
                return
            if path == ["bots"]:
                self._send_json({"bots": manager.list_bots()})
                return
            if len(path) == 3 and path[0] == "bots" and path[2] == "health":
                self._send_json(manager.check_bot_health(path[1]))
                return
            self._not_found()
        except Exception as exc:
            self._error(exc)

    def do_POST(self) -> None:  # noqa: N802
        try:
            path = self._path_parts()
            body = self._read_body()
            if path == ["bots"]:
                name = str(body.pop("name", "")).strip()
                account = _optional_str(body.pop("account", None))
                wait_spawn = bool(body.pop("wait_spawn", True))
                height = body.pop("height", None)
                nested_options = body.pop("options", {})
                if nested_options:
                    if not isinstance(nested_options, dict):
                        raise ValueError("options must be a JSON object.")
                    body = {**nested_options, **body}
                if height is not None:
                    height = int(height)
                self._send_json(
                    manager.create_bot(
                        name,
                        account=account,
                        wait_spawn=wait_spawn,
                        height=height,
                        **body,
                    ),
                    status=HTTPStatus.CREATED,
                )
                return
            if path == ["active_bot"]:
                name = str(body.get("name", "")).strip()
                self._send_json(manager.set_active_bot(name))
                return
            if len(path) == 3 and path[0] == "bots" and path[2] == "activate":
                self._send_json(manager.set_active_bot(path[1]))
                return
            self._not_found()
        except Exception as exc:
            self._error(exc)

    def do_DELETE(self) -> None:  # noqa: N802
        try:
            path = self._path_parts()
            if len(path) == 2 and path[0] == "bots":
                self._send_json(manager.close_bot(path[1]))
                return
            self._not_found()
        except Exception as exc:
            self._error(exc)

    def _path_parts(self) -> list[str]:
        path = urlparse(self.path).path.strip("/")
        if not path:
            return []
        return [unquote(part) for part in path.split("/")]

    def _read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("content-length", "0") or "0")
        if length <= 0:
            return {}
        data = self.rfile.read(length)
        if not data:
            return {}
        body = json.loads(data.decode("utf-8"))
        if not isinstance(body, dict):
            raise ValueError("JSON body must be an object.")
        return body

    def _send_json(
        self,
        payload: object,
        *,
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_static(self, filename: str) -> None:
        file_path = (STATIC_DIR / filename).resolve()
        if STATIC_DIR not in file_path.parents or not file_path.is_file():
            self._not_found()
            return
        data = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _not_found(self) -> None:
        self._send_json(
            {"error": "not_found", "message": f"No route for {self.path}"},
            status=HTTPStatus.NOT_FOUND,
        )

    def _error(self, exc: Exception) -> None:
        self._send_json(
            {"error": type(exc).__name__, "message": str(exc)},
            status=HTTPStatus.BAD_REQUEST,
        )


def _optional_str(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

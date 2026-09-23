from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import parse_qs, urlparse

from . import __version__
from .storage import Storage


ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/ramrattan-logo.png": ("ramrattan-logo.png", "image/png"),
}


class CompanionServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], storage: Storage):
        super().__init__(address, CompanionHandler)
        self.storage = storage


class CompanionHandler(BaseHTTPRequestHandler):
    server: CompanionServer

    def _headers(
        self, status: HTTPStatus, content_type: str, length: int
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'none'; "
            "frame-ancestors 'self'",
        )
        self.end_headers()

    def _send_bytes(
        self,
        body: bytes,
        content_type: str,
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        self._headers(status, content_type, len(body))
        self.wfile.write(body)

    def _send_json(
        self,
        value: object,
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        body = json.dumps(
            value, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        self._send_bytes(body, "application/json; charset=utf-8", status)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)

        if parsed.path == "/api/health":
            self._send_json(
                {
                    "status": "ok",
                    "version": __version__,
                    "measurements": self.server.storage.count(),
                    "last_recorded_at": self.server.storage.last_recorded_at(),
                }
            )
            return

        if parsed.path == "/api/results":
            raw_limit = parse_qs(parsed.query).get("limit", ["100"])[0]
            try:
                limit = int(raw_limit)
            except ValueError:
                self._send_json(
                    {"error": "limit must be an integer"},
                    HTTPStatus.BAD_REQUEST,
                )
                return
            self._send_json(
                {"records": self.server.storage.list_recent(limit)}
            )
            return

        asset = ASSETS.get(parsed.path)
        if asset is not None:
            filename, content_type = asset
            body = (
                files("pihole_speedtest")
                .joinpath("web", filename)
                .read_bytes()
            )
            self._send_bytes(body, content_type)
            return

        self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        self._send_json(
            {"error": "manual HTTP execution is not enabled"},
            HTTPStatus.METHOD_NOT_ALLOWED,
        )

    def log_message(self, format: str, *args: object) -> None:
        return


def serve(
    storage: Storage, host: str = "127.0.0.1", port: int = 8765
) -> None:
    storage.initialize()
    server = CompanionServer((host, port), storage)
    try:
        server.serve_forever()
    finally:
        server.server_close()

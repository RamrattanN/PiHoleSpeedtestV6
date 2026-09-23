from __future__ import annotations

import csv
import hmac
import io
import json
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from . import __version__
from .storage import Storage
from .settings import SettingsError, load_settings, save_settings


ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/ramrattan-logo.png": ("ramrattan-logo.png", "image/png"),
}


class CompanionServer(ThreadingHTTPServer):
    def __init__(
        self,
        address: tuple[str, int],
        storage: Storage,
        settings_file: Optional[Path] = None,
        admin_token_file: Optional[Path] = None,
        backup_directory: Optional[Path] = None,
    ):
        super().__init__(address, CompanionHandler)
        self.storage = storage
        self.settings_file = settings_file or storage.path.with_name("settings.json")
        self.admin_token_file = admin_token_file
        self.backup_directory = backup_directory or storage.path.parent / "backups"


class CompanionHandler(BaseHTTPRequestHandler):
    server: CompanionServer

    def _headers(
        self,
        status: HTTPStatus,
        content_type: str,
        length: int,
        extra_headers: Optional[dict[str, str]] = None,
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
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()

    def _send_bytes(
        self,
        body: bytes,
        content_type: str,
        status: HTTPStatus = HTTPStatus.OK,
        extra_headers: Optional[dict[str, str]] = None,
    ) -> None:
        self._headers(status, content_type, len(body), extra_headers)
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

        if parsed.path == "/api/settings":
            try:
                self._send_json(load_settings(self.server.settings_file))
            except SettingsError as exc:
                self._send_json(
                    {"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR
                )
            return

        if parsed.path == "/api/export.csv":
            output = io.StringIO(newline="")
            columns = (
                "recorded_at", "download_mbps", "upload_mbps",
                "latency_ms", "jitter_ms", "server_name", "server_id",
                "interface_name",
            )
            writer = csv.DictWriter(output, fieldnames=columns)
            writer.writeheader()
            writer.writerows(self.server.storage.list_all())
            self._send_bytes(
                output.getvalue().encode("utf-8"),
                "text/csv; charset=utf-8",
                extra_headers={
                    "Content-Disposition":
                        'attachment; filename="pihole-speedtest.csv"'
                },
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
        parsed = urlparse(self.path)
        if parsed.path not in ("/api/settings", "/api/reset"):
            self._send_json(
                {"error": "manual HTTP execution is not enabled"},
                HTTPStatus.METHOD_NOT_ALLOWED,
            )
            return

        if not self._authorized():
            self._send_json(
                {"error": "administrator authorization required"},
                HTTPStatus.FORBIDDEN,
            )
            return
        payload = self._read_json()
        if payload is None:
            return

        if parsed.path == "/api/settings":
            try:
                settings = save_settings(
                    self.server.settings_file,
                    int(payload.get("collection_interval_minutes", 0)),
                )
            except (SettingsError, TypeError, ValueError) as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            self._send_json(settings)
            return

        if payload.get("confirmation") != "RESET":
            self._send_json(
                {"error": "confirmation must be RESET"},
                HTTPStatus.BAD_REQUEST,
            )
            return
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = self.server.backup_directory / f"speedtest-before-reset-{timestamp}.db"
        deleted = self.server.storage.backup_and_reset(backup)
        self._send_json(
            {"status": "reset", "deleted": deleted, "backup": backup.name}
        )

    def _authorized(self) -> bool:
        token_file = self.server.admin_token_file
        if token_file is None or not token_file.is_file():
            return False
        expected = token_file.read_text(encoding="utf-8").strip()
        supplied = self.headers.get("Authorization", "")
        if not supplied.startswith("Bearer "):
            return False
        return bool(expected) and hmac.compare_digest(supplied[7:], expected)

    def _read_json(self) -> Optional[dict[str, object]]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > 4096:
            self._send_json({"error": "invalid request body"}, HTTPStatus.BAD_REQUEST)
            return None
        try:
            value = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json({"error": "invalid JSON"}, HTTPStatus.BAD_REQUEST)
            return None
        if not isinstance(value, dict):
            self._send_json({"error": "JSON object required"}, HTTPStatus.BAD_REQUEST)
            return None
        return value

    def do_PUT(self) -> None:  # noqa: N802
        self._send_json(
            {"error": "manual HTTP execution is not enabled"},
            HTTPStatus.METHOD_NOT_ALLOWED,
        )

    def log_message(self, format: str, *args: object) -> None:
        return


def serve(
    storage: Storage,
    host: str = "127.0.0.1",
    port: int = 8765,
    settings_file: Optional[Path] = None,
    admin_token_file: Optional[Path] = None,
    backup_directory: Optional[Path] = None,
) -> None:
    storage.initialize()
    server = CompanionServer(
        (host, port), storage, settings_file, admin_token_file, backup_directory
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()

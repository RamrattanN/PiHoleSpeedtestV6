from __future__ import annotations

import csv
import io
import json
import sqlite3
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from . import __version__
from .collector import CollectionError, collect
from .locking import CollectionLockedError, collection_lock
from .storage import Storage
from .settings import SettingsError, load_settings, save_settings


ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/ramrattan-logo.png": ("ramrattan-logo.png", "image/png"),
}


def validate_frame_ancestors(values: list[str]) -> tuple[str, ...]:
    validated = []
    for value in values:
        parsed = urlparse(value)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in ("", "/")
            or parsed.params
            or parsed.query
            or parsed.fragment
            or "\r" in value
            or "\n" in value
        ):
            raise ValueError(f"invalid frame ancestor origin: {value}")
        validated.append(value.rstrip("/"))
    return tuple(validated)


class CompanionServer(ThreadingHTTPServer):
    def __init__(
        self,
        address: tuple[str, int],
        storage: Storage,
        settings_file: Optional[Path] = None,
        backup_directory: Optional[Path] = None,
        frame_ancestors: Optional[list[str]] = None,
        collection_binary: Optional[str] = None,
        collection_lock_file: Optional[Path] = None,
        collection_timeout: int = 180,
    ):
        super().__init__(address, CompanionHandler)
        self.storage = storage
        self.settings_file = settings_file or storage.path.with_name("settings.json")
        self.backup_directory = backup_directory or storage.path.parent / "backups"
        self.frame_ancestors = validate_frame_ancestors(frame_ancestors or [])
        self.collection_binary = collection_binary
        self.collection_lock_file = collection_lock_file or storage.path.with_name(
            "collect.lock"
        )
        self.collection_timeout = collection_timeout
        self.collection_guard = threading.Lock()
        self.collection_status: dict[str, object] = {
            "state": "idle" if collection_binary else "unavailable",
            "message": (
                "Ready to run a speed test."
                if collection_binary
                else "Manual speed tests are not configured."
            ),
        }

    def start_collection(self) -> bool:
        with self.collection_guard:
            if self.collection_status["state"] == "running":
                return False
            if not self.collection_binary:
                return False
            self.collection_status = {
                "state": "running",
                "message": "Running an official Ookla speed test.",
            }
        threading.Thread(target=self._collect_once, daemon=True).start()
        return True

    def _collect_once(self) -> None:
        try:
            with collection_lock(self.collection_lock_file):
                measurement = collect(
                    self.collection_binary or "speedtest",
                    self.collection_timeout,
                )
                measurement_id = self.storage.insert(measurement)
        except (
            CollectionError,
            CollectionLockedError,
            OSError,
            sqlite3.Error,
        ) as exc:
            with self.collection_guard:
                self.collection_status = {
                    "state": "failed",
                    "message": str(exc),
                }
            return
        with self.collection_guard:
            self.collection_status = {
                "state": "succeeded",
                "message": "Speed test completed successfully.",
                "measurement_id": measurement_id,
                "recorded_at": measurement.recorded_at,
                "started_at": measurement.started_at,
                "completed_at": measurement.recorded_at,
            }

    def get_collection_status(self) -> dict[str, object]:
        with self.collection_guard:
            return dict(self.collection_status)


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
        frame_ancestors = " ".join(
            ("'self'", *self.server.frame_ancestors)
        )
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'none'; "
            f"frame-ancestors {frame_ancestors}",
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

        if parsed.path == "/api/collection-status":
            self._send_json(self.server.get_collection_status())
            return

        if parsed.path == "/api/export.csv":
            output = io.StringIO(newline="")
            columns = (
                "recorded_at", "download_mbps", "upload_mbps",
                "latency_ms", "jitter_ms", "server_name", "server_id",
                "interface_name", "started_at", "completed_at",
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
        if parsed.path not in ("/api/settings", "/api/reset", "/api/collect"):
            self._send_json(
                {"error": "manual HTTP execution is not enabled"},
                HTTPStatus.METHOD_NOT_ALLOWED,
            )
            return

        content_type = self.headers.get("Content-Type", "")
        if content_type.split(";", 1)[0].strip().lower() != "application/json":
            self._send_json(
                {"error": "Content-Type must be application/json"},
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            )
            return

        if parsed.path == "/api/collect":
            if not self.server.collection_binary:
                self._send_json(
                    {"error": "manual speed tests are not configured"},
                    HTTPStatus.SERVICE_UNAVAILABLE,
                )
                return
            if not self.server.start_collection():
                self._send_json(
                    {"error": "a speed test is already running"},
                    HTTPStatus.CONFLICT,
                )
                return
            self._send_json(
                {
                    "state": "running",
                    "message": "Running an official Ookla speed test.",
                },
                HTTPStatus.ACCEPTED,
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
    backup_directory: Optional[Path] = None,
    frame_ancestors: Optional[list[str]] = None,
    collection_binary: Optional[str] = None,
    collection_lock_file: Optional[Path] = None,
    collection_timeout: int = 180,
) -> None:
    storage.initialize()
    server = CompanionServer(
        (host, port), storage, settings_file,
        backup_directory, frame_ancestors, collection_binary,
        collection_lock_file, collection_timeout,
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from typing import Any, Optional

from .models import Measurement


class CollectionError(RuntimeError):
    """Raised when a speed test cannot produce a trustworthy measurement."""


def _mapping(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise CollectionError(f"Ookla result is missing the {key} object")
    return value


def _number(parent: dict[str, Any], key: str) -> float:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CollectionError(f"Ookla result has no numeric {key} value")
    value = float(value)
    if value < 0:
        raise CollectionError(f"Ookla result has a negative {key} value")
    return value


def parse_ookla_result(
    payload: str, recorded_at: Optional[str] = None
) -> Measurement:
    try:
        result = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise CollectionError("Ookla returned invalid JSON") from exc

    if not isinstance(result, dict):
        raise CollectionError("Ookla returned a non-object JSON result")

    download = _mapping(result, "download")
    upload = _mapping(result, "upload")
    ping = _mapping(result, "ping")
    server = _mapping(result, "server")
    interface = _mapping(result, "interface")

    download_mbps = (_number(download, "bandwidth") * 8) / 1_000_000
    upload_mbps = (_number(upload, "bandwidth") * 8) / 1_000_000
    latency_ms = _number(ping, "latency")
    jitter_ms = _number(ping, "jitter")

    timestamp = recorded_at or result.get("timestamp")
    if not isinstance(timestamp, str) or not timestamp.strip():
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    return Measurement(
        recorded_at=timestamp,
        download_mbps=round(download_mbps, 2),
        upload_mbps=round(upload_mbps, 2),
        latency_ms=round(latency_ms, 2),
        jitter_ms=round(jitter_ms, 2),
        server_name=str(server.get("name") or "Not available"),
        server_id=str(server.get("id") or ""),
        interface_name=str(interface.get("name") or "Not available"),
    )


def collect(
    binary: str = "speedtest", timeout_seconds: int = 180
) -> Measurement:
    command = [
        binary,
        "--accept-license",
        "--accept-gdpr",
        "--format=json",
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        raise CollectionError(f"Speedtest CLI not found: {binary}") from exc
    except subprocess.TimeoutExpired as exc:
        raise CollectionError(
            f"Speedtest exceeded the {timeout_seconds}-second timeout"
        ) from exc

    if completed.returncode != 0:
        detail = completed.stderr.strip() or "no error detail"
        raise CollectionError(
            f"Speedtest exited with {completed.returncode}: {detail}"
        )

    if not completed.stdout.strip():
        raise CollectionError("Speedtest produced no JSON output")

    return parse_ookla_result(completed.stdout)

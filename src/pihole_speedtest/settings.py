from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


ALLOWED_INTERVAL_MINUTES = (15, 30, 60, 120, 240, 360, 720, 1440)
DEFAULT_INTERVAL_MINUTES = 60


class SettingsError(ValueError):
    pass


def load_settings(path: Path) -> dict[str, int]:
    if not path.exists():
        return {"collection_interval_minutes": DEFAULT_INTERVAL_MINUTES}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        interval = int(value["collection_interval_minutes"])
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise SettingsError(f"invalid settings file: {exc}") from exc
    if interval not in ALLOWED_INTERVAL_MINUTES:
        raise SettingsError("unsupported collection interval")
    return {"collection_interval_minutes": interval}


def save_settings(path: Path, interval_minutes: int) -> dict[str, int]:
    interval = int(interval_minutes)
    if interval not in ALLOWED_INTERVAL_MINUTES:
        raise SettingsError("unsupported collection interval")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"collection_interval_minutes": interval}
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
            json.dump(payload, destination, separators=(",", ":"))
            destination.write("\n")
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
    return payload

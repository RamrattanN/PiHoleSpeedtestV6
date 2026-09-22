from __future__ import annotations

import csv
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Union

from .models import Measurement
from .storage import Storage


REQUIRED_COLUMNS = {
    "timestamp",
    "iso8601",
    "download_mbps",
    "upload_mbps",
    "latency_ms",
    "jitter_ms",
    "server",
    "interface",
}


class LegacyImportError(RuntimeError):
    """Raised when a legacy CSV cannot be safely interpreted."""


@dataclass(frozen=True)
class ImportIssue:
    line: int
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {"line": self.line, "reason": self.reason}


@dataclass(frozen=True)
class ImportReport:
    rows: int
    inserted: int
    duplicates: int
    rejected: int
    issues: List[ImportIssue]

    def to_dict(self) -> dict[str, object]:
        return {
            "rows": self.rows,
            "inserted": self.inserted,
            "duplicates": self.duplicates,
            "rejected": self.rejected,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def _number(row: dict[str, str], column: str) -> float:
    raw = (row.get(column) or "").strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise LegacyImportError(f"{column} is not numeric") from exc
    if not math.isfinite(value) or value < 0:
        raise LegacyImportError(f"{column} must be a finite non-negative value")
    return value


def _timestamp(row: dict[str, str]) -> str:
    raw_iso = (row.get("iso8601") or "").strip()
    try:
        parsed = datetime.fromisoformat(raw_iso.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LegacyImportError("iso8601 is invalid") from exc
    if parsed.tzinfo is None:
        raise LegacyImportError("iso8601 must include a timezone")

    raw_epoch = (row.get("timestamp") or "").strip()
    try:
        epoch = float(raw_epoch)
    except ValueError as exc:
        raise LegacyImportError("timestamp is not numeric") from exc
    if not math.isfinite(epoch):
        raise LegacyImportError("timestamp must be finite")
    if abs(parsed.timestamp() - epoch) > 1:
        raise LegacyImportError("timestamp and iso8601 do not match")

    return (
        parsed.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _measurement(row: dict[str, str]) -> Measurement:
    return Measurement(
        recorded_at=_timestamp(row),
        download_mbps=_number(row, "download_mbps"),
        upload_mbps=_number(row, "upload_mbps"),
        latency_ms=_number(row, "latency_ms"),
        jitter_ms=_number(row, "jitter_ms"),
        server_name=(row.get("server") or "").strip() or "Not available",
        server_id="",
        interface_name=(row.get("interface") or "").strip()
        or "Not available",
    )


def _same_measurement(
    existing: sqlite3.Row, measurement: Measurement
) -> bool:
    return all(
        (
            float(existing["download_mbps"]) == measurement.download_mbps,
            float(existing["upload_mbps"]) == measurement.upload_mbps,
            float(existing["latency_ms"]) == measurement.latency_ms,
            float(existing["jitter_ms"]) == measurement.jitter_ms,
            str(existing["server_name"]) == measurement.server_name,
            str(existing["server_id"]) == measurement.server_id,
            str(existing["interface_name"]) == measurement.interface_name,
        )
    )


def import_legacy_csv(
    source: Union[str, Path],
    storage: Storage,
    issue_limit: int = 20,
) -> ImportReport:
    source_path = Path(source).expanduser().resolve()
    if issue_limit < 0:
        raise ValueError("issue_limit must not be negative")

    storage.initialize()
    rows = inserted = duplicates = rejected = 0
    issues: List[ImportIssue] = []

    try:
        source_file = source_path.open(
            "r", encoding="utf-8-sig", newline=""
        )
    except OSError as exc:
        raise LegacyImportError(f"cannot read {source_path}: {exc}") from exc

    with source_file:
        reader = csv.DictReader(source_file)
        columns = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_COLUMNS - columns)
        if missing:
            raise LegacyImportError(
                "legacy CSV is missing columns: " + ", ".join(missing)
            )

        with storage.connect() as connection:
            for line_number, row in enumerate(reader, start=2):
                rows += 1
                try:
                    measurement = _measurement(row)
                    existing = connection.execute(
                        """
                        SELECT
                            download_mbps,
                            upload_mbps,
                            latency_ms,
                            jitter_ms,
                            server_name,
                            server_id,
                            interface_name
                        FROM measurements
                        WHERE recorded_at = ?
                        ORDER BY id
                        LIMIT 1
                        """,
                        (measurement.recorded_at,),
                    ).fetchone()

                    if existing is not None:
                        if _same_measurement(existing, measurement):
                            duplicates += 1
                            continue
                        raise LegacyImportError(
                            "recorded_at conflicts with an existing measurement"
                        )

                    connection.execute(
                        """
                        INSERT INTO measurements (
                            recorded_at,
                            download_mbps,
                            upload_mbps,
                            latency_ms,
                            jitter_ms,
                            server_name,
                            server_id,
                            interface_name
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            measurement.recorded_at,
                            measurement.download_mbps,
                            measurement.upload_mbps,
                            measurement.latency_ms,
                            measurement.jitter_ms,
                            measurement.server_name,
                            measurement.server_id,
                            measurement.interface_name,
                        ),
                    )
                    inserted += 1
                except LegacyImportError as exc:
                    rejected += 1
                    if len(issues) < issue_limit:
                        issues.append(ImportIssue(line_number, str(exc)))

    return ImportReport(rows, inserted, duplicates, rejected, issues)

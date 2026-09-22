from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional, Union

from .models import Measurement


SCHEMA = """
CREATE TABLE IF NOT EXISTS measurements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at TEXT NOT NULL,
    download_mbps REAL NOT NULL CHECK(download_mbps >= 0),
    upload_mbps REAL NOT NULL CHECK(upload_mbps >= 0),
    latency_ms REAL NOT NULL CHECK(latency_ms >= 0),
    jitter_ms REAL NOT NULL CHECK(jitter_ms >= 0),
    server_name TEXT NOT NULL,
    server_id TEXT NOT NULL,
    interface_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
    )
);
CREATE INDEX IF NOT EXISTS idx_measurements_recorded_at
    ON measurements(recorded_at DESC);
"""


class Storage:
    def __init__(self, database: Union[str, Path]):
        self.path = Path(database).expanduser().resolve()

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def insert(self, measurement: Measurement) -> int:
        self.initialize()
        with self.connect() as connection:
            cursor = connection.execute(
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
            return int(cursor.lastrowid)

    def list_recent(self, limit: int = 100) -> list[dict[str, object]]:
        self.initialize()
        bounded_limit = max(1, min(int(limit), 500))
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    recorded_at,
                    download_mbps,
                    upload_mbps,
                    latency_ms,
                    jitter_ms,
                    server_name,
                    server_id,
                    interface_name
                FROM measurements
                ORDER BY recorded_at DESC, id DESC
                LIMIT ?
                """,
                (bounded_limit,),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def count(self) -> int:
        self.initialize()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM measurements"
            ).fetchone()
        return int(row["total"])

    def last_recorded_at(self) -> Optional[str]:
        self.initialize()
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT recorded_at
                FROM measurements
                ORDER BY recorded_at DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
        return None if row is None else str(row["recorded_at"])

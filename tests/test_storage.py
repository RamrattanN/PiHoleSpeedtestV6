import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from pihole_speedtest.models import Measurement
from pihole_speedtest.storage import Storage


def measurement(recorded_at: str, download: float) -> Measurement:
    return Measurement(
        recorded_at=recorded_at,
        download_mbps=download,
        upload_mbps=20.0,
        latency_ms=10.0,
        jitter_ms=1.0,
        server_name="Example",
        server_id="42",
        interface_name="eth0",
    )


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.storage = Storage(
            Path(self.temporary.name) / "nested" / "speedtest.db"
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_initialization_is_idempotent(self):
        self.storage.initialize()
        self.storage.initialize()
        self.assertEqual(self.storage.count(), 0)

    def test_insert_and_chronological_query(self):
        self.storage.insert(measurement("2026-09-22T18:30:00Z", 120.0))
        self.storage.insert(measurement("2026-09-22T18:00:00Z", 100.0))

        records = self.storage.list_recent()
        self.assertEqual([row["download_mbps"] for row in records], [100, 120])
        self.assertEqual(self.storage.count(), 2)
        self.assertEqual(
            self.storage.last_recorded_at(), "2026-09-22T18:30:00Z"
        )

    def test_query_limit_is_bounded(self):
        for index in range(3):
            self.storage.insert(
                measurement(f"2026-09-22T18:0{index}:00Z", 100 + index)
            )
        self.assertEqual(len(self.storage.list_recent(2)), 2)
        self.assertEqual(len(self.storage.list_recent(0)), 1)

    def test_existing_database_keeps_history_and_null_start(self):
        self.storage.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.storage.path) as connection:
            connection.execute(
                "CREATE TABLE measurements (id INTEGER PRIMARY KEY, "
                "recorded_at TEXT NOT NULL, download_mbps REAL NOT NULL, "
                "upload_mbps REAL NOT NULL, latency_ms REAL NOT NULL, "
                "jitter_ms REAL NOT NULL, server_name TEXT NOT NULL, "
                "server_id TEXT NOT NULL, interface_name TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO measurements VALUES "
                "(1, '2026-09-22T18:00:20Z', 100, 20, 10, 1, 'Example', '42', 'eth0')"
            )
        self.storage.initialize()
        self.storage.initialize()
        original = self.storage.list_recent()[0]
        self.assertIsNone(original["started_at"])
        self.assertEqual(original["recorded_at"], original["completed_at"])
        self.assertEqual(original["download_mbps"], 100)
        self.assertEqual(self.storage.count(), 1)

        newer = measurement("2026-09-22T18:15:20Z", 120)
        self.storage.insert(replace(newer, started_at="2026-09-22T18:15:00Z"))
        records = self.storage.list_recent()
        self.assertEqual([row["started_at"] for row in records], [None, "2026-09-22T18:15:00Z"])
        self.assertEqual(records[-1]["completed_at"], "2026-09-22T18:15:20Z")
        self.assertEqual(self.storage.last_recorded_at(), "2026-09-22T18:15:20Z")

    def test_chart_history_is_sorted_by_start_but_schedule_uses_completion(self):
        self.storage.insert(replace(
            measurement("2026-09-22T18:25:00Z", 100),
            started_at="2026-09-22T18:00:00Z",
        ))
        self.storage.insert(replace(
            measurement("2026-09-22T18:20:00Z", 120),
            started_at="2026-09-22T18:15:00Z",
        ))
        self.assertEqual(
            [row["download_mbps"] for row in self.storage.list_recent()],
            [100, 120],
        )
        self.assertEqual(self.storage.last_recorded_at(), "2026-09-22T18:25:00Z")

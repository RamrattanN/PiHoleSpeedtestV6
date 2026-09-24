import tempfile
import unittest
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

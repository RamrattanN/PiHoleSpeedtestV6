import random
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from pihole_speedtest.cli import main
from pihole_speedtest.models import Measurement
from pihole_speedtest.storage import Storage


UTC = timezone.utc
QUARTER = timedelta(minutes=15)


def at(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def iso(moment):
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def measurement(recorded_at):
    return Measurement(
        recorded_at=recorded_at,
        download_mbps=320.0,
        upload_mbps=100.0,
        latency_ms=10.0,
        jitter_ms=1.0,
        server_name="Example",
        server_id="42",
        interface_name="eth0",
    )


class ScheduleSlotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.storage = Storage(Path(self.temporary.name) / "speedtest.db")

    def tearDown(self):
        self.temporary.cleanup()

    def record(self, moment):
        self.storage.insert(measurement(moment if isinstance(moment, str) else iso(moment)))

    def simulate(self, interval_minutes, hours=24, seed=6):
        """Run the quarter-hour timer with randomized delay and test duration."""
        rng = random.Random(seed)
        start = at("2026-09-25T00:00:00Z")
        recorded = []
        for tick in range(hours * 4):
            fired = start + tick * QUARTER + timedelta(seconds=rng.uniform(0, 60))
            if self.storage.collection_is_due(interval_minutes, now=fired):
                completed = fired + timedelta(seconds=rng.uniform(20, 60))
                self.record(completed)
                recorded.append(completed)
        return recorded

    def test_empty_history_is_due(self):
        self.assertTrue(self.storage.collection_is_due(15, now=at("2026-09-25T03:00:30Z")))

    def test_reproduces_rc1_acceptance_sequence(self):
        # rc.1: measurement at 02:31:10Z, next timer run at 02:45:23Z was "not due".
        self.record("2026-09-25T02:31:10Z")
        next_run = at("2026-09-25T02:45:23Z")

        self.assertLess(next_run - at("2026-09-25T02:31:10Z"), QUARTER)
        self.assertTrue(self.storage.collection_is_due(15, now=next_run))

    def test_next_quarter_hour_run_is_accepted_after_late_completion(self):
        slot = at("2026-09-25T10:00:00Z")
        for start_delay in range(0, 61, 5):
            for duration in range(20, 61, 5):
                for next_delay in range(0, 61, 5):
                    with self.subTest(start=start_delay, duration=duration, next=next_delay):
                        completed = slot + timedelta(seconds=start_delay + duration)
                        next_run = slot + QUARTER + timedelta(seconds=next_delay)
                        self.assertTrue(
                            Storage.collection_is_due(
                                _SingleRecord(completed), 15, now=next_run
                            )
                        )

    def test_randomized_day_collects_every_quarter_hour_without_skips(self):
        recorded = self.simulate(15)

        self.assertEqual(len(recorded), 96)
        # Completion spacing varies only by timer delay (0-60 s) and duration (20-60 s).
        spread = timedelta(seconds=100)
        gaps = [later - earlier for earlier, later in zip(recorded, recorded[1:])]
        self.assertTrue(all(QUARTER - spread <= gap <= QUARTER + spread for gap in gaps))

    def test_longer_intervals_collect_once_per_interval(self):
        for interval, expected in ((30, 48), (60, 24), (120, 12), (1440, 1)):
            with self.subTest(interval=interval):
                self.tearDown()
                self.setUp()
                recorded = self.simulate(interval)
                self.assertEqual(len(recorded), expected)
                slots = [int(moment.timestamp()) // (interval * 60) for moment in recorded]
                self.assertEqual(len(slots), len(set(slots)))

    def test_run_within_the_same_slot_is_skipped(self):
        self.record("2026-09-25T10:00:45Z")

        self.assertFalse(self.storage.collection_is_due(15, now=at("2026-09-25T10:14:59Z")))
        self.assertFalse(self.storage.collection_is_due(30, now=at("2026-09-25T10:29:59Z")))
        self.assertTrue(self.storage.collection_is_due(15, now=at("2026-09-25T10:15:00Z")))

    def test_repeated_timer_activation_in_one_slot_records_once(self):
        fired = at("2026-09-25T10:15:10Z")
        self.assertTrue(self.storage.collection_is_due(15, now=fired))
        self.record(fired + timedelta(seconds=35))

        self.assertFalse(self.storage.collection_is_due(15, now=fired + timedelta(seconds=40)))

    def test_manual_run_satisfies_its_slot_without_blocking_the_next(self):
        self.record("2026-09-25T10:07:30Z")

        self.assertFalse(self.storage.collection_is_due(15, now=at("2026-09-25T10:14:40Z")))
        self.assertTrue(self.storage.collection_is_due(15, now=at("2026-09-25T10:15:40Z")))

    def test_restart_after_outage_collects_immediately_then_resumes(self):
        self.record("2026-09-25T06:01:10Z")
        restart = at("2026-09-25T09:37:12Z")

        self.assertTrue(self.storage.collection_is_due(15, now=restart))
        self.record(restart + timedelta(seconds=30))
        self.assertFalse(self.storage.collection_is_due(15, now=at("2026-09-25T09:44:59Z")))
        self.assertTrue(self.storage.collection_is_due(15, now=at("2026-09-25T09:45:20Z")))

    def test_existing_history_formats_are_respected(self):
        for recorded, now, due in (
            ("2025-11-02T14:31:26.123456+00:00", "2025-11-02T14:44:10Z", False),
            ("2025-11-02T14:31:26.123456+00:00", "2025-11-02T14:45:10Z", True),
            ("2026-09-24T21:31:10-05:00", "2026-09-25T02:44:59Z", False),
            ("2026-09-24T21:31:10-05:00", "2026-09-25T02:45:01Z", True),
        ):
            with self.subTest(recorded=recorded, now=now):
                self.tearDown()
                self.setUp()
                for earlier in ("2024-01-01T00:00:00Z", "2025-06-01T12:05:00Z"):
                    self.record(earlier)
                self.record(recorded)
                self.assertEqual(self.storage.collection_is_due(15, now=at(now)), due)

    def test_future_timestamp_from_clock_skew_is_not_due(self):
        self.record("2999-01-01T00:00:00Z")

        self.assertFalse(self.storage.collection_is_due(15, now=at("2026-09-25T10:15:30Z")))


class _SingleRecord:
    """Minimal stand-in exposing only last_recorded_at for the timing grid."""

    def __init__(self, moment):
        self.value = iso(moment)

    def last_recorded_at(self):
        return self.value


class ScheduledCollectCommandTests(unittest.TestCase):
    @patch("pihole_speedtest.cli.collect")
    def test_scheduled_command_collects_in_a_new_slot_and_skips_a_repeat(self, collect_mock):
        now = datetime.now(UTC)
        slot_start = now - timedelta(seconds=int(now.timestamp()) % 900, microseconds=now.microsecond)
        collect_mock.return_value = measurement(iso(now))
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "speedtest.db"
            (Path(directory) / "settings.json").write_text(
                '{"collection_interval_minutes":15}\n', encoding="utf-8"
            )
            Storage(database).insert(measurement(iso(slot_start - timedelta(seconds=30))))
            command = ["collect", "--database", str(database), "--respect-schedule"]

            self.assertEqual(main(command), 0)
            self.assertEqual(collect_mock.call_count, 1)
            self.assertEqual(main(command), 0)
            self.assertEqual(collect_mock.call_count, 1)
            self.assertEqual(Storage(database).count(), 2)


if __name__ == "__main__":
    unittest.main()

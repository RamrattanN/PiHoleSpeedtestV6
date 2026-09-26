import unittest
from datetime import datetime, timezone

from pihole_speedtest.docker_scheduler import seconds_until_next_slot


class DockerSchedulerTests(unittest.TestCase):
    def test_next_quarter_hour_is_aligned_even_after_restart(self):
        for current, next_slot in (
            ("2026-09-26T10:01:00Z", "2026-09-26T10:15:00Z"),
            ("2026-09-26T10:15:00Z", "2026-09-26T10:30:00Z"),
            ("2026-09-26T10:29:59Z", "2026-09-26T10:30:00Z"),
        ):
            with self.subTest(current=current):
                start = datetime.fromisoformat(current.replace("Z", "+00:00"))
                end = datetime.fromisoformat(next_slot.replace("Z", "+00:00"))
                self.assertEqual(
                    seconds_until_next_slot(start.timestamp()),
                    (end - start).total_seconds(),
                )

    def test_fractional_seconds_still_wait_for_next_boundary(self):
        moment = datetime(2026, 9, 26, 10, 14, 59, 500000, timezone.utc)
        self.assertEqual(seconds_until_next_slot(moment.timestamp()), 0.5)


if __name__ == "__main__":
    unittest.main()

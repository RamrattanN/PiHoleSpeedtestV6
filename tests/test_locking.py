import tempfile
import unittest
from pathlib import Path

from pihole_speedtest.locking import (
    CollectionLockedError,
    collection_lock,
)


class LockingTests(unittest.TestCase):
    def test_second_collector_cannot_acquire_the_same_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            lock_file = Path(temporary) / "collect.lock"

            with collection_lock(lock_file):
                with self.assertRaisesRegex(
                    CollectionLockedError, "already running"
                ):
                    with collection_lock(lock_file):
                        self.fail("second lock acquisition unexpectedly passed")

            with collection_lock(lock_file):
                self.assertTrue(lock_file.exists())

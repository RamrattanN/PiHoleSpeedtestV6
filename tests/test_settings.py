import json
import tempfile
import unittest
from pathlib import Path

from pihole_speedtest.settings import SettingsError, load_settings, save_settings


class SettingsTests(unittest.TestCase):
    def test_default_and_atomic_save(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            self.assertEqual(load_settings(path)["collection_interval_minutes"], 60)
            save_settings(path, 720)
            self.assertEqual(load_settings(path)["collection_interval_minutes"], 720)
            self.assertEqual(json.loads(path.read_text())["collection_interval_minutes"], 720)

    def test_rejects_unsupported_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(SettingsError):
                save_settings(Path(directory) / "settings.json", 5)

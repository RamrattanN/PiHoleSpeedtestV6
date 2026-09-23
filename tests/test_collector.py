import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pihole_speedtest.collector import (
    CollectionError,
    collect,
    parse_ookla_result,
)
from pihole_speedtest.cli import main
from pihole_speedtest.models import Measurement
from pihole_speedtest.storage import Storage


VALID_RESULT = {
    "timestamp": "2026-09-22T18:00:00Z",
    "download": {"bandwidth": 12_500_000},
    "upload": {"bandwidth": 2_500_000},
    "ping": {"latency": 13.24, "jitter": 1.51},
    "server": {"id": 42, "name": "Example Server"},
    "interface": {"name": "eth0"},
}


class CollectorTests(unittest.TestCase):
    def test_parses_official_ookla_units(self):
        measurement = parse_ookla_result(json.dumps(VALID_RESULT))

        self.assertEqual(measurement.download_mbps, 100.0)
        self.assertEqual(measurement.upload_mbps, 20.0)
        self.assertEqual(measurement.latency_ms, 13.24)
        self.assertEqual(measurement.jitter_ms, 1.51)
        self.assertEqual(measurement.server_name, "Example Server")
        self.assertEqual(measurement.server_id, "42")
        self.assertEqual(measurement.interface_name, "eth0")

    def test_rejects_invalid_json(self):
        with self.assertRaisesRegex(CollectionError, "invalid JSON"):
            parse_ookla_result("not-json")

    def test_rejects_missing_measurement_fields(self):
        incomplete = dict(VALID_RESULT)
        incomplete.pop("download")
        with self.assertRaisesRegex(CollectionError, "download"):
            parse_ookla_result(json.dumps(incomplete))

    @patch("pihole_speedtest.collector.subprocess.run")
    def test_nonzero_process_does_not_parse_or_store(self, run):
        run.return_value = subprocess.CompletedProcess(
            args=["speedtest"], returncode=2, stdout="", stderr="failed"
        )
        with self.assertRaisesRegex(CollectionError, "exited with 2"):
            collect()

    @patch("pihole_speedtest.collector.subprocess.run")
    def test_collect_invokes_official_json_mode(self, run):
        run.return_value = subprocess.CompletedProcess(
            args=["speedtest"],
            returncode=0,
            stdout=json.dumps(VALID_RESULT),
            stderr="",
        )
        measurement = collect(timeout_seconds=45)
        self.assertEqual(measurement.download_mbps, 100.0)
        run.assert_called_once_with(
            [
                "speedtest",
                "--accept-license",
                "--accept-gdpr",
                "--format=json",
            ],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )

    @patch("pihole_speedtest.cli.collect")
    def test_schedule_check_skips_collection_that_is_not_due(self, collect_mock):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "speedtest.db"
            Storage(database).insert(
                Measurement(
                    recorded_at="2999-01-01T00:00:00Z",
                    download_mbps=100,
                    upload_mbps=20,
                    latency_ms=10,
                    jitter_ms=1,
                    server_name="Example",
                    server_id="42",
                    interface_name="eth0",
                )
            )
            status = main([
                "collect", "--database", str(database), "--respect-schedule"
            ])
        self.assertEqual(status, 0)
        collect_mock.assert_not_called()

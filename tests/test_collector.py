import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from pihole_speedtest.collector import (
    CollectionError,
    collect,
    default_route_interface,
    parse_ookla_result,
)
from pihole_speedtest.cli import main, scheduled_slot
from pihole_speedtest.models import Measurement
from pihole_speedtest.settings import save_settings
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

    @patch("pihole_speedtest.collector.subprocess.run")
    def test_collect_keeps_completion_and_captures_start_before_process(self, run):
        observed = []

        def finish(*args, **kwargs):
            observed.append(datetime.now(timezone.utc))
            return subprocess.CompletedProcess(
                args=args[0], returncode=0,
                stdout=json.dumps(VALID_RESULT), stderr="",
            )

        run.side_effect = finish
        measurement = collect()
        started = datetime.fromisoformat(measurement.started_at.replace("Z", "+00:00"))
        self.assertLessEqual(started, observed[0])
        self.assertEqual(measurement.recorded_at, VALID_RESULT["timestamp"])
        self.assertEqual(measurement.to_dict()["completed_at"], VALID_RESULT["timestamp"])

    @patch(
        "pihole_speedtest.collector.default_route_interface",
        return_value="eth0",
    )
    @patch("pihole_speedtest.collector.subprocess.run")
    def test_collect_uses_default_route_when_ookla_omits_interface(
        self, run, route_interface
    ):
        result = dict(VALID_RESULT)
        result["interface"] = {"internalIp": "192.0.2.14"}
        run.return_value = subprocess.CompletedProcess(
            args=["speedtest"],
            returncode=0,
            stdout=json.dumps(result),
            stderr="",
        )

        measurement = collect()

        self.assertEqual(measurement.interface_name, "eth0")
        route_interface.assert_called_once_with()

    def test_default_route_interface_reads_linux_route_table(self):
        route_table = """Iface Destination Gateway Flags RefCnt Use Metric Mask MTU Window IRTT
eth0 00000000 0102A8C0 0003 0 0 100 00000000 0 0 0
eth0 0002A8C0 00000000 0001 0 0 100 00FFFFFF 0 0 0
"""
        with tempfile.TemporaryDirectory() as directory:
            route_path = Path(directory) / "route"
            route_path.write_text(route_table, encoding="utf-8")

            self.assertEqual(default_route_interface(route_path), "eth0")

    def test_scheduled_collection_stores_slot_start_and_completion_separately(self):
        now = datetime(2026, 9, 22, 18, 15, 57, tzinfo=timezone.utc)
        self.assertEqual(scheduled_slot(now, 15), "2026-09-22T18:15:00Z")
        self.assertEqual(scheduled_slot(now, 30), "2026-09-22T18:00:00Z")
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "speedtest.db"
            save_settings(database.with_name("settings.json"), 15)
            with patch("pihole_speedtest.cli.datetime", wraps=datetime) as clock, \
                 patch("pihole_speedtest.cli.collect") as collector:
                clock.now.return_value = now
                collector.return_value = Measurement(
                    recorded_at="2026-09-22T18:16:20Z",
                    started_at="2026-09-22T18:15:59Z",
                    download_mbps=100, upload_mbps=20, latency_ms=10,
                    jitter_ms=1, server_name="Example", server_id="42",
                    interface_name="eth0",
                )
                self.assertEqual(main([
                    "collect", "--database", str(database), "--respect-schedule",
                ]), 0)
            row = Storage(database).list_recent()[0]
            self.assertEqual(row["scheduled_at"], "2026-09-22T18:15:00Z")
            self.assertEqual(row["started_at"], "2026-09-22T18:15:59Z")
            self.assertEqual(row["completed_at"], "2026-09-22T18:16:20Z")

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

import csv
import io
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from pihole_speedtest.models import Measurement
from pihole_speedtest.server import CompanionServer, validate_frame_ancestors
from pihole_speedtest.storage import Storage


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.storage = Storage(Path(self.temporary.name) / "speedtest.db")
        self.storage.insert(
            Measurement(
                recorded_at="2026-09-22T18:00:00Z",
                download_mbps=100.0,
                upload_mbps=20.0,
                latency_ms=10.0,
                jitter_ms=1.0,
                server_name="Example",
                server_id="42",
                interface_name="eth0",
            )
        )
        self.server = CompanionServer(("127.0.0.1", 0), self.storage)
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.thread.start()
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temporary.cleanup()

    def get_json(self, path):
        with urlopen(self.base_url + path, timeout=2) as response:
            return response, json.loads(response.read())

    def test_health(self):
        response, payload = self.get_json("/api/health")
        self.assertEqual(response.status, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["measurements"], 1)
        self.assertEqual(payload["last_recorded_at"], "2026-09-22T18:00:00Z")

    def test_results(self):
        _, payload = self.get_json("/api/results?limit=10")
        self.assertEqual(len(payload["records"]), 1)
        self.assertEqual(payload["records"][0]["download_mbps"], 100.0)

    def test_csv_export(self):
        with urlopen(self.base_url + "/api/export.csv", timeout=2) as response:
            body = response.read().decode("utf-8")
        self.assertIn("attachment; filename=\"pihole-speedtest.csv\"", response.headers["Content-Disposition"])
        self.assertIn("recorded_at,download_mbps", body)
        self.assertIn("2026-09-22T18:00:00Z,100.0,20.0", body)
        rows = list(csv.DictReader(io.StringIO(body)))
        self.assertEqual(rows[0]["started_at"], "")
        self.assertEqual(rows[0]["scheduled_at"], "")
        self.assertEqual(rows[0]["completed_at"], rows[0]["recorded_at"])

    def test_results_expose_both_timestamps_for_new_measurement(self):
        from dataclasses import replace
        self.storage.insert(replace(
            Measurement(
                recorded_at="2026-09-22T18:15:20Z", download_mbps=101,
                upload_mbps=20, latency_ms=10, jitter_ms=1,
                server_name="Example", server_id="42", interface_name="eth0",
            ), started_at="2026-09-22T18:15:07Z",
            scheduled_at="2026-09-22T18:15:00Z",
        ))
        _, payload = self.get_json("/api/results?limit=10")
        self.assertIsNone(payload["records"][0]["started_at"])
        self.assertEqual(payload["records"][1]["started_at"], "2026-09-22T18:15:07Z")
        self.assertEqual(payload["records"][1]["completed_at"], "2026-09-22T18:15:20Z")
        self.assertEqual(payload["records"][1]["scheduled_at"], "2026-09-22T18:15:00Z")
        with urlopen(self.base_url + "/api/export.csv", timeout=2) as response:
            rows = list(csv.DictReader(io.StringIO(response.read().decode("utf-8"))))
        self.assertEqual(rows[1]["scheduled_at"], "2026-09-22T18:15:00Z")
        self.assertEqual(rows[1]["started_at"], "2026-09-22T18:15:07Z")
        self.assertEqual(rows[1]["completed_at"], "2026-09-22T18:15:20Z")

    def post_json(self, path, payload):
        request = Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            return response, json.loads(response.read())

    def test_settings_update_does_not_require_token(self):
        _, payload = self.post_json(
            "/api/settings", {"collection_interval_minutes": 30}
        )
        self.assertEqual(payload["collection_interval_minutes"], 30)

    def test_writes_require_json_content_type(self):
        for path, body in (
            ("/api/settings", b'{"collection_interval_minutes":30}'),
            ("/api/reset", b'{"confirmation":"RESET"}'),
            ("/api/collect", b"{}"),
        ):
            with self.subTest(path=path):
                request = Request(
                    self.base_url + path,
                    data=body,
                    headers={"Content-Type": "text/plain"},
                    method="POST",
                )
                with self.assertRaises(HTTPError) as raised:
                    urlopen(request, timeout=2)
                self.assertEqual(raised.exception.code, 415)

    def test_reset_creates_backup_before_delete(self):
        _, payload = self.post_json("/api/reset", {"confirmation": "RESET"})
        self.assertEqual(payload["deleted"], 1)
        self.assertEqual(self.storage.count(), 0)
        self.assertTrue((Path(self.temporary.name) / "backups" / payload["backup"]).is_file())

    def test_assets_have_security_policy(self):
        with urlopen(self.base_url + "/", timeout=2) as response:
            body = response.read().decode("utf-8")
            self.assertIn("Pi-hole Speedtest", body)
            self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])

        with urlopen(self.base_url + "/ramrattan-logo.png") as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers["Content-Type"], "image/png")
            self.assertTrue(response.read().startswith(b"\x89PNG\r\n\x1a\n"))

    def test_explicit_frame_ancestor_is_added_to_security_policy(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.server = CompanionServer(
            ("127.0.0.1", 0),
            self.storage,
            frame_ancestors=["http://pihole.example.test"],
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.thread.start()
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"

        with urlopen(self.base_url + "/", timeout=2) as response:
            policy = response.headers["Content-Security-Policy"]
        self.assertIn(
            "frame-ancestors 'self' http://pihole.example.test",
            policy,
        )

    def test_frame_ancestor_rejects_non_origin_and_header_injection(self):
        for value in (
            "http://pihole.example.test/admin",
            "javascript:alert(1)",
            "http://example.test\r\nX-Test: unsafe",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_frame_ancestors([value])

    @patch("pihole_speedtest.server.collect")
    def test_manual_collection_runs_asynchronously_and_stores_result(self, run):
        run.return_value = Measurement(
            recorded_at="2026-09-23T02:15:00Z",
            download_mbps=320.0,
            upload_mbps=100.0,
            latency_ms=8.0,
            jitter_ms=1.5,
            server_name="Example",
            server_id="99",
            interface_name="eth0",
        )
        self.server.collection_binary = "/usr/bin/speedtest"
        _, started = self.post_json("/api/collect", {})
        self.assertEqual(started["state"], "running")

        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            _, status = self.get_json("/api/collection-status")
            if status["state"] != "running":
                break
            time.sleep(0.01)

        self.assertEqual(status["state"], "succeeded")
        self.assertEqual(self.storage.count(), 2)
        run.assert_called_once_with("/usr/bin/speedtest", 180)

    def test_manual_collection_refuses_overlap(self):
        self.server.collection_binary = "/usr/bin/speedtest"
        self.server.collection_status = {
            "state": "running",
            "message": "Running an official Ookla speed test.",
        }
        with self.assertRaises(HTTPError) as raised:
            self.post_json("/api/collect", {})
        self.assertEqual(raised.exception.code, 409)

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

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
        self.token_file = Path(self.temporary.name) / "admin.token"
        self.token_file.write_text("test-secret\n", encoding="utf-8")
        self.server = CompanionServer(
            ("127.0.0.1", 0), self.storage,
            admin_token_file=self.token_file,
        )
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

    def post_json(self, path, payload, token="test-secret"):
        request = Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            return response, json.loads(response.read())

    def test_settings_update_requires_token(self):
        request = Request(
            self.base_url + "/api/settings",
            data=b'{"collection_interval_minutes":30}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=2)
        self.assertEqual(raised.exception.code, 403)

        _, payload = self.post_json(
            "/api/settings", {"collection_interval_minutes": 30}
        )
        self.assertEqual(payload["collection_interval_minutes"], 30)

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
            frame_ancestors=["http://192.168.2.14"],
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
            "frame-ancestors 'self' http://192.168.2.14",
            policy,
        )

    def test_frame_ancestor_rejects_non_origin_and_header_injection(self):
        for value in (
            "http://192.168.2.14/admin",
            "javascript:alert(1)",
            "http://example.test\r\nX-Test: unsafe",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_frame_ancestors([value])

    def test_manual_http_execution_is_disabled(self):
        request = Request(
            self.base_url + "/api/run", data=b"{}", method="POST"
        )
        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=2)
        self.assertEqual(raised.exception.code, 405)

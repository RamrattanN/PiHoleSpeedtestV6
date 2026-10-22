import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pihole_speedtest.adapter import AdapterError, install_adapter, remove_adapter
from pihole_speedtest.adapter_reconcile import inspect_restored, prepare, recover
from pihole_speedtest.pihole_headers import allow_companion_frame

SIDEBAR = '<ul class="sidebar-menu">\n                <!-- Donate button -->\n</ul>\n'


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        self.web, self.data, self.backups = (
            root / x for x in ("admin", "data", "recovery")
        )
        self.sidebar = self.web / "scripts/lua/sidebar.lp"
        self.sidebar.parent.mkdir(parents=True)
        self.sidebar.write_text(SIDEBAR)
        self.data.mkdir()
        self.url = "http://pihole.example.test:8765"
        self.origin = "http://pihole.example.test"
        self.old = install_adapter(self.web, "v6.6", self.url, self.origin, self.backups)
        before = ["Content-Security-Policy: default-src 'self'"]
        for name, content in (
            ("pihole-web-headers.before.json", json.dumps(before)),
            (
                "pihole-web-headers.installed.json",
                json.dumps(allow_companion_frame(before, self.url)),
            ),
            ("install-manifest.before.txt", "pihole_adapter_installed=false\n"),
            ("collection-manifest.before.txt", "pihole_adapter_installed=false\n"),
        ):
            (self.old.parent / name).write_text(content)
        for name in ("install-manifest.txt", "collection-manifest.txt"):
            (self.data / name).write_text(
                f"source_commit={'a' * 40}\npihole_adapter_installed=true\npihole_adapter_manifest={self.old}\n"
            )
        self.options = {
            "uid": os.getuid(),
            "approved": hashlib.sha256(SIDEBAR.encode()).hexdigest(),
        }
        self.args = self.data, self.backups, self.web
        remove_adapter(self.old)

    def check(self):
        return inspect_restored(*self.args, **self.options)

    def test_restored_state_reconciles_without_touching_user_data_or_history(self):
        for name in ("speedtest.db", "settings.json", "tls.pem"):
            (self.data / name).write_bytes(b"preserved bytes")
        historical = {p: p.read_bytes() for p in self.old.parent.iterdir()}
        journal = prepare(*self.args, **self.options)
        for name in ("install-manifest.txt", "collection-manifest.txt"):
            self.assertIn(
                "pihole_adapter_installed=false", (self.data / name).read_text()
            )
            self.assertTrue((journal / name).is_file())
        self.assertTrue((journal / "reconciliation.json").is_file())
        for path, contents in historical.items():
            self.assertEqual(path.read_bytes(), contents)
        for name in ("speedtest.db", "settings.json", "tls.pem"):
            self.assertEqual((self.data / name).read_bytes(), b"preserved bytes")
        new = install_adapter(self.web, "v6.6", self.url, self.origin, self.backups)
        self.assertNotEqual(new, self.old)
        remove_adapter(new)
        self.assertEqual(self.sidebar.read_text(), SIDEBAR)

    def test_healthy_installed_adapter_is_never_reconciled(self):
        self.old = install_adapter(self.web, "v6.6", self.url, self.origin, self.backups)
        for name in ("install-manifest.txt", "collection-manifest.txt"):
            (self.data / name).write_text(
                f"pihole_adapter_installed=true\npihole_adapter_manifest={self.old}\n"
            )
        records = {p: p.read_bytes() for p in self.data.iterdir()}
        recovery = sorted(self.backups.iterdir())
        with self.assertRaisesRegex(AdapterError, "fully restored"):
            prepare(*self.args, **self.options)
        self.assertEqual({p: p.read_bytes() for p in self.data.iterdir()}, records)
        self.assertEqual(sorted(self.backups.iterdir()), recovery)

    def test_unknown_sidebar_is_refused(self):
        self.sidebar.write_text(SIDEBAR + "custom")
        with self.assertRaisesRegex(AdapterError, "fully restored"):
            self.check()

    def test_either_page_present_or_dangling_symlink_is_refused(self):
        for name in ("speedtest.lp", "speedtest-setup.lp"):
            page = self.web / name
            for symlink in (False, True):
                with self.subTest(name=name, symlink=symlink):
                    if symlink:
                        page.symlink_to(self.web / "missing")
                    else:
                        page.write_text("unexpected content")
                    with self.assertRaisesRegex(AdapterError, "partial state"):
                        self.check()
                    page.unlink()

    def test_missing_malformed_and_unsafe_recovery_manifest(self):
        original = self.old.read_bytes()
        for content in ("{", "{}", json.dumps({"schema": 999})):
            self.old.write_text(content)
            with self.assertRaises((AdapterError, ValueError, KeyError)):
                self.check()
        self.old.unlink()
        with self.assertRaises(OSError):
            self.check()
        other = self.old.with_name("other.json")
        other.write_bytes(original)
        self.old.symlink_to(other)
        with self.assertRaisesRegex(AdapterError, "symlink"):
            self.check()

    def test_unsafe_recorded_paths_or_checksums_are_refused(self):
        original = self.old.read_text()
        for field, value in (
            ("path", "/tmp/other"),
            ("backup", "/tmp/backup"),
            ("before_sha256", "0" * 64),
            ("installed_sha256", "0" * 64),
        ):
            manifest = json.loads(original)
            manifest["sidebar"][field] = value
            self.old.write_text(json.dumps(manifest))
            with self.assertRaises(AdapterError):
                self.check()

    def test_missing_backup_or_header_evidence_is_refused(self):
        for name in ("sidebar.lp.before", "pihole-web-headers.before.json"):
            path = self.old.with_name(name)
            contents = path.read_bytes()
            path.unlink()
            with self.assertRaises(OSError):
                self.check()
            path.write_bytes(contents)

    def test_untrusted_permissions_and_owner_are_refused(self):
        self.old.chmod(0o666)
        with self.assertRaisesRegex(AdapterError, "permissions"):
            self.check()
        self.old.chmod(0o600)
        with self.assertRaisesRegex(AdapterError, "owner"):
            inspect_restored(
                *self.args, uid=os.getuid() + 1, approved=self.options["approved"]
            )

    def test_duplicate_or_disagreeing_deployment_records_are_refused(self):
        state = self.data / "collection-manifest.txt"
        state.write_text(state.read_text() + "pihole_adapter_installed=true\n")
        with self.assertRaisesRegex(AdapterError, "duplicate"):
            self.check()
        state.write_text(
            "pihole_adapter_installed=true\npihole_adapter_manifest=/unsafe\n"
        )
        with self.assertRaisesRegex(AdapterError, "disagree"):
            self.check()

    def test_interruption_between_metadata_writes_can_recover_and_retry(self):
        from pihole_speedtest.adapter_reconcile import _write_atomic

        def interrupt(path, text):
            if path == self.data / "install-manifest.txt":
                raise OSError("simulated power loss")
            _write_atomic(path, text)

        with (
            patch(
                "pihole_speedtest.adapter_reconcile._write_atomic",
                side_effect=interrupt,
            ),
            self.assertRaisesRegex(OSError, "power loss"),
        ):
            prepare(*self.args, **self.options)
        with self.assertRaisesRegex(AdapterError, "interrupted reconciliation"):
            self.check()
        journal = recover(*self.args, **self.options)
        self.assertTrue((journal / "recovered.json").exists())
        self.assertEqual(self.check(), self.old)
        prepare(*self.args, **self.options)

    def test_install_failure_retains_journal_and_recovery_restores_stale_record(self):
        prepare(*self.args, **self.options)
        with (
            patch(
                "pihole_speedtest.adapter._write_atomic",
                side_effect=OSError("disk full"),
            ),
            self.assertRaises(OSError),
        ):
            install_adapter(self.web, "v6.6", self.url, self.origin, self.backups)
        self.assertEqual(self.sidebar.read_text(), SIDEBAR)
        recover(*self.args, **self.options)
        self.assertEqual(self.check(), self.old)

    def test_recovery_never_overwrites_changed_web_or_deployment_state(self):
        prepare(*self.args, **self.options)
        self.sidebar.write_text("custom")
        with self.assertRaises(AdapterError):
            recover(*self.args, **self.options)
        self.sidebar.write_text(SIDEBAR)
        state = self.data / "install-manifest.txt"
        state.write_text(state.read_text() + "unexpected=change\n")
        with self.assertRaisesRegex(AdapterError, "outside reconciliation"):
            recover(*self.args, **self.options)

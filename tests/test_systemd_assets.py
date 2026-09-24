import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SYSTEMD = ROOT / "deploy" / "systemd"
INSTALLER = ROOT / "scripts" / "install_companion_dashboard.sh"
REMOVER = ROOT / "scripts" / "remove_companion_dashboard.sh"
COLLECTION_UPGRADER = ROOT / "scripts" / "upgrade_and_enable_collection.sh"
KEYLESS_UPGRADER = ROOT / "scripts" / "upgrade_remove_administrator_key.sh"
COMPANION_UPGRADER = ROOT / "scripts" / "upgrade_companion.sh"
ADAPTER_INSTALLER = ROOT / "scripts" / "install_pihole_adapter.sh"
ADAPTER_REMOVER = ROOT / "scripts" / "remove_pihole_adapter.sh"


class SystemdAssetTests(unittest.TestCase):
    def read(self, name):
        return (SYSTEMD / name).read_text(encoding="utf-8")

    def test_dashboard_runs_unprivileged_on_companion_port(self):
        unit = self.read("pihole-speedtest-dashboard.service")

        self.assertIn("User=pihole-speedtest", unit)
        self.assertIn("--host 0.0.0.0 --port 8765", unit)
        self.assertIn("Restart=on-failure", unit)
        self.assertIn("NoNewPrivileges=true", unit)
        self.assertIn(
            "EnvironmentFile=-/etc/default/pihole-speedtest-v6",
            unit,
        )
        self.assertIn("--collection-binary /usr/bin/speedtest", unit)
        self.assertIn(
            "--collection-lock-file /var/lib/pihole-speedtest/collect.lock",
            unit,
        )

    def test_collection_uses_official_cli_and_lock(self):
        unit = self.read("pihole-speedtest-collect.service")

        self.assertIn("--binary /usr/bin/speedtest", unit)
        self.assertIn("--lock-file /var/lib/pihole-speedtest/collect.lock", unit)
        self.assertIn("User=pihole-speedtest", unit)

    def test_timer_is_persistent_and_conservative(self):
        timer = self.read("pihole-speedtest-collect.timer")

        self.assertIn("OnCalendar=*:00/15", timer)
        self.assertIn("RandomizedDelaySec=60", timer)
        self.assertIn("Persistent=true", timer)
        service = self.read("pihole-speedtest-collect.service")
        self.assertIn("--respect-schedule", service)
        self.assertIn("--settings-file /var/lib/pihole-speedtest/settings.json", service)

    def test_units_do_not_modify_pihole_paths(self):
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(SYSTEMD.iterdir())
        )

        self.assertNotIn("/etc/pihole", combined)
        self.assertNotIn("/var/www/html", combined)

    def test_dashboard_only_installer_preserves_phase_boundaries(self):
        installer = INSTALLER.read_text(encoding="utf-8")

        self.assertIn("--legacy-csv", installer)
        self.assertIn("--expected-commit", installer)
        self.assertIn("Source worktree has tracked changes", installer)
        self.assertIn("PRAGMA integrity_check", installer)
        self.assertIn("expected_count", installer)
        self.assertIn("systemctl enable --now", installer)
        self.assertNotIn("pihole-speedtest-collect.timer", installer)
        self.assertNotIn("adapter-install", installer)
        self.assertIn("Collection timer: disabled", installer)
        self.assertIn("Pi-hole sidebar adapter: not installed", installer)

    def test_dashboard_only_removal_preserves_data_and_phase_boundaries(self):
        remover = REMOVER.read_text(encoding="utf-8")

        self.assertIn("--expected-commit", remover)
        self.assertIn('mv "$data_dir" "$recovery_dir/data"', remover)
        self.assertIn("pihole-speedtest-collect.timer", remover)
        self.assertIn("refuses to continue", remover)
        self.assertNotIn("/var/www/html", remover)
        self.assertNotIn("/etc/pihole", remover)
        self.assertIn("Pi-hole web files were not modified", remover)

    def test_collection_upgrade_is_guarded_and_keeps_adapter_disabled(self):
        upgrader = COLLECTION_UPGRADER.read_text(encoding="utf-8")

        self.assertIn("--expected-source-commit", upgrader)
        self.assertIn("--expected-installed-commit", upgrader)
        self.assertIn("speedtest.before.db", upgrader)
        self.assertIn("-m pip wheel", upgrader)
        self.assertNotIn("pihole-speedtest.next", upgrader)
        self.assertIn("PRAGMA integrity_check", upgrader)
        self.assertIn('"http://127.0.0.1:8765/api/collect"', upgrader)
        self.assertIn('systemctl enable --now "$timer_unit"', upgrader)
        self.assertIn("Any successfully completed measurement", upgrader)
        self.assertNotIn("adapter-install", upgrader)
        self.assertNotIn("/var/www/html", upgrader)

    def test_keyless_upgrade_is_guarded_and_preserves_collection(self):
        upgrader = KEYLESS_UPGRADER.read_text(encoding="utf-8")

        self.assertIn("--expected-source-commit", upgrader)
        self.assertIn("--expected-installed-commit", upgrader)
        self.assertIn("speedtest.before.db", upgrader)
        self.assertIn("PRAGMA integrity_check", upgrader)
        self.assertIn("admin.token.before", upgrader)
        self.assertIn('rm -f -- "$token_path"', upgrader)
        self.assertIn('systemctl stop "$timer_unit"', upgrader)
        self.assertIn('systemctl start "$timer_unit"', upgrader)
        self.assertIn('"http://127.0.0.1:8765/api/collect"', upgrader)
        self.assertNotIn("Authorization", upgrader)
        self.assertNotIn("adapter-install", upgrader)
        self.assertNotIn("/var/www/html", upgrader)

    def test_dashboard_service_does_not_require_administrator_token(self):
        unit = self.read("pihole-speedtest-dashboard.service")

        self.assertNotIn("admin-token-file", unit)
        self.assertNotIn("admin.token", unit)

    def test_companion_upgrade_preserves_data_schedule_and_adapter_state(self):
        upgrader = COMPANION_UPGRADER.read_text(encoding="utf-8")

        self.assertIn("--expected-source-commit", upgrader)
        self.assertIn("--expected-installed-commit", upgrader)
        self.assertIn("speedtest.before.db", upgrader)
        self.assertIn("PRAGMA integrity_check", upgrader)
        self.assertIn('systemctl stop "$timer_unit"', upgrader)
        self.assertIn('systemctl start "$timer_unit"', upgrader)
        self.assertIn('id=\"history-tooltip\"', upgrader)
        self.assertIn("collapsible Setup markup is still present", upgrader)
        self.assertNotIn("adapter-install", upgrader)
        self.assertNotIn("/var/www/html", upgrader)
        self.assertIn("pihole_adapter_manifest", upgrader)
        self.assertIn("Installed adapter sidebar no longer matches", upgrader)

    def test_adapter_installation_is_guarded_and_records_recovery_state(self):
        installer = ADAPTER_INSTALLER.read_text(encoding="utf-8")

        self.assertIn("--expected-source-commit", installer)
        self.assertIn("--expected-installed-commit", installer)
        self.assertIn("83943cbdf5258fe43e819108a5135e070", installer)
        self.assertIn("installed_web_version", installer)
        self.assertIn('!= "v6.6"', installer)
        self.assertIn("--pihole-origin", installer)
        self.assertIn("frame-ancestors 'self' $pihole_origin", installer)
        self.assertIn("frame-src $companion_url", installer)
        self.assertIn("pihole-web-headers.before.json", installer)
        self.assertIn("pihole-FTL --config webserver.headers", installer)
        self.assertIn("adapter-install", installer)
        self.assertIn("pihole_adapter_installed=true", installer)
        self.assertIn("pihole_adapter_manifest=", installer)
        self.assertIn("adapter-remove", installer)
        self.assertNotIn("192.168.", installer)

    def test_adapter_removal_uses_verified_manifest_and_records_absence(self):
        remover = ADAPTER_REMOVER.read_text(encoding="utf-8")

        self.assertIn("pihole_adapter_installed", remover)
        self.assertIn("pihole_adapter_manifest", remover)
        self.assertIn("adapter-remove", remover)
        self.assertIn("pihole-web-headers.installed.json", remover)
        self.assertIn("pihole-FTL --config webserver.headers", remover)
        self.assertIn("refusing to overwrite them", remover)
        self.assertIn("pihole_adapter_installed=false", remover)

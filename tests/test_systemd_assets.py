import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SYSTEMD = ROOT / "deploy" / "systemd"
INSTALLER = ROOT / "scripts" / "install_companion_dashboard.sh"
REMOVER = ROOT / "scripts" / "remove_companion_dashboard.sh"


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

    def test_collection_uses_official_cli_and_lock(self):
        unit = self.read("pihole-speedtest-collect.service")

        self.assertIn("--binary /usr/bin/speedtest", unit)
        self.assertIn("--lock-file /run/pihole-speedtest/collect.lock", unit)
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

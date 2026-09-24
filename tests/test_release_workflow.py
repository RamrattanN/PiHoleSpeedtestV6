import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
INSTALLER = SCRIPTS / "install_release.sh"
UNINSTALLER = SCRIPTS / "uninstall_release.sh"
PURGER = SCRIPTS / "purge_preserved_data.sh"
ADAPTER_INSTALLER = SCRIPTS / "install_pihole_adapter.sh"
BUILDER = SCRIPTS / "build_release_assets.sh"
RENDERER = SCRIPTS / "render_release_bootstrap.sh"
BOOTSTRAP = ROOT / "release" / "bootstrap.template.sh"


class ReleaseWorkflowTests(unittest.TestCase):
    def read(self, path):
        return path.read_text(encoding="utf-8")

    def test_release_scripts_have_valid_bash_syntax(self):
        scripts = [
            INSTALLER,
            UNINSTALLER,
            PURGER,
            BUILDER,
            RENDERER,
            BOOTSTRAP,
        ]
        subprocess.run(["bash", "-n", *map(str, scripts)], check=True)

    def test_bootstrap_verifies_bundle_before_privileged_execution(self):
        bootstrap = self.read(BOOTSTRAP)

        self.assertIn("raw.githubusercontent.com/${repository}/${asset_commit}", bootstrap)
        self.assertIn("--proto '=https' --tlsv1.2", bootstrap)
        self.assertIn("sha256sum --check --status", bootstrap)
        self.assertLess(bootstrap.index("sha256sum --check"), bootstrap.index("sudo bash"))
        self.assertNotIn("curl |", bootstrap)
        self.assertNotIn("curl -s |", bootstrap)
        self.assertIn("release/SOURCE-COMMIT", bootstrap)
        self.assertIn("hostname awk sed", bootstrap)
        self.assertIn("/var/lib/pihole-speedtest/install-manifest.txt", bootstrap)
        self.assertIn('--expected-installed-commit "$installed_commit"', bootstrap)
        self.assertIn("Installed companion commit could not be verified", bootstrap)

    def test_bootstrap_uninstalls_the_verified_installed_version(self):
        bootstrap = self.read(BOOTSTRAP)

        self.assertIn("read_installed_commit()", bootstrap)
        self.assertIn("Installed companion manifest could not be found", bootstrap)
        self.assertIn('installed_commit="$(read_installed_commit)"', bootstrap)
        self.assertIn('--expected-commit "$installed_commit"', bootstrap)
        self.assertNotIn('--expected-commit "$source_commit"', bootstrap)

    def test_install_fails_closed_and_keeps_adapter_separate(self):
        installer = self.read(INSTALLER)

        self.assertIn("Unsupported architecture", installer)
        self.assertIn("Python 3.9 or newer", installer)
        self.assertIn("Pi-hole Core v6 is required", installer)
        self.assertIn("official Ookla CLI", installer)
        self.assertIn("Source worktree has tracked changes", self.read(BUILDER))
        self.assertIn("User data was preserved", installer)
        self.assertIn('systemctl enable --now "$timer_unit"', installer)
        self.assertIn("Pi-hole sidebar adapter: not installed", installer)
        self.assertNotIn("adapter-install", installer)
        self.assertNotIn("/var/www/html", installer)

    def test_install_builds_outside_the_unprivileged_bootstrap_workspace(self):
        installer = self.read(INSTALLER)

        self.assertIn("mktemp -d /var/tmp/pihole-speedtest-package.XXXXXX", installer)
        self.assertIn('cp -a "$source_root/." "$package_source/"', installer)
        self.assertIn('pip install "$package_source"', installer)
        self.assertIn('rm -rf -- "$package_source"', installer)
        self.assertNotIn('pip install "$source_root"', installer)

    def test_uninstall_preserves_data_and_refuses_installed_adapter(self):
        uninstaller = self.read(UNINSTALLER)

        self.assertIn("Remove the Pi-hole sidebar adapter", uninstaller)
        self.assertIn("PRAGMA integrity_check", uninstaller)
        self.assertIn("source.backup(destination)", uninstaller)
        self.assertIn("data_preserved=true", uninstaller)
        self.assertNotIn('rm -rf -- "$data_dir"', uninstaller)
        self.assertNotIn("/var/www/html", uninstaller)

    def test_purge_is_separate_and_requires_exact_confirmation(self):
        purger = self.read(PURGER)

        self.assertIn('required_confirmation="DELETE /var/lib/pihole-speedtest"', purger)
        self.assertIn("Exact purge confirmation", purger)
        self.assertIn("Uninstall before purging data", purger)
        self.assertIn('rm -rf -- "$data_dir"', purger)

    def test_reinstall_reuses_preserved_history_and_settings(self):
        installer = self.read(INSTALLER)

        self.assertIn("uninstall or failed-install marker", installer)
        self.assertIn("failed_install_at", installer)
        self.assertIn("Preserved SQLite database failed integrity check", installer)
        self.assertIn("Preserved settings contain an unsupported collection interval", installer)
        self.assertNotIn('rm -rf -- "$data_dir"', installer)

    def test_adapter_accepts_only_git_or_verified_release_source(self):
        installer = self.read(ADAPTER_INSTALLER)

        self.assertIn("release/SOURCE-COMMIT", installer)
        self.assertIn('if [ -d "$source_root/.git" ]', installer)
        self.assertIn("Source commit does not match", installer)

    def test_builder_creates_deterministic_checksum_asset(self):
        builder = self.read(BUILDER)

        self.assertIn("--sort=name", builder)
        self.assertIn("--mtime='UTC 1970-01-01'", builder)
        self.assertIn("gzip -n", builder)
        self.assertIn("sha256sum", builder)
        self.assertIn("release/SOURCE-COMMIT", builder)
        self.assertIn("':(exclude)release/*.tar.gz'", builder)
        self.assertIn("':(exclude)release/*.tar.gz.sha256'", builder)
        self.assertIn("':(exclude)release/pihole-speedtest-v6-bootstrap.sh'", builder)


if __name__ == "__main__":
    unittest.main()

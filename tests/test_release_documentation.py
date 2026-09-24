import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReleaseDocumentationTests(unittest.TestCase):
    RUNNER = "https://raw.githubusercontent.com/RamrattanN/PiHoleSpeedtestV6/main/install.sh"

    def test_documentation_lists_stable_and_prerelease_commands(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        curl = (ROOT / "docs" / "CURL-INSTALLATION.md").read_text(encoding="utf-8")
        stable = f"curl -fsSL \\\n  {self.RUNNER} |\n  bash\n"
        prerelease = f"curl -fsSL \\\n  {self.RUNNER} |\n  PIHOLE_SPEEDTEST_RELEASE_TAG=v1.0.6-rc.1 bash\n"
        uninstall = (
            f"curl -fsSL \\\n  {self.RUNNER} |\n  PIHOLE_SPEEDTEST_RELEASE_TAG=v1.0.6-rc.1 \\\n"
            "  bash -s -- uninstall\n"
        )

        for document in (readme, curl):
            self.assertIn(stable, document)
            self.assertIn(prerelease, document)
        self.assertIn(uninstall, curl)
        self.assertIn("`releases/latest` must continue to resolve only the latest stable release", curl)
        self.assertIn("scripts/publish_github_release.sh \\\n  --kind prerelease", curl)
        self.assertIn("PUBLISH PRERELEASE v1.0.6-rc.1", curl)
        self.assertIn("PUBLISH PRODUCTION v1.0.6", curl)


if __name__ == "__main__":
    unittest.main()

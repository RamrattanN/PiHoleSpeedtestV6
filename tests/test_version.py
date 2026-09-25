import re
import unittest
from pathlib import Path

from pihole_speedtest import __version__


ROOT = Path(__file__).resolve().parents[1]


class VersionTests(unittest.TestCase):
    def test_runtime_and_release_versions_are_stable_and_consistent(self):
        project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        template = (ROOT / "release" / "bootstrap.template.sh").read_text(
            encoding="utf-8"
        )
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        project_version = re.search(
            r'^version = "([^"]+)"$', project, flags=re.MULTILINE
        ).group(1)
        release_version = re.search(
            r'^version="([^"]+)"$', template, flags=re.MULTILINE
        ).group(1)

        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")
        self.assertEqual(project_version, __version__)
        self.assertEqual(release_version, __version__)
        self.assertNotIn("dev", __version__.lower())
        self.assertNotRegex(workflow, r"\.dev\d+")
        self.assertIn('bundle_name="pihole-speedtest-v6-${version}.tar.gz"', workflow)

    def test_next_release_version_is_1_0_7(self):
        self.assertEqual(__version__, "1.0.7")


if __name__ == "__main__":
    unittest.main()

import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_IPV4 = re.compile(
    r"\b(?:"
    r"10(?:\.\d{1,3}){3}|"
    r"192\.168(?:\.\d{1,3}){2}|"
    r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}"
    r")\b"
)


class RepositoryHygieneTests(unittest.TestCase):
    def test_mit_license_identifies_current_owner(self):
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertTrue(license_text.startswith("MIT License\n"))
        copyright_lines = [
            line
            for line in license_text.splitlines()
            if line.lower().startswith("copyright (c)")
        ]
        self.assertEqual(copyright_lines, ["Copyright (c) 2026 Nilesh Ramrattan"])
        self.assertIn("License :: OSI Approved :: MIT License", project)

    def test_repository_does_not_publish_private_ipv4_addresses(self):
        findings = []
        tracked_files = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
        ).stdout.split(b"\0")
        for relative_path in tracked_files:
            if not relative_path:
                continue
            path = ROOT / relative_path.decode("utf-8")
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for match in PRIVATE_IPV4.finditer(content):
                findings.append(f"{path.relative_to(ROOT)}:{match.group(0)}")
        self.assertEqual(findings, [], "private IPv4 addresses are not publishable")


if __name__ == "__main__":
    unittest.main()

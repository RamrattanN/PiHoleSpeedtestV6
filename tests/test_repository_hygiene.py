import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IGNORED_PARTS = {".git", ".venv", "__pycache__", "build"}
PRIVATE_IPV4 = re.compile(
    r"\b(?:"
    r"10(?:\.\d{1,3}){3}|"
    r"192\.168(?:\.\d{1,3}){2}|"
    r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}"
    r")\b"
)


class RepositoryHygieneTests(unittest.TestCase):
    def test_repository_does_not_publish_private_ipv4_addresses(self):
        findings = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or any(part in IGNORED_PARTS for part in path.parts):
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for match in PRIVATE_IPV4.finditer(content):
                findings.append(f"{path.relative_to(ROOT)}:{match.group(0)}")
        self.assertEqual(findings, [], "private IPv4 addresses are not publishable")


if __name__ == "__main__":
    unittest.main()

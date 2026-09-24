import hashlib
import re
import subprocess
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_IPV4 = re.compile(
    r"\b(?:"
    r"10(?:\.\d{1,3}){3}|"
    r"192\.168(?:\.\d{1,3}){2}|"
    r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}"
    r")\b"
)
MIT_TERMS = """\
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
PRODUCT_COPYRIGHT = "Copyright (c) 2026 Nilesh Ramrattan"
INHERITED_COPYRIGHT = "Copyright (c) 2018 Siddhu"
# Git blob SHAs of the tagged upstream LICENSE.md files for the bundled versions.
CANONICAL_LICENSES = {
    "https://github.com/chartjs/Chart.js/blob/v4.5.0/LICENSE.md": (
        "f216610fd7edadc57a11668b3ca5b7a400e5b96e",
        "Copyright (c) 2014-2024 Chart.js Contributors",
    ),
    "https://github.com/kurkle/color/blob/v0.3.2/LICENSE.md": (
        "ae411212bf290a8562b0c2c08bff8c1ca2fb4b49",
        "Copyright (c) 2018-2021 Jukka Kurkela",
    ),
}
# First-party snapshot of commit c12d4a4; any change requires a new notice audit.
V6_PACKAGE_ZIP = ROOT / "Archive" / "PiHole_SpeedTest_v6_package.zip"
V6_PACKAGE_ZIP_SHA256 = (
    "9d22c77ddffeb52d3b51d1f271e4a9ffbe9fb5055bbc71b757f51367cda6914a"
)


def copyright_lines(text):
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip().lower().startswith("copyright (c)")
    ]


def reproduced_license(notice, source):
    match = re.search(
        rf"reproduced from\n<{re.escape(source)}>:\n\n```text\n(.*?)```", notice, re.S
    )
    return match.group(1) if match else None


def git_blob_sha(text):
    content = text.encode("utf-8")
    return hashlib.sha1(b"blob %d\0" % len(content) + content).hexdigest()


class RepositoryHygieneTests(unittest.TestCase):
    def test_mit_license_identifies_current_owner(self):
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertEqual(
            license_text, f"MIT License\n\n{PRODUCT_COPYRIGHT}\n\n{MIT_TERMS}"
        )
        self.assertEqual(copyright_lines(license_text), [PRODUCT_COPYRIGHT])
        self.assertIn("License :: OSI Approved :: MIT License", project)

    def test_third_party_notice_retains_inherited_mit_license(self):
        notice = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")

        self.assertIn("https://github.com/arevindh/pihole-speedtest", notice)
        self.assertIn(
            f"MIT License\n\n{INHERITED_COPYRIGHT}\n\n{MIT_TERMS}", notice
        )
        self.assertIn("[LICENSE](LICENSE)", notice)

    def test_third_party_notice_preserves_bundled_chart_headers(self):
        notice = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        chart = (ROOT / "web" / "chart.min.js").read_text(encoding="utf-8")
        headers = re.findall(r"/\*!\n(.*?)\n \*/", chart, re.S)

        self.assertEqual(len(headers), 2)
        for header in headers:
            retained = "\n".join(line[3:] for line in header.splitlines())
            self.assertIn(f"```text\n{retained}\n```", notice)

    def test_third_party_notice_reproduces_canonical_chart_licenses(self):
        notice = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")

        for source, (blob_sha, copyright_line) in CANONICAL_LICENSES.items():
            reproduced = reproduced_license(notice, source)
            self.assertIsNotNone(reproduced, source)
            self.assertEqual(git_blob_sha(reproduced), blob_sha, source)
            self.assertTrue(reproduced.startswith("The MIT License (MIT)\n\n"))
            self.assertIn(f"\n{copyright_line}\n", reproduced)

    def test_notice_scope_matches_audited_v6_package_archive(self):
        notice = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        digest = hashlib.sha256(V6_PACKAGE_ZIP.read_bytes()).hexdigest()
        with zipfile.ZipFile(V6_PACKAGE_ZIP) as archive:
            names = archive.namelist()

        self.assertEqual(digest, V6_PACKAGE_ZIP_SHA256)
        self.assertNotIn(V6_PACKAGE_ZIP.name, notice)
        self.assertIn("`Archive/PiHole SpeedTest.zip`", notice)
        for name in names:
            self.assertNotRegex(name.lower(), r"licen[cs]e|notice|copying|chart")

    def test_product_and_third_party_licenses_are_not_confused(self):
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        notice = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")

        for inherited in ("Siddhu", "arevindh", "Chart.js", "kurkle"):
            self.assertNotIn(inherited, license_text)
        self.assertNotIn(PRODUCT_COPYRIGHT, notice)
        inherited_section = notice.split("## arevindh/pihole-speedtest\n")[1].split(
            "\n## "
        )[0]
        self.assertIn(INHERITED_COPYRIGHT, inherited_section)
        self.assertEqual(notice.count("Siddhu"), 1)
        self.assertEqual(
            copyright_lines(notice),
            [
                INHERITED_COPYRIGHT,
                *(line for _, line in CANONICAL_LICENSES.values()),
            ],
        )

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

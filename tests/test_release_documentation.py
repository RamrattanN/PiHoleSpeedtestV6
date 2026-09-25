import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CURRENT_CANDIDATE = "v1.0.6-rc.8"
SUPERSEDED_CANDIDATES = (
    "v1.0.6-rc.1",
    "v1.0.6-rc.2",
    "v1.0.6-rc.3",
    "v1.0.6-rc.4",
    "v1.0.6-rc.5",
    "v1.0.6-rc.6",
    "v1.0.6-rc.7",
)
RELEASE_DOCUMENTS = (
    "README.md",
    "DEPLOY.md",
    "docs/CURL-INSTALLATION.md",
    "docs/QA-AND-ACCEPTANCE.md",
    "docs/ROADMAP.md",
    "docs/WIKI.md",
)


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def normalized(text):
    return " ".join(text.split())


def actionable_patterns(tag):
    """Forms that would act on a release candidate if copied."""
    escaped = re.escape(tag)
    return (
        rf"PIHOLE_SPEEDTEST_RELEASE_TAG={escaped}(?![\d.])",
        rf"--tag {escaped}(?![\d.])",
        rf"--accepted-prerelease {escaped}(?![\d.])",
        rf"PUBLISH PRERELEASE {escaped}(?![\d.])",
        rf"releases/download/{escaped}/",
    )


class ReleaseDocumentationTests(unittest.TestCase):
    RUNNER = "https://raw.githubusercontent.com/RamrattanN/PiHoleSpeedtestV6/main/install.sh"

    def test_documentation_lists_stable_and_current_prerelease_commands(self):
        readme = read("README.md")
        curl = read("docs/CURL-INSTALLATION.md")
        stable = f"curl -fsSL \\\n  {self.RUNNER} |\n  bash\n"
        prerelease = (
            f"curl -fsSL \\\n  {self.RUNNER} |\n"
            f"  PIHOLE_SPEEDTEST_RELEASE_TAG={CURRENT_CANDIDATE} bash\n"
        )
        uninstall = (
            f"curl -fsSL \\\n  {self.RUNNER} |\n"
            f"  PIHOLE_SPEEDTEST_RELEASE_TAG={CURRENT_CANDIDATE} \\\n"
            "  bash -s -- uninstall\n"
        )

        for document in (readme, curl):
            self.assertIn(stable, document)
            self.assertIn(prerelease, document)
        self.assertIn(uninstall, curl)
        self.assertIn("`releases/latest` must continue to resolve only the latest stable release", curl)
        self.assertIn(
            f"scripts/publish_github_release.sh \\\n  --kind prerelease \\\n  --tag {CURRENT_CANDIDATE} \\",
            curl,
        )
        self.assertIn(f"PUBLISH PRERELEASE {CURRENT_CANDIDATE}", curl)
        self.assertIn(f"--accepted-prerelease {CURRENT_CANDIDATE}", normalized(curl))
        self.assertIn("PUBLISH PRODUCTION v1.0.6", curl)

    def test_no_actionable_command_uses_a_superseded_candidate(self):
        for name in RELEASE_DOCUMENTS:
            text = normalized(read(name))
            for candidate in SUPERSEDED_CANDIDATES:
                for pattern in actionable_patterns(candidate):
                    with self.subTest(document=name, pattern=pattern):
                        self.assertIsNone(re.search(pattern, text))

    def test_acceptance_procedure_targets_the_current_candidate(self):
        qa = normalized(read("docs/QA-AND-ACCEPTANCE.md"))

        self.assertIn(f"against the published `{CURRENT_CANDIDATE}` prerelease", qa)
        self.assertIn(f"`PIHOLE_SPEEDTEST_RELEASE_TAG={CURRENT_CANDIDATE}`", qa)

    def test_status_names_the_current_candidate_and_held_production(self):
        for name in ("README.md", "docs/CURL-INSTALLATION.md", "docs/WIKI.md"):
            text = normalized(read(name))
            with self.subTest(document=name):
                self.assertRegex(text, r"Production `v1\.0\.6` is held")
                self.assertIn(f"`{CURRENT_CANDIDATE}`", text)
                self.assertIn("current acceptance candidate", text)

    def test_superseded_candidates_are_described_historically(self):
        for name in ("README.md", "docs/CURL-INSTALLATION.md", "docs/WIKI.md"):
            text = normalized(read(name))
            with self.subTest(document=name):
                self.assertIn("`v1.0.6-rc.1` was published and accepted", text)
                self.assertIn("`v1.0.6-rc.2`", text)
                self.assertIn("`v1.0.6-rc.3`", text)
                self.assertIn("`v1.0.6-rc.4`", text)
                self.assertIn("`v1.0.6-rc.5`", text)
                self.assertIn("`v1.0.6-rc.6`", text)
                self.assertIn("superseded for acceptance", text)
        for name in RELEASE_DOCUMENTS + ("docs/KANBAN.md",):
            sentences = re.split(r"(?<=[.!?])\s+", normalized(read(name)))
            for sentence in sentences:
                if any(candidate in sentence for candidate in SUPERSEDED_CANDIDATES):
                    with self.subTest(document=name, sentence=sentence[:80]):
                        self.assertNotRegex(sentence.lower(), r"withdrawn|deleted|removed")


if __name__ == "__main__":
    unittest.main()

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLISHER = ROOT / "scripts" / "publish_github_release.sh"
TEMPLATE = ROOT / "release" / "bootstrap.template.sh"
VERSION = re.search(
    r'^version = "([^"]+)"$',
    (ROOT / "pyproject.toml").read_text(encoding="utf-8"),
    flags=re.MULTILINE,
).group(1)
ASSET = "pihole-speedtest-v6-bootstrap.sh"
PRERELEASE = f"v{VERSION}-rc.1"
PRODUCTION = f"v{VERSION}"


class ReleaseFixture:
    """A throwaway repository following the established release commit layout."""

    def __init__(self, root, bootstrap_text=None, bundle_sha256=None):
        self.root = Path(root)
        self.repo = self.root / "repo"
        self.assets = self.root / "assets"
        self.bin = self.root / "bin"
        self.gh_log = self.root / "gh.log"
        for directory in (self.repo / "scripts", self.repo / "release", self.assets, self.bin):
            directory.mkdir(parents=True)
        shutil.copy2(PUBLISHER, self.repo / "scripts" / PUBLISHER.name)
        (self.repo / "pyproject.toml").write_text(
            f'[project]\nversion = "{VERSION}"\n', encoding="utf-8"
        )
        self.git("init", "-q")
        self.source_commit = self.commit("Application source")
        bundle = self.repo / "release" / f"pihole-speedtest-v6-{VERSION}.tar.gz"
        bundle.write_bytes(b"deterministic bundle bytes")
        self.asset_commit = self.commit("Publish bundle")
        rendered = bootstrap_text or (
            TEMPLATE.read_text(encoding="utf-8")
            .replace("@SOURCE_COMMIT@", self.source_commit)
            .replace("@ASSET_COMMIT@", self.asset_commit)
            .replace(
                "@BUNDLE_SHA256@",
                bundle_sha256 or hashlib.sha256(bundle.read_bytes()).hexdigest(),
            )
        )
        (self.repo / "release" / ASSET).write_text(rendered, encoding="utf-8")
        self.release_commit = self.commit("Publish bootstrap")
        self.write_assets(rendered.encode("utf-8"))
        gh = self.bin / "gh"
        gh.write_text(
            f'#!/usr/bin/env bash\necho "$*" >> "{self.gh_log}"\nexit 97\n',
            encoding="utf-8",
        )
        gh.chmod(0o755)

    def git(self, *args):
        return subprocess.run(
            [
                "git",
                "-c",
                "maintenance.auto=false",
                "-c",
                "gc.auto=0",
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                *args,
            ],
            cwd=self.repo,
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        ).stdout.strip()

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    def write_assets(self, bootstrap_bytes, checksum_line=None):
        (self.assets / ASSET).write_bytes(bootstrap_bytes)
        self.sha256 = hashlib.sha256(bootstrap_bytes).hexdigest()
        (self.assets / f"{ASSET}.sha256").write_text(
            checksum_line or f"{self.sha256}  {ASSET}\n", encoding="utf-8"
        )

    def run(self, *extra, kind="prerelease", tag=PRERELEASE, commit=None, sha256=None):
        arguments = [
            "bash", str(self.repo / "scripts" / PUBLISHER.name),
            "--kind", kind,
            "--tag", tag,
            "--expected-commit", commit or self.release_commit,
            "--bootstrap-sha256", sha256 or self.sha256,
            "--asset-dir", str(self.assets),
        ]
        if kind == "production" and "--accepted-prerelease" not in extra:
            arguments += ["--accepted-prerelease", f"{tag}-rc.1"]
        environment = dict(os.environ)
        environment["PATH"] = f"{self.bin}:{environment['PATH']}"
        return subprocess.run(
            [*arguments, *extra],
            cwd=self.root,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=60,
        )

    def gh_calls(self):
        return self.gh_log.read_text(encoding="utf-8") if self.gh_log.exists() else ""


class PublicationValidationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = ReleaseFixture(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def assertStops(self, result, message):
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(message, result.stdout)
        self.assertEqual(self.fixture.gh_calls(), "")

    def test_prerelease_validation_succeeds_without_contacting_github(self):
        result = self.fixture.run()

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(f"Release assets validated for prerelease {PRERELEASE}", result.stdout)
        self.assertIn("Validation only.  Nothing was tagged, created, or uploaded.", result.stdout)
        self.assertIn("--prerelease --latest=false", result.stdout)
        self.assertEqual(self.fixture.gh_calls(), "")

    def test_production_validation_succeeds_without_contacting_github(self):
        result = self.fixture.run(kind="production", tag=PRODUCTION)

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("--latest", result.stdout)
        self.assertNotIn("--prerelease", result.stdout)
        self.assertEqual(self.fixture.gh_calls(), "")

    def test_tag_kind_and_version_must_agree(self):
        self.assertStops(self.fixture.run(tag=PRODUCTION), "prerelease tag must look like")
        self.assertStops(
            self.fixture.run(kind="production", tag=PRERELEASE), "production tag must look like"
        )
        self.assertStops(self.fixture.run(tag="v9.9.9-rc.1"), "do not match")
        self.assertStops(self.fixture.run(tag="v1.0.6-rc.1/x"), "prerelease tag must look like")
        self.assertStops(self.fixture.run(kind="docker"), "--kind must be prerelease or production")

    def test_production_requires_matching_accepted_prerelease(self):
        self.assertStops(
            self.fixture.run(
                "--accepted-prerelease", "v9.9.9-rc.1", kind="production", tag=PRODUCTION
            ),
            "--accepted-prerelease must be",
        )
        self.assertStops(
            self.fixture.run("--accepted-prerelease", PRERELEASE),
            "applies only to production",
        )

    def test_commit_mismatch_and_dirty_state_are_rejected(self):
        self.assertStops(
            self.fixture.run(commit=self.fixture.asset_commit), "not --expected-commit"
        )
        (self.fixture.repo / "stray.txt").write_text("stray\n", encoding="utf-8")
        self.assertStops(self.fixture.run(), "working tree is not clean")

    def test_asset_directory_must_hold_exactly_the_two_runner_assets(self):
        extra = self.fixture.assets / "notes.txt"
        extra.write_text("extra\n", encoding="utf-8")
        self.assertStops(self.fixture.run(), "must contain only")
        extra.unlink()

        (self.fixture.assets / ASSET).rename(self.fixture.assets / "bootstrap.sh")
        self.assertStops(self.fixture.run(), "must be a regular file")

    def test_missing_checksum_is_rejected(self):
        (self.fixture.assets / f"{ASSET}.sha256").unlink()

        self.assertStops(self.fixture.run(), "must be a regular file")

    def test_symbolic_links_are_rejected(self):
        bootstrap = self.fixture.assets / ASSET
        real = self.fixture.root / "real-bootstrap.sh"
        bootstrap.rename(real)
        bootstrap.symlink_to(real)

        self.assertStops(self.fixture.run(), "not a link")

    def test_checksum_records_must_be_exact(self):
        digest = self.fixture.sha256
        bootstrap = (self.fixture.assets / ASSET).read_bytes()
        for line, message in (
            (f"{digest}  {ASSET}\n{digest}  {ASSET}\n", "one SHA-256 record"),
            (f"{digest}  other.sh\n", "one SHA-256 record"),
            (f"{digest} *{ASSET}\n", "one SHA-256 record"),
            (f"{'0' * 64}  {ASSET}\n", "does not record --bootstrap-sha256"),
        ):
            with self.subTest(line=line):
                self.fixture.write_assets(bootstrap, checksum_line=line)
                self.assertStops(self.fixture.run(sha256=digest), message)

    def test_checksum_failure_is_rejected(self):
        original = (self.fixture.assets / ASSET).read_bytes()
        self.fixture.write_assets(original)
        (self.fixture.assets / ASSET).write_bytes(original + b"# altered\n")

        self.assertStops(self.fixture.run(), "sha256sum --check failed")

    def test_asset_must_match_committed_bootstrap(self):
        altered = (self.fixture.assets / ASSET).read_bytes() + b"# altered\n"
        self.fixture.write_assets(altered)

        self.assertStops(self.fixture.run(), "differs from release/")

    def test_confirmation_is_required_and_kind_specific(self):
        self.assertStops(
            self.fixture.run("--publish"), f"requires --confirm 'PUBLISH PRERELEASE {PRERELEASE}'"
        )
        self.assertStops(
            self.fixture.run("--publish", "--confirm", f"PUBLISH PRODUCTION {PRERELEASE}"),
            "requires --confirm",
        )
        self.assertStops(
            self.fixture.run(
                "--publish", "--confirm", f"PUBLISH PRERELEASE {PRODUCTION}",
                kind="production", tag=PRODUCTION,
            ),
            f"requires --confirm 'PUBLISH PRODUCTION {PRODUCTION}'",
        )
        self.assertStops(
            self.fixture.run("--confirm", f"PUBLISH PRERELEASE {PRERELEASE}"),
            "only accepted together with --publish",
        )


class PublicationBootstrapContentTests(unittest.TestCase):
    def fixture(self, **kwargs):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        return ReleaseFixture(temporary.name, **kwargs)

    def test_unresolved_placeholders_are_rejected(self):
        fixture = self.fixture(bootstrap_text=TEMPLATE.read_text(encoding="utf-8"))
        result = fixture.run()

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("unresolved release-template placeholders", result.stdout)

    def test_bundle_checksum_mismatch_is_rejected(self):
        fixture = self.fixture(bundle_sha256="0" * 64)
        result = fixture.run()

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("does not match its embedded checksum", result.stdout)

    def test_embedded_version_must_match(self):
        text = TEMPLATE.read_text(encoding="utf-8").replace(
            f'version="{VERSION}"', 'version="1.0.5"'
        )
        fixture = self.fixture(bootstrap_text=text.replace("@SOURCE_COMMIT@", "a" * 40)
                               .replace("@ASSET_COMMIT@", "b" * 40)
                               .replace("@BUNDLE_SHA256@", "c" * 64))
        result = fixture.run()

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("do not match", result.stdout)

    def test_bootstrap_commits_must_be_ancestors_of_the_release_commit(self):
        text = (
            TEMPLATE.read_text(encoding="utf-8")
            .replace("@SOURCE_COMMIT@", "a" * 40)
            .replace("@ASSET_COMMIT@", "b" * 40)
            .replace("@BUNDLE_SHA256@", "c" * 64)
        )
        fixture = self.fixture(bootstrap_text=text)
        result = fixture.run()

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("is not an ancestor of the expected commit", result.stdout)


class PublicationSafetyTests(unittest.TestCase):
    def test_publication_script_is_valid_and_never_touches_docker(self):
        subprocess.run(["bash", "-n", str(PUBLISHER)], check=True)
        script = PUBLISHER.read_text(encoding="utf-8")

        self.assertNotRegex(script.lower(), r"docker|ghcr|workflow run")
        self.assertNotRegex(script, r"\beval\b")
        self.assertIn('repository="RamrattanN/PiHoleSpeedtestV6"', script)
        self.assertIn("release_flags=(--prerelease --latest=false)", script)
        self.assertIn("release_flags=(--latest)", script)
        self.assertIn('required_confirmation="PUBLISH PRERELEASE $tag"', script)
        self.assertIn('required_confirmation="PUBLISH PRODUCTION $tag"', script)
        self.assertLess(
            script.index('if [ "$publish" -eq 0 ]; then'), script.index("gh release create")
        )


if __name__ == "__main__":
    unittest.main()

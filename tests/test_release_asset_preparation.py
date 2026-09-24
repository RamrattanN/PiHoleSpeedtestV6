"""Release scope, drift, and workflow-safety controls for version 1.0.6.

The scope lock applies to the 1.0.6 release line only: it pins every file
outside the release allowlist to the reviewed baseline e3582b2.  Bumping the
project version ends the lock for later development.
"""

import hashlib
import os
import re
import subprocess
import tarfile
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
PREPARE = WORKFLOWS / "prepare-release-assets.yml"
RELEASE_VERSION = "1.0.6"
REVIEWED_BASE = "e3582b254b8a259ab8e9375ea06038aa6f00336e"
BUNDLE = ROOT / "release" / f"pihole-speedtest-v6-{RELEASE_VERSION}.tar.gz"
BOOTSTRAP = ROOT / "release" / "pihole-speedtest-v6-bootstrap.sh"
PRIVATE_IPV4 = re.compile(
    r"\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|"
    r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b"
)
RELEASE_ALLOWLIST = {
    ".github/workflows/prepare-release-assets.yml",
    "tests/test_release_asset_preparation.py",
    "README.md",
    "DEPLOY.md",
    "docs/CURL-INSTALLATION.md",
    "docs/KANBAN.md",
    "docs/QA-AND-ACCEPTANCE.md",
    "docs/ROADMAP.md",
    "docs/WIKI.md",
    f"release/pihole-speedtest-v6-{RELEASE_VERSION}.tar.gz",
    f"release/pihole-speedtest-v6-{RELEASE_VERSION}.tar.gz.sha256",
    "release/pihole-speedtest-v6-bootstrap.sh",
}
# Ordered partition of every tracked file outside the allowlist.
PROTECTED_GROUPS = [
    ("chart", ("src/pihole_speedtest/web/", "web/")),
    ("runtime", ("src/", "deploy/")),
    ("installer", ("install.sh", "mod", "test", "scripts/")),
    ("version-and-template", ("pyproject.toml", "release/bootstrap.template.sh")),
    ("licensing", ("LICENSE", "THIRD_PARTY_NOTICES.md")),
    ("docker", ("Dockerfile", "docker/", ".github/workflows/publish.yml")),
    ("workflows", (".github/",)),
    ("tests", ("tests/",)),
    ("published-releases", ("release/",)),
    ("other", ("",)),
]
# sha256 over sorted "mode blob path" lines at the reviewed baseline, and file count.
BASELINE_DIGESTS = {
    "chart": ("46b0f5b0b4c25aa09441d09912dfbb4c98374661d3f3072e42f5eda1eef690fc", 8),
    "runtime": ("7a3f580d4ff8690a500fffd50bb1b88e7560d3a567f20847f264aad9680917ac", 15),
    "installer": ("a61172a18120527361d1b8d6ab2e56e31a819e553ac446e39872f7adc7a2c4e9", 19),
    "version-and-template": ("092537f50899ce69da3b8189ef7722786941a798dbf5f7b6fdd093e1192616a3", 2),
    "licensing": ("d2daa9886b45795f3a4fb46f63e64ee976ee5a5d6023164a9a735fa38eef1d07", 2),
    "docker": ("51898daa73be46eb2dfa82700dedc02a9fd29370a81f2f9ca65160156cec60b3", 4),
    "workflows": ("ca2d8e4d6a3353f9fd3d1fc0cc60204a612f8101d69f57aef22287995bad6987", 2),
    "tests": ("fc83f5a0d36c8fcf7ffd3abbf065bcbdcad832c0f220a8220d4c10f3ff67ec2d", 17),
    "published-releases": ("dd860ea23f231664df1c844b1417a444d6b395412ed98e135c80935abae33c4b", 14),
    "other": ("79d3cf5e77a934e246dba795ba1933bce37c0f778f16f7d7525dd4d172534106", 7),
}
RELEASE_DOCS = [
    "README.md",
    "DEPLOY.md",
    "docs/CURL-INSTALLATION.md",
    "docs/KANBAN.md",
    "docs/QA-AND-ACCEPTANCE.md",
    "docs/ROADMAP.md",
    "docs/WIKI.md",
]


def project_version():
    return re.search(
        r'^version = "([^"]+)"$',
        (ROOT / "pyproject.toml").read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    ).group(1)


def git(*args, cwd=ROOT, check=True):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=check, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True,
    )


def tracked_files():
    """Index modes with the working-tree content of every tracked file."""
    entries = {}
    for line in git("ls-files", "-s", "-z").stdout.split("\0"):
        if not line:
            continue
        meta, path = line.split("\t", 1)
        mode = meta.split()[0]
        data = (ROOT / path).read_bytes()
        blob = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
        entries[path] = (mode, blob)
    return entries


def protected_group(path):
    for name, prefixes in PROTECTED_GROUPS:
        for prefix in prefixes:
            if prefix == "" or path == prefix or (prefix.endswith("/") and path.startswith(prefix)):
                return name
    raise AssertionError(path)


def bootstrap_value(text, name):
    match = re.search(rf'^{name}="([^"]*)"$', text, flags=re.MULTILINE)
    return match.group(1) if match else None


def workflow_step_script(name):
    """Return the run block of one named step, without a YAML dependency."""
    lines = PREPARE.read_text(encoding="utf-8").splitlines()
    start = lines.index(f"      - name: {name}")
    run = next(i for i in range(start, len(lines)) if lines[i].strip() == "run: |")
    body = []
    for line in lines[run + 1:]:
        if line and not line.startswith(" " * 10):
            break
        body.append(line)
    return textwrap.dedent("\n".join(body)) + "\n"


@unittest.skipUnless(
    project_version() == RELEASE_VERSION,
    "The release scope lock applies only to the 1.0.6 release line.",
)
class ReleaseScopeTests(unittest.TestCase):
    def test_versions_are_exactly_the_release_version(self):
        from pihole_speedtest import __version__

        template = (ROOT / "release" / "bootstrap.template.sh").read_text(encoding="utf-8")
        server = (ROOT / "src" / "pihole_speedtest" / "server.py").read_text(encoding="utf-8")
        self.assertEqual(__version__, RELEASE_VERSION)
        self.assertEqual(bootstrap_value(template, "version"), RELEASE_VERSION)
        self.assertIn('"version": __version__', server)
        self.assertNotRegex(__version__, r"dev")

    def test_protected_files_match_the_reviewed_baseline(self):
        groups = {}
        for path, (mode, blob) in tracked_files().items():
            if path in RELEASE_ALLOWLIST:
                continue
            groups.setdefault(protected_group(path), []).append(f"{mode} {blob} {path}\n")
        for name, (digest, count) in BASELINE_DIGESTS.items():
            with self.subTest(group=name):
                entries = sorted(groups.get(name, []))
                self.assertEqual(len(entries), count, f"{name} files were added or removed")
                self.assertEqual(
                    hashlib.sha256("".join(entries).encode()).hexdigest(),
                    digest,
                    f"{name} files differ from the reviewed baseline",
                )

    def test_runner_and_publisher_stay_executable(self):
        entries = tracked_files()
        for path in ("install.sh", "scripts/publish_github_release.sh"):
            self.assertEqual(entries[path][0], "100755", path)

    def test_changed_files_are_within_the_allowlist(self):
        if git("cat-file", "-e", f"{REVIEWED_BASE}^{{commit}}", check=False).returncode:
            self.skipTest("Reviewed baseline history is unavailable in this checkout.")
        changed = set(git("diff", "--name-only", REVIEWED_BASE).stdout.split())
        changed |= set(git("ls-files", "--others", "--exclude-standard").stdout.split())
        self.assertEqual(sorted(changed - RELEASE_ALLOWLIST), [])

    def test_release_documents_do_not_claim_publication_or_acceptance(self):
        claim = re.compile(
            r"1\.0\.6`?\s+(?:is|was|has been)\s+(?:now\s+)?(?:published|released|"
            r"accepted|installed|live|the\s+(?:owner-approved\s+)?production)",
            re.IGNORECASE,
        )
        for name in RELEASE_DOCS:
            text = " ".join((ROOT / name).read_text(encoding="utf-8").split())
            with self.subTest(document=name):
                self.assertIsNone(claim.search(text))
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("unpublished", readme)

    def test_documents_do_not_present_a_development_version_as_current(self):
        current = re.compile(
            r"Version `[^`]*dev[^`]*` is the (?:current|installed|owner-approved|production)"
        )
        for name in RELEASE_DOCS:
            with self.subTest(document=name):
                self.assertIsNone(current.search((ROOT / name).read_text(encoding="utf-8")))

    def test_runner_rejects_bootstraps_from_another_release(self):
        runner = (ROOT / "install.sh").read_text(encoding="utf-8")

        self.assertIn('fail "Verified bootstrap does not match release $release_tag."', runner)


@unittest.skipUnless(
    project_version() == RELEASE_VERSION,
    "The release asset checks apply only to the 1.0.6 release line.",
)
class ReleaseAssetTests(unittest.TestCase):
    def setUp(self):
        if not BUNDLE.exists():
            self.skipTest("The version 1.0.6 bundle has not been committed yet.")
        self.root = f"pihole-speedtest-v6-{RELEASE_VERSION}"
        with tarfile.open(BUNDLE, "r:gz") as archive:
            self.members = archive.getnames()
            self.marker = (
                archive.extractfile(f"{self.root}/release/SOURCE-COMMIT").read().decode().strip()
            )
            self.texts = {
                member.name: archive.extractfile(member).read()
                for member in archive.getmembers()
                if member.isfile()
            }

    def test_bundle_checksum_file_is_one_exact_record(self):
        digest = hashlib.sha256(BUNDLE.read_bytes()).hexdigest()
        checksum = (BUNDLE.parent / f"{BUNDLE.name}.sha256").read_text(encoding="utf-8")

        self.assertEqual(checksum, f"{digest}  {BUNDLE.name}\n")

    def test_bundle_contents_are_complete_and_scoped(self):
        for member in ("LICENSE", "THIRD_PARTY_NOTICES.md", "web/chart.min.js", "install.sh"):
            self.assertIn(f"{self.root}/{member}", self.members)
        self.assertRegex(self.marker, r"^[0-9a-f]{40}$")
        for name in self.members:
            self.assertTrue(name == self.root or name.startswith(f"{self.root}/"), name)
            self.assertNotRegex(name, r"/release/.*\.tar\.gz(\.sha256)?$")
            self.assertFalse(name.endswith("/release/pihole-speedtest-v6-bootstrap.sh"), name)

    def test_bundle_licences_match_the_repository(self):
        for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
            self.assertEqual(self.texts[f"{self.root}/{name}"], (ROOT / name).read_bytes())

    def test_bundle_contains_no_private_addresses(self):
        for name, data in self.texts.items():
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                continue
            with self.subTest(member=name):
                self.assertEqual(PRIVATE_IPV4.findall(text), [])

    def test_bundle_source_commit_is_its_parent_when_history_is_available(self):
        relative = f"release/{BUNDLE.name}"
        added = git("log", "--diff-filter=A", "--format=%H", "--", relative, check=False)
        commits = added.stdout.split()
        if added.returncode or not commits:
            self.skipTest("Bundle history is unavailable in this checkout.")
        self.assertEqual(git("rev-parse", f"{commits[-1]}^").stdout.strip(), self.marker)

    def test_rendered_bootstrap_references_this_bundle(self):
        text = BOOTSTRAP.read_text(encoding="utf-8")
        if bootstrap_value(text, "version") != RELEASE_VERSION:
            self.skipTest("The version 1.0.6 bootstrap has not been rendered yet.")
        self.assertNotRegex(text, r"@(SOURCE_COMMIT|ASSET_COMMIT|BUNDLE_SHA256)@")
        self.assertEqual(bootstrap_value(text, "repository"), "RamrattanN/PiHoleSpeedtestV6")
        self.assertEqual(bootstrap_value(text, "source_commit"), self.marker)
        self.assertEqual(
            bootstrap_value(text, "bundle_sha256"), hashlib.sha256(BUNDLE.read_bytes()).hexdigest()
        )
        self.assertRegex(bootstrap_value(text, "asset_commit"), r"^[0-9a-f]{40}$")
        self.assertEqual(PRIVATE_IPV4.findall(text), [])
        subprocess.run(["bash", "-n", str(BOOTSTRAP)], check=True)
        added = git("log", "--diff-filter=A", "--format=%H", "--", f"release/{BUNDLE.name}", check=False)
        if added.returncode == 0 and added.stdout.split():
            self.assertEqual(bootstrap_value(text, "asset_commit"), added.stdout.split()[-1])


class PrepareWorkflowSafetyTests(unittest.TestCase):
    def setUp(self):
        self.workflow = PREPARE.read_text(encoding="utf-8")
        self.code = "\n".join(
            line for line in self.workflow.splitlines() if not line.lstrip().startswith("#")
        )

    def test_workflow_is_read_only_and_pull_request_only(self):
        trigger = self.workflow.split("\non:", 1)[1].split("\npermissions:", 1)[0]

        self.assertEqual(re.findall(r"^  ([a-z_]+):", trigger, flags=re.MULTILINE), ["pull_request"])
        self.assertIn("    branches: [main]", trigger)
        self.assertIn("permissions:\n  contents: read\n", self.workflow)
        self.assertNotRegex(self.code, r"\bwrite\b")
        self.assertNotIn("secrets.", self.code)
        self.assertIn("persist-credentials: false", self.code)
        self.assertIn("if: github.head_ref == 'release/v1.0.6-assets'", self.code)
        self.assertIn(f"REVIEWED_BASE: {REVIEWED_BASE}", self.code)

    def test_workflow_cannot_push_tag_release_publish_or_install(self):
        for forbidden in (
            r"git\s+push", r"git\s+tag", r"gh\s+release", r"gh\s+api", r"releases",
            r"--publish", r"--confirm", r"docker", r"publish\.yml", r"workflow_dispatch",
            r"pip\s+install", r"apt(-get)?\s", r"brew\s", r"npm\s", r"curl\s", r"wget\s",
            r"setup-python", r"GITHUB_TOKEN",
        ):
            with self.subTest(pattern=forbidden):
                self.assertNotRegex(self.code.lower(), forbidden.lower())

    def test_workflow_uses_only_expected_actions_and_bounded_time(self):
        self.assertEqual(
            sorted(set(re.findall(r"uses: (\S+)", self.code))),
            ["actions/checkout@v4", "actions/upload-artifact@v4"],
        )
        self.assertIn("    timeout-minutes: 20", self.code)
        steps = self.code.split("\n      - name: ")[1:]
        for step in steps:
            with self.subTest(step=step.splitlines()[0]):
                self.assertRegex(step, r"\n        timeout-minutes: \d+\n")
        self.assertIn("concurrency:\n  group: prepare-release-assets-${{ github.head_ref }}", self.code)
        self.assertIn("retention-days: 7", self.code)
        self.assertIn("if-no-files-found: error", self.code)

    def test_workflow_builds_twice_and_compares_bytes(self):
        self.assertEqual(self.code.count("scripts/build_release_assets.sh"), 2)
        self.assertIn('cmp "$RUNNER_TEMP/first/$BUNDLE" "$RUNNER_TEMP/second/$BUNDLE"', self.code)
        self.assertIn('cmp "$RUNNER_TEMP/$build/$BUNDLE" "release/$BUNDLE"', self.code)
        self.assertIn("sha256sum --check --strict", self.code)

    def test_artifact_stages_contain_only_the_intended_files(self):
        self.assertIn(
            'test "$(ls -A "$RUNNER_TEMP/artifact" | LC_ALL=C sort | tr \'\\n\' \' \')" = "$BUNDLE $BUNDLE.sha256 "',
            self.code,
        )
        self.assertIn(
            'test "$(ls -A "$RUNNER_TEMP/artifact" | LC_ALL=C sort | tr \'\\n\' \' \')" = "$BOOTSTRAP $BOOTSTRAP.sha256 "',
            self.code,
        )
        self.assertIn("path: ${{ runner.temp }}/artifact/", self.code)
        for name in ("bundle-stage", "bootstrap-stage", "release-validated"):
            self.assertIn(name, self.code)

    def test_publication_script_runs_only_in_validation_mode(self):
        dry_run = self.code.split("scripts/publish_github_release.sh", 1)[1].split("| tee", 1)[0]

        self.assertIn("--kind prerelease", dry_run)
        self.assertIn('--tag "$PRERELEASE_TAG"', dry_run)
        self.assertNotIn("--publish", dry_run)
        self.assertIn(
            'grep -Fqx "Validation only.  Nothing was tagged, created, or uploaded."', self.code
        )

    def test_licence_checks_use_repository_files_not_minified_headers(self):
        self.assertNotIn("chart.min.js |", self.code)
        self.assertNotIn("@kurkle", self.code)
        self.assertIn("for member in LICENSE THIRD_PARTY_NOTICES.md", self.code)

    def test_no_workflow_runs_on_release_events(self):
        for path in sorted(WORKFLOWS.glob("*.y*ml")):
            trigger = path.read_text(encoding="utf-8").split("\non:", 1)[1].split("\njobs:", 1)[0]
            with self.subTest(workflow=path.name):
                self.assertNotRegex(trigger, r"(?m)^\s*-?\s*release\s*:?\s*$")
        publish = (WORKFLOWS / "publish.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch", publish)
        self.assertIn("EXPERIMENTAL", publish)


class PrepareWorkflowGuardTests(unittest.TestCase):
    """Run the workflow's own guard and stage scripts in throwaway repositories."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary.name) / "repo"
        self.runner_temp = Path(self.temporary.name) / "runner"
        self.runner_temp.mkdir()
        (self.repo / "release").mkdir(parents=True)
        (self.repo / "docs").mkdir()
        (self.repo / "pyproject.toml").write_text(f'version = "{RELEASE_VERSION}"\n', encoding="utf-8")
        (self.repo / "release" / "bootstrap.template.sh").write_text(
            f'version="{RELEASE_VERSION}"\n', encoding="utf-8"
        )
        (self.repo / "release" / "pihole-speedtest-v6-bootstrap.sh").write_text(
            'version="1.0.5"\n', encoding="utf-8"
        )
        (self.repo / "docs" / "WIKI.md").write_text("wiki\n", encoding="utf-8")
        self.git("init", "-q")
        self.base = self.commit("baseline")

    def tearDown(self):
        self.temporary.cleanup()

    def git(self, *args):
        return subprocess.run(
            ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *args],
            cwd=self.repo, check=True, stdout=subprocess.PIPE, text=True,
        ).stdout.strip()

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD")

    def run_step(self, name, head_ref="release/v1.0.6-assets", base=None):
        output = self.runner_temp / "github_output"
        output.write_text("", encoding="utf-8")
        environment = dict(os.environ)
        environment.update(
            RELEASE_VERSION=RELEASE_VERSION,
            RELEASE_BRANCH="release/v1.0.6-assets",
            REVIEWED_BASE=self.base,
            BUNDLE=f"pihole-speedtest-v6-{RELEASE_VERSION}.tar.gz",
            BOOTSTRAP="pihole-speedtest-v6-bootstrap.sh",
            HEAD_REF=head_ref,
            HEAD_SHA=self.git("rev-parse", "HEAD"),
            BASE_SHA=base or self.base,
            RUNNER_TEMP=str(self.runner_temp),
            GITHUB_OUTPUT=str(output),
        )
        result = subprocess.run(
            ["bash", "-e", "-c", workflow_step_script(name)],
            cwd=self.repo, env=environment, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, timeout=60,
        )
        return result, output.read_text(encoding="utf-8")

    def guard(self, **kwargs):
        return self.run_step("Guard branch, base, scope, and cleanliness", **kwargs)[0]

    def stage(self):
        result, output = self.run_step("Determine the release stage")
        return result, output.strip()

    def test_guard_accepts_allowlisted_changes(self):
        (self.repo / "docs" / "WIKI.md").write_text("updated\n", encoding="utf-8")
        self.commit("docs")

        self.assertEqual(self.guard().returncode, 0)

    def test_guard_rejects_the_wrong_branch(self):
        result = self.guard(head_ref="feature/other")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Only release/v1.0.6-assets may prepare release assets", result.stdout)

    def test_guard_rejects_a_changed_base(self):
        result = self.guard(base="f" * 40)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("main moved from the reviewed baseline", result.stdout)

    def test_guard_rejects_disallowed_files(self):
        (self.repo / "src").mkdir()
        (self.repo / "src" / "runtime.py").write_text("changed = True\n", encoding="utf-8")
        self.commit("runtime change")
        result = self.guard()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outside the release allowlist: src/runtime.py", result.stdout)

    def test_guard_rejects_a_dirty_tree(self):
        (self.repo / "docs" / "WIKI.md").write_text("uncommitted\n", encoding="utf-8")
        result = self.guard()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not clean", result.stdout)

    def test_stage_detection_follows_tracked_files(self):
        self.assertEqual(self.stage()[1], "stage=A")
        bundle = self.repo / "release" / f"pihole-speedtest-v6-{RELEASE_VERSION}.tar.gz"
        bundle.write_bytes(b"bundle")
        (self.repo / "release" / f"{bundle.name}.sha256").write_text("x\n", encoding="utf-8")
        self.assertEqual(self.stage()[1], "stage=B")
        (self.repo / "release" / "pihole-speedtest-v6-bootstrap.sh").write_text(
            f'version="{RELEASE_VERSION}"\n', encoding="utf-8"
        )
        self.assertEqual(self.stage()[1], "stage=C")

    def test_stage_detection_rejects_inconsistent_assets(self):
        (self.repo / "release" / "pihole-speedtest-v6-bootstrap.sh").write_text(
            f'version="{RELEASE_VERSION}"\n', encoding="utf-8"
        )
        result, _ = self.stage()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("committed without its bundle", result.stdout)

        (self.repo / "release" / f"pihole-speedtest-v6-{RELEASE_VERSION}.tar.gz").write_bytes(b"x")
        result, _ = self.stage()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be committed together", result.stdout)


if __name__ == "__main__":
    unittest.main()

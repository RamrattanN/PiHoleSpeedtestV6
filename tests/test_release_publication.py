import hashlib
import json
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

    def run(self, *extra, kind="prerelease", tag=PRERELEASE, commit=None, sha256=None, extra_env=None):
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
        environment.update(extra_env or {})
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


NOT_FOUND_BODY = json.dumps(
    {
        "message": "Not Found",
        "documentation_url": "https://docs.github.com/rest/git/refs#get-a-reference",
        "status": "404",
    }
)
GH_STUB = r"""#!/usr/bin/env python3
# Models GitHub CLI behavior: HTTP errors exit 1 and still print the JSON error
# body to stdout; network errors print only to stderr.
import json
import os
import shutil
import sys

state_path = os.environ["GH_STUB_STATE"]
with open(state_path, encoding="utf-8") as source:
    state = json.load(source)
args = sys.argv[1:]
with open(os.environ["GH_STUB_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(args) + "\n")
NOT_FOUND = {"exit": 1, "stdout": state["not_found_body"]}


def respond(result):
    sys.stdout.write(result.get("stdout", ""))
    sys.stderr.write(result.get("stderr", ""))
    sys.exit(result.get("exit", 0))


def ref_body(tag, kind, sha):
    return json.dumps({"ref": f"refs/tags/{tag}", "object": {"type": kind, "sha": sha}})


if args[0] == "api":
    path = args[1]
    if "/git/ref/tags/" in path:
        tag = path.rsplit("/git/ref/tags/", 1)[1]
        if tag in state["created"]:
            respond({"stdout": ref_body(tag, "commit", state["created"][tag]["target"])})
        respond(state["refs"].get(tag, NOT_FOUND))
    if "/git/tags/" in path:
        respond(state["annotated"].get(path.rsplit("/", 1)[1], NOT_FOUND))
    respond(NOT_FOUND)
if args[:2] == ["release", "view"]:
    tag = args[2]
    release = state["created"].get(tag) or state["releases"].get(tag)
    if release is None:
        respond({"exit": 1, "stderr": "release not found\n"})
    query = args[args.index("--jq") + 1]
    if query == ".isPrerelease":
        respond({"stdout": ("true" if release["prerelease"] else "false") + "\n"})
    if query == ".assets[].name":
        respond({"stdout": "".join(name + "\n" for name in release["assets"])})
if args[:2] == ["release", "download"]:
    release = state["releases"][args[2]]
    directory = args[args.index("--dir") + 1]
    for name, source in release["files"].items():
        shutil.copyfile(source, os.path.join(directory, name))
    respond({})
if args[:2] == ["release", "create"]:
    tag = args[2]
    files = []
    for value in args[3:]:
        if value.startswith("--"):
            break
        files.append(os.path.basename(value))
    overrides = state.get("create_overrides", {})
    state["created"][tag] = {
        "target": overrides.get("target", args[args.index("--target") + 1]),
        "prerelease": overrides.get("prerelease", "--prerelease" in args),
        "assets": overrides.get("assets", files),
    }
    with open(state_path, "w", encoding="utf-8") as destination:
        json.dump(state, destination)
    respond({})
respond({"exit": 2, "stderr": "unsupported gh call in test stub\n"})
"""


class PublishPathFixture(ReleaseFixture):
    """A ReleaseFixture whose gh is a scenario stub that can never reach GitHub."""

    def __init__(self, root):
        super().__init__(root)
        self.state_path = self.root / "gh-state.json"
        self.stub_log = self.root / "gh-stub.log"
        self.config = self.root / "gh-config"
        self.config.mkdir()
        gh = self.bin / "gh"
        gh.write_text(GH_STUB, encoding="utf-8")
        gh.chmod(0o755)
        self.state = {
            "not_found_body": NOT_FOUND_BODY,
            "refs": {},
            "annotated": {},
            "releases": {},
            "created": {},
        }

    def ref(self, tag, kind, sha):
        return {"stdout": json.dumps({"ref": f"refs/tags/{tag}", "object": {"type": kind, "sha": sha}})}

    def accepted_prerelease(self, target=None, prerelease=True, bootstrap=None):
        accepted = self.root / "accepted"
        accepted.mkdir(exist_ok=True)
        (accepted / ASSET).write_bytes(bootstrap or (self.assets / ASSET).read_bytes())
        shutil.copyfile(self.assets / f"{ASSET}.sha256", accepted / f"{ASSET}.sha256")
        self.state["refs"][PRERELEASE] = self.ref(PRERELEASE, "commit", target or self.release_commit)
        self.state["releases"][PRERELEASE] = {
            "prerelease": prerelease,
            "assets": [ASSET, f"{ASSET}.sha256"],
            "files": {ASSET: str(accepted / ASSET), f"{ASSET}.sha256": str(accepted / f"{ASSET}.sha256")},
        }

    def publish(self, kind="prerelease", tag=PRERELEASE):
        self.state_path.write_text(json.dumps(self.state), encoding="utf-8")
        environment = {
            "GH_STUB_STATE": str(self.state_path),
            "GH_STUB_LOG": str(self.stub_log),
            "GH_HOST": "github.invalid",
            "GH_CONFIG_DIR": str(self.config),
            "GH_TOKEN": "test-token-never-valid",
        }
        search = f"{self.bin}:{os.environ['PATH']}"
        assert shutil.which("gh", path=search) == str(self.bin / "gh")
        confirmation = f"PUBLISH {'PRERELEASE' if kind == 'prerelease' else 'PRODUCTION'} {tag}"
        return self.run(
            "--publish", "--confirm", confirmation, kind=kind, tag=tag, extra_env=environment
        )

    def calls(self):
        if not self.stub_log.exists():
            return []
        return [json.loads(line) for line in self.stub_log.read_text(encoding="utf-8").splitlines()]

    def creates(self):
        return [call for call in self.calls() if call[:2] == ["release", "create"]]


class PublicationPathTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = PublishPathFixture(self.temporary.name)
        self.other = "f" * 40

    def tearDown(self):
        self.temporary.cleanup()

    def assertStopsWithoutPublishing(self, result, message):
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(message, result.stdout)
        self.assertEqual(self.fixture.creates(), [])

    def test_missing_tag_404_is_absent_and_prerelease_is_published_and_verified(self):
        result = self.fixture.publish()
        tag_ref = f"repos/RamrattanN/PiHoleSpeedtestV6/git/ref/tags/{PRERELEASE}"

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(f"Published prerelease {PRERELEASE} from {self.fixture.release_commit}", result.stdout)
        calls = self.fixture.calls()
        self.assertEqual(calls[0], ["api", tag_ref])
        create = calls[1]
        notes = create[create.index("--notes-file") + 1]
        self.assertEqual(
            create,
            [
                "release", "create", PRERELEASE,
                str(self.fixture.assets / ASSET), str(self.fixture.assets / f"{ASSET}.sha256"),
                "--repo", "RamrattanN/PiHoleSpeedtestV6",
                "--target", self.fixture.release_commit,
                "--prerelease", "--latest=false",
                "--title", f"Pi-hole Speedtest {PRERELEASE}",
                "--notes-file", notes,
            ],
        )
        self.assertEqual(calls[2], ["api", tag_ref])
        self.assertEqual(
            [call[:3] + [call[call.index("--jq") + 1]] for call in calls[3:]],
            [
                ["release", "view", PRERELEASE, ".isPrerelease"],
                ["release", "view", PRERELEASE, ".assets[].name"],
            ],
        )

    def test_existing_lightweight_tag_stops(self):
        self.fixture.state["refs"][PRERELEASE] = self.fixture.ref(PRERELEASE, "commit", self.other)

        self.assertStopsWithoutPublishing(
            self.fixture.publish(), f"Tag {PRERELEASE} already exists on GitHub at {self.other}"
        )

    def test_existing_annotated_tag_is_dereferenced_and_stops(self):
        tag_object = "e" * 40
        self.fixture.state["refs"][PRERELEASE] = self.fixture.ref(PRERELEASE, "tag", tag_object)
        self.fixture.state["annotated"][tag_object] = self.fixture.ref(PRERELEASE, "commit", self.other)

        self.assertStopsWithoutPublishing(
            self.fixture.publish(), f"already exists on GitHub at {self.other}"
        )

    def test_api_errors_fail_closed(self):
        errors = {
            "authentication": {"exit": 1, "stdout": json.dumps({"message": "Bad credentials", "status": "401"})},
            "authorization": {"exit": 1, "stdout": json.dumps({"message": "Resource not accessible", "status": "403"})},
            "rate limit": {"exit": 1, "stdout": json.dumps({"message": "API rate limit exceeded", "status": "403"})},
            "not found wording": {"exit": 1, "stdout": json.dumps({"message": "Moved", "status": "404"})},
            "server error": {"exit": 1, "stdout": json.dumps({"message": "Server Error", "status": "500"})},
            "network": {"exit": 1, "stdout": "", "stderr": "error connecting to api.github.com\n"},
            "malformed json": {"exit": 0, "stdout": "<html>not json</html>"},
            "json array": {"exit": 0, "stdout": "[]"},
            "error body with success exit": {"exit": 0, "stdout": NOT_FOUND_BODY},
            "malformed sha": self.fixture.ref(PRERELEASE, "commit", "xyz"),
            "short sha": self.fixture.ref(PRERELEASE, "commit", "a" * 39),
            "wrong ref": self.fixture.ref("v9.9.9-rc.1", "commit", "a" * 40),
            "tree target": self.fixture.ref(PRERELEASE, "tree", "a" * 40),
        }
        for name, response in errors.items():
            with self.subTest(case=name):
                self.fixture.state["refs"][PRERELEASE] = response
                self.fixture.stub_log.unlink(missing_ok=True)
                self.assertStopsWithoutPublishing(
                    self.fixture.publish(), f"Could not determine whether tag {PRERELEASE} exists"
                )

    def test_annotated_tag_errors_fail_closed(self):
        tag_object = "e" * 40
        self.fixture.state["refs"][PRERELEASE] = self.fixture.ref(PRERELEASE, "tag", tag_object)
        for name, response in {
            "missing tag object": {"exit": 1, "stdout": NOT_FOUND_BODY},
            "nested annotated tag": self.fixture.ref(PRERELEASE, "tag", "d" * 40),
        }.items():
            with self.subTest(case=name):
                self.fixture.state["annotated"][tag_object] = response
                self.fixture.stub_log.unlink(missing_ok=True)
                self.assertStopsWithoutPublishing(self.fixture.publish(), "Could not determine")

    def test_post_publication_verification_detects_wrong_results(self):
        for name, override, message in (
            ("wrong commit", {"target": self.other}, "does not point at the expected commit"),
            ("not prerelease", {"prerelease": False}, "wrong prerelease state"),
            ("extra asset", {"assets": [ASSET, f"{ASSET}.sha256", "extra.bin"]}, "exactly the runner assets"),
        ):
            with self.subTest(case=name):
                self.fixture.state["create_overrides"] = override
                self.fixture.state["created"] = {}
                result = self.fixture.publish()
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(message, result.stdout)

    def test_production_publishes_after_verifying_the_accepted_prerelease(self):
        self.fixture.accepted_prerelease()
        result = self.fixture.publish(kind="production", tag=PRODUCTION)

        self.assertEqual(result.returncode, 0, result.stdout)
        create = self.fixture.creates()
        self.assertEqual(len(create), 1)
        self.assertIn("--latest", create[0])
        self.assertNotIn("--prerelease", create[0])
        self.assertEqual(create[0][create[0].index("--target") + 1], self.fixture.release_commit)
        self.assertIn(
            ["api", f"repos/RamrattanN/PiHoleSpeedtestV6/git/ref/tags/{PRERELEASE}"],
            self.fixture.calls(),
        )

    def test_production_accepts_an_annotated_prerelease_tag_on_the_expected_commit(self):
        self.fixture.accepted_prerelease()
        tag_object = "e" * 40
        self.fixture.state["refs"][PRERELEASE] = self.fixture.ref(PRERELEASE, "tag", tag_object)
        self.fixture.state["annotated"][tag_object] = self.fixture.ref(
            PRERELEASE, "commit", self.fixture.release_commit
        )

        self.assertEqual(self.fixture.publish(kind="production", tag=PRODUCTION).returncode, 0)

    def test_production_rejects_an_unverified_accepted_prerelease(self):
        cases = (
            ("wrong commit", {"target": self.other}, "was not published from the expected commit"),
            ("not a prerelease", {"prerelease": False}, "is not a published prerelease"),
            ("different bootstrap", {"bootstrap": b"#!/usr/bin/env bash\n"}, "not byte-identical"),
        )
        for name, options, message in cases:
            with self.subTest(case=name):
                self.fixture.state["refs"] = {}
                self.fixture.state["releases"] = {}
                self.fixture.accepted_prerelease(**options)
                self.fixture.stub_log.unlink(missing_ok=True)
                self.assertStopsWithoutPublishing(
                    self.fixture.publish(kind="production", tag=PRODUCTION), message
                )
        self.fixture.state["refs"] = {}
        self.fixture.stub_log.unlink(missing_ok=True)
        self.assertStopsWithoutPublishing(
            self.fixture.publish(kind="production", tag=PRODUCTION),
            "was not published from the expected commit",
        )

    def test_validation_only_never_invokes_github(self):
        self.fixture.state_path.write_text(json.dumps(self.fixture.state), encoding="utf-8")
        result = self.fixture.run(
            extra_env={
                "GH_STUB_STATE": str(self.fixture.state_path),
                "GH_STUB_LOG": str(self.fixture.stub_log),
                "GH_HOST": "github.invalid",
            }
        )

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Validation only.  Nothing was tagged, created, or uploaded.", result.stdout)
        self.assertEqual(self.fixture.calls(), [])


if __name__ == "__main__":
    unittest.main()

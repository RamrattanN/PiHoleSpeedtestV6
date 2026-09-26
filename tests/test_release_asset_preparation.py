"""Release scope, drift, and workflow-safety controls for version 1.0.6.

The preparation scope lock protected the unpublished 1.0.6 release candidate.
It is closed after production publication so maintenance documentation can
accurately record acceptance without modifying the immutable release commit.
The asset, lineage, and workflow safety tests below remain active.
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
# Content baseline for the scope lock: the reviewed rc.7 merge on main.
REVIEWED_BASE = "f4b742e89c293b6c6d351c32dfc011b6f78223bc"
# Pull request base for the current recut, pinned by the preparation workflow.
PR_BASE = "cb51f9595e72cb9cda33d10acbdab6414bf4c952"
RELEASE_BRANCH = "fix/v1.0.6-heading-style"
# Assets recut before publication; they must never be reused.
SUPERSEDED_SHA256 = {
    "40ea0b5c1c60f4143441244d03e338dde8cfa1fa23f3684cb3cd9de75c7408ce",
    "59a67636376c918da111b6efba78715cc57f88929895faf0cfbb779b794a8844",
    "84f39f17c01271f3554ce0fe4b26763f6aedc5f1434724abce4296201558ddae",
    # v1.0.6-rc.1, superseded by the collection-schedule correction.
    "b356547c6171fd0978f04591211a725140c72e19f57a29d577011cb2df7a4abb",
    "c1e19a103f85e7c6fc35baee58f1aa6c48ede434a721d32fd842e91a175e2450",
    # First rc.2 assets, superseded by the rc.2 documentation correction.
    "4b4ac3959240d05df9865eef4fabaa58556d8a86996c38956980eea567189144",
    "c6ee26eb441d06e11ff3cd9d753876471799e7fda6b6e37903c21cd317437c64",
    # Published rc.2 assets remain historical evidence and cannot be reused for rc.3.
    "ba04982ba7605a8ba7cf165de6fdab70d9fa7bb1b34bf2e8650386204a46ef85",
    "dfc75dc7b775c18940a864e33a27be73c6c3fb449a61b2102d38dc65dbe663b3",
    # Published rc.3 assets remain historical evidence and cannot be reused for rc.4.
    "4fdfff598c73d805f119bf9e72b6fc92ecfe9cb45e366cea3210f2598fe55b30",
    "cf699eb50583551ad40db7399bb3e88ec458018629f91ee219b38b161ac315b4",
    # Published rc.4 assets remain historical evidence and cannot be reused for rc.5.
    "7cbd9f088d4ee9676d1c09619d52478b1e3dc1130cdc922bcecedddcec394d2a",
    "81e0f27302d01cd4dab51e194c40b3ceff7019ef9e9111e95fc0f2176e95a1cc",
    # Published rc.5 assets remain historical evidence and cannot be reused for rc.6.
    "4d67f41e3b12268c5690c5237240787d753afc95a0678a4496ccbd7f2db28fcc",
    "3af1b4290b00d1b06f07356312f5ba3b7837f07b9059330f60725bd48ce919c7",
    # Published rc.6 assets remain historical evidence and cannot be reused for rc.7.
    "7d7e33b12fdb9605465373b92a8c970be2818ce0757397254d740d15b679a54d",
    "083b5f4320cb61681362ef3b30a9ddc38d1bb2db293462fd8b905b14b6313789",
    # Published rc.7 assets remain historical evidence and cannot be reused for rc.8.
    "f99c75395b689dd8aa8f54bdf49c00bd524e6ce2654aa860b866487a10938698",
    "fe0bd79aa80389654b2038dd55a45d7bd1bc0d984c8c1ef0db92b3f9ff9c3a6e",
    # Published rc.8 assets remain historical evidence and cannot be reused for rc.9.
    "de89ec112dd64cd0123777ee66f150f1830faf00b203cca97d1bba6514f1db77",
    "948435ea38017633125c9cf107d2a56abb03b9ea3e7aa30d2d7bbdff8177992c",
}
# The superseded bundle on main (source commit, SHA-256) that this recut replaces.
INHERITED_BUNDLE = (
    "cabcbd7b217666b6b98ed41f1581c05a38bb11d4",
    "de89ec112dd64cd0123777ee66f150f1830faf00b203cca97d1bba6514f1db77",
)
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
    "docs/PIHOLE-V6-ADAPTER.md",
    "docs/QA-AND-ACCEPTANCE.md",
    "docs/ROADMAP.md",
    "docs/WIKI.md",
    f"release/pihole-speedtest-v6-{RELEASE_VERSION}.tar.gz",
    f"release/pihole-speedtest-v6-{RELEASE_VERSION}.tar.gz.sha256",
    "release/pihole-speedtest-v6-bootstrap.sh",
}
# Files outside the allowlist that carry an exact owner-approved change.  Each is
# pinned to its complete corrected content and excluded from the group digests.
APPROVED_OVERRIDES = {
    # The owner-approved post-rc.7 Pi-hole LCARS typography correction.
    "THIRD_PARTY_NOTICES.md": "6594ec9722c4de5c6f8385cbb4fcea230b1267e9cfeade4fa09cd83101fc7595",
    "pyproject.toml": "356d7b137f96e71720e44315966e09f4ef16949b820287bb413b5d2d129cc7eb",
    # The rc.9 bundle builder normalizes archive modes across runner umasks.
    "scripts/build_release_assets.sh": "e2f2e8919e250ee8569d04e8dad6436ac801ded482696e9f071e740497464550",
    "src/pihole_speedtest/server.py": "8a81fa20411d5798f8e3f0d8a80b5de0219183119c8177db8928f8289af13ff4",
    "src/pihole_speedtest/web/app.js": "918b8f7d8bb887d4f024fe28a3e331331ef746e8c272a46faa08532b56408c86",
    # Post-rc.8 owner-requested uppercase heading and Pi-hole title-color correction.
    "src/pihole_speedtest/web/styles.css": "f44386bc24ab32526a1640ed8aef5a9abe8f43de95bfe7ce04861d8d3882a7ea",
    "src/pihole_speedtest/web/fonts/antonio-v19-latin-100.woff2": "dfabf3dee53dc9c8b2a15b9661242cd06717aaeb7f19ea36a19b04596b7221a8",
    "src/pihole_speedtest/web/fonts/antonio-v19-latin-700.woff2": "b6d68353c888773b36c65d1cddbc8aa805259dd74d8cc9e500def7f41818840e",
    "src/pihole_speedtest/web/fonts/antonio-v19-latin-regular.woff2": "c367b51912a07ce2f2ec2fe9bf4c332c8e27133f466c7e22925088c2fdbf6040",
    "tests/test_server.py": "2a2b8cd073d9b153939da15d495afe4748ee211efe51d9a77956456752104e5a",
    "tests/test_web_assets.py": "18bbcd1ce8b03283f1497563d6454fdf9579ee8bd86edb27f4c382eb7677f7e3",
    "tests/test_release_documentation.py": "9b99116da24f3948f887c820d12a2d04301e0bbe9e4294ab03af22514e8cab82",
}
APPROVED_OVERRIDE_MODES = {
    path: "100755" if path == "scripts/build_release_assets.sh" else "100644"
    for path in APPROVED_OVERRIDES
}
# Ordered partition of every tracked file outside the allowlist and overrides.
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
    "chart": ("afa6e76c260c8e510f9014a003a5a0f437c8308a024af5e0bbbe5e608c2e9c0a", 6),
    "runtime": ("bba3082480c1901d6a2880defb5b2e7d07c942a260349435c6ca19f21ebd8374", 15),
    "installer": ("27cd67ec3cc4a071cf6dd3aa3e76e4dbc6b73be556a5de1f85ea3430c5d78a01", 18),
    "version-and-template": ("d3b04dcacfcd663122b831a41207aaee1de02baffc096e78665692d5876795f0", 1),
    "licensing": ("277478439fad1f542b1f766675df58a1c32c7738a64f6f0e3e8bd921fbfe2bbc", 1),
    "docker": ("51898daa73be46eb2dfa82700dedc02a9fd29370a81f2f9ca65160156cec60b3", 4),
    "workflows": ("ca2d8e4d6a3353f9fd3d1fc0cc60204a612f8101d69f57aef22287995bad6987", 2),
    "tests": ("bd3fd6cc7a149ecef3d605ee600074263c5e065f0f50f48900251e5c72ae8ee2", 15),
    "published-releases": ("dd860ea23f231664df1c844b1417a444d6b395412ed98e135c80935abae33c4b", 14),
    "other": ("3ec5663d54549afade020ac123e2ee7b01beb784c53a4e37efb996f2479990a7", 6),
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


def approved_override_violations(read_bytes):
    """Return overrides whose content is not the exact approved correction."""
    return sorted(
        path
        for path, digest in APPROVED_OVERRIDES.items()
        if hashlib.sha256(read_bytes(path)).hexdigest() != digest
    )


SHALLOW_HISTORY_REASON = (
    "Full Git history is required for release provenance; the authoritative "
    "prepare-release-assets workflow performs this check with fetch-depth: 0."
)


def require_full_history(repo):
    shallow = git("rev-parse", "--is-shallow-repository", cwd=repo).stdout.strip()
    if shallow == "true":
        raise unittest.SkipTest(SHALLOW_HISTORY_REASON)
    if shallow != "false":
        raise AssertionError(f"Unexpected shallow-repository state: {shallow!r}")


def verify_bundle_lineage(repo, bundle_relative, source_commit):
    """Return the latest commit that changed the bundle after proving its parent is the source."""
    require_full_history(repo)
    asset_commit = git("log", "-1", "--format=%H", "--", bundle_relative, cwd=repo).stdout.strip()
    if not asset_commit:
        raise AssertionError(f"{bundle_relative} has no commit in this history.")
    parent = git("rev-parse", f"{asset_commit}^", cwd=repo).stdout.strip()
    if parent != source_commit:
        raise AssertionError(
            f"Bundle commit {asset_commit} has parent {parent}, not source {source_commit}."
        )
    return asset_commit


def verify_asset_commit(repo, bundle_relative, asset_commit, source_commit):
    """Prove asset_commit holds exactly the committed bundle and follows its source."""
    require_full_history(repo)
    committed = subprocess.run(
        ["git", "show", f"{asset_commit}:{bundle_relative}"],
        cwd=repo, check=True, stdout=subprocess.PIPE,
    ).stdout
    if committed != (Path(repo) / bundle_relative).read_bytes():
        raise AssertionError(f"Asset commit {asset_commit} does not hold the committed bundle.")
    parent = git("rev-parse", f"{asset_commit}^", cwd=repo).stdout.strip()
    if parent != source_commit:
        raise AssertionError(
            f"Asset commit {asset_commit} has parent {parent}, not source {source_commit}."
        )
    return asset_commit


def bootstrap_bundle_state(text, bundle_sha256, bundle_source_commit):
    """Classify how the committed bootstrap relates to the committed bundle.

    "match": the bootstrap references this bundle and its source.
    "awaiting-render": the bootstrap belongs entirely to an earlier bundle
    lineage, the transient state between a recut bundle commit and its Stage B
    bootstrap.  The preparation workflow's Stage C still requires "match".
    "mismatch": anything partial, which always fails.
    """
    same_bundle = bootstrap_value(text, "bundle_sha256") == bundle_sha256
    same_source = bootstrap_value(text, "source_commit") == bundle_source_commit
    if same_bundle and same_source:
        return "match"
    if not same_bundle and not same_source:
        return "awaiting-render"
    return "mismatch"


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


@unittest.skip("The 1.0.6 prerelease scope lock ended at stable publication.")
class ReleaseScopeTests(unittest.TestCase):
    def test_versions_are_exactly_the_release_version(self):
        from pihole_speedtest import __version__

        template = (ROOT / "release" / "bootstrap.template.sh").read_text(encoding="utf-8")
        server = (ROOT / "src" / "pihole_speedtest" / "server.py").read_text(encoding="utf-8")
        self.assertEqual(__version__, RELEASE_VERSION)
        self.assertEqual(bootstrap_value(template, "version"), RELEASE_VERSION)
        self.assertIn('"version": __version__', server)
        self.assertNotRegex(__version__, r"dev")

    def test_approved_overrides_match_their_exact_correction(self):
        self.assertEqual(
            approved_override_violations(lambda path: (ROOT / path).read_bytes()), []
        )
        entries = tracked_files()
        self.assertEqual(set(APPROVED_OVERRIDE_MODES), set(APPROVED_OVERRIDES))
        for path, mode in APPROVED_OVERRIDE_MODES.items():
            self.assertEqual(entries[path][0], mode, path)

    def test_any_further_override_edit_is_rejected(self):
        for path in APPROVED_OVERRIDES:
            original = (ROOT / path).read_bytes()
            for altered in (original + b"\n", original.replace(b"a", b"b", 1), b""):
                with self.subTest(path=path, size=len(altered)):

                    def read(candidate, target=path, content=altered):
                        if candidate == target:
                            return content
                        return (ROOT / candidate).read_bytes()

                    self.assertEqual(approved_override_violations(read), [path])

    def test_protected_files_match_the_reviewed_baseline(self):
        self.assertEqual(
            approved_override_violations(lambda path: (ROOT / path).read_bytes()), []
        )
        groups = {}
        for path, (mode, blob) in tracked_files().items():
            if path in RELEASE_ALLOWLIST or path in APPROVED_OVERRIDES:
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

    def test_bundle_bytes_are_independent_of_shell_and_git_umasks(self):
        source_commit = git("rev-parse", "HEAD").stdout.strip()
        with tempfile.TemporaryDirectory() as tmp:
            outputs = []
            for setting in ("0022", "0002"):
                destination = Path(tmp) / setting
                subprocess.run(
                    ["bash", "-c", 'umask "$1"; shift; exec "$@"', "bash", setting,
                     str(ROOT / "scripts" / "build_release_assets.sh"),
                     "--source-commit", source_commit,
                     "--output-directory", str(destination)],
                    cwd=ROOT, check=True, stdout=subprocess.PIPE, text=True,
                    env={**os.environ, "GIT_CONFIG_COUNT": "1",
                         "GIT_CONFIG_KEY_0": "tar.umask",
                         "GIT_CONFIG_VALUE_0": setting},
                )
                outputs.append((destination / BUNDLE.name).read_bytes())
            self.assertEqual(outputs[0], outputs[1])

    def test_changed_files_are_within_the_allowlist(self):
        if git("cat-file", "-e", f"{REVIEWED_BASE}^{{commit}}", check=False).returncode:
            self.skipTest("Reviewed baseline history is unavailable in this checkout.")
        changed = set(git("diff", "--name-only", REVIEWED_BASE).stdout.split())
        changed |= set(git("ls-files", "--others", "--exclude-standard").stdout.split())
        self.assertEqual(sorted(changed - RELEASE_ALLOWLIST - set(APPROVED_OVERRIDES)), [])

    def test_local_data_is_never_tracked(self):
        self.assertEqual(git("ls-files", "--", "data/").stdout, "")
        ignored = git("check-ignore", "-q", "--no-index", "data/admin.token", check=False)
        self.assertEqual(ignored.returncode, 0, "data/ must remain ignored")

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
            self.assertFalse(name.startswith(f"{self.root}/data/"), name)
            self.assertNotIn("admin.token", name)
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

    def test_bundle_source_commit_is_its_parent(self):
        text = BOOTSTRAP.read_text(encoding="utf-8")
        relative = f"release/{BUNDLE.name}"
        if self.bundle_state(text) == "match":
            verify_asset_commit(ROOT, relative, bootstrap_value(text, "asset_commit"), self.marker)
        else:
            verify_bundle_lineage(ROOT, relative, self.marker)

    def test_committed_assets_are_not_superseded(self):
        digest = hashlib.sha256(BUNDLE.read_bytes()).hexdigest()
        if (self.marker, digest) == INHERITED_BUNDLE:
            self.skipTest("Recut in progress: Stage A replaces the superseded bundle inherited from main.")
        self.assertNotIn(digest, SUPERSEDED_SHA256)
        text = BOOTSTRAP.read_text(encoding="utf-8")
        if self.bundle_state(text) == "match":
            self.assertNotIn(hashlib.sha256(BOOTSTRAP.read_bytes()).hexdigest(), SUPERSEDED_SHA256)

    def bundle_state(self, text):
        return bootstrap_bundle_state(
            text, hashlib.sha256(BUNDLE.read_bytes()).hexdigest(), self.marker
        )

    def test_rendered_bootstrap_references_this_bundle(self):
        text = BOOTSTRAP.read_text(encoding="utf-8")
        if bootstrap_value(text, "version") != RELEASE_VERSION:
            self.skipTest("The version 1.0.6 bootstrap has not been rendered yet.")
        self.assertNotRegex(text, r"@(SOURCE_COMMIT|ASSET_COMMIT|BUNDLE_SHA256)@")
        self.assertEqual(bootstrap_value(text, "repository"), "RamrattanN/PiHoleSpeedtestV6")
        self.assertRegex(bootstrap_value(text, "asset_commit"), r"^[0-9a-f]{40}$")
        self.assertEqual(PRIVATE_IPV4.findall(text), [])
        subprocess.run(["bash", "-n", str(BOOTSTRAP)], check=True)
        state = self.bundle_state(text)
        if state == "awaiting-render":
            self.skipTest(
                "Recut in progress: the committed bundle awaits its Stage B bootstrap; "
                "the prepare-release-assets workflow Stage C requires them to match."
            )
        self.assertEqual(state, "match")
        self.assertEqual(bootstrap_value(text, "source_commit"), self.marker)
        self.assertEqual(
            bootstrap_value(text, "bundle_sha256"), hashlib.sha256(BUNDLE.read_bytes()).hexdigest()
        )

    def test_rendered_bootstrap_asset_commit_is_the_bundle_commit(self):
        text = BOOTSTRAP.read_text(encoding="utf-8")
        if bootstrap_value(text, "version") != RELEASE_VERSION:
            self.skipTest("The version 1.0.6 bootstrap has not been rendered yet.")
        if self.bundle_state(text) == "awaiting-render":
            self.skipTest("Recut in progress: the committed bundle awaits its Stage B bootstrap.")
        self.assertEqual(self.bundle_state(text), "match")
        verify_asset_commit(
            ROOT, f"release/{BUNDLE.name}", bootstrap_value(text, "asset_commit"), self.marker
        )


class BundleLineageCheckTests(unittest.TestCase):
    """Exercise the provenance helper on full-history and shallow repositories."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary.name) / "repo"
        (self.repo / "release").mkdir(parents=True)
        self.fixture_git("init", "-q")
        (self.repo / "source.txt").write_text("source\n", encoding="utf-8")
        self.source = self.commit("source")
        (self.repo / "release" / "bundle.tar.gz").write_bytes(b"bundle")
        self.asset = self.commit("bundle")

    def tearDown(self):
        self.temporary.cleanup()

    def fixture_git(self, *args, cwd=None):
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
            cwd=cwd or self.repo, check=True, stdout=subprocess.PIPE, text=True,
        ).stdout.strip()

    def commit(self, message):
        self.fixture_git("add", "-A")
        self.fixture_git("commit", "-q", "-m", message)
        return self.fixture_git("rev-parse", "HEAD")

    def test_full_history_runs_the_provenance_assertion(self):
        self.assertEqual(
            verify_bundle_lineage(self.repo, "release/bundle.tar.gz", self.source), self.asset
        )

    def test_invalid_full_history_lineage_fails(self):
        (self.repo / "source.txt").write_text("later\n", encoding="utf-8")
        later = self.commit("later")
        with self.assertRaisesRegex(AssertionError, "not source"):
            verify_bundle_lineage(self.repo, "release/bundle.tar.gz", later)
        with self.assertRaisesRegex(AssertionError, "has no commit"):
            verify_bundle_lineage(self.repo, "release/other.tar.gz", self.source)

    def test_asset_commit_must_hold_the_committed_bundle_and_follow_its_source(self):
        bundle = "release/bundle.tar.gz"
        self.assertEqual(verify_asset_commit(self.repo, bundle, self.asset, self.source), self.asset)
        with self.assertRaisesRegex(AssertionError, "not source"):
            verify_asset_commit(self.repo, bundle, self.asset, self.asset)
        (self.repo / bundle).write_bytes(b"different bundle")
        self.commit("replace bundle")
        with self.assertRaisesRegex(AssertionError, "does not hold the committed bundle"):
            verify_asset_commit(self.repo, bundle, self.asset, self.source)

    def test_git_errors_fail_instead_of_skipping(self):
        with self.assertRaises(subprocess.CalledProcessError):
            verify_bundle_lineage(Path(self.temporary.name), "release/bundle.tar.gz", self.source)

    def test_shallow_repository_skips_with_the_explicit_reason(self):
        shallow = Path(self.temporary.name) / "shallow"
        self.fixture_git(
            "-c", "protocol.file.allow=always", "clone", "-q", "--depth", "1",
            self.repo.resolve().as_uri(), str(shallow), cwd=self.temporary.name,
        )
        with self.assertRaises(unittest.SkipTest) as raised:
            verify_bundle_lineage(shallow, "release/bundle.tar.gz", self.source)
        self.assertEqual(str(raised.exception), SHALLOW_HISTORY_REASON)
        with self.assertRaises(unittest.SkipTest):
            verify_asset_commit(shallow, "release/bundle.tar.gz", self.asset, self.source)


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
        self.assertIn(f"if: github.head_ref == '{RELEASE_BRANCH}'", self.code)
        self.assertIn(f"REVIEWED_BASE: {PR_BASE}", self.code)
        self.assertIn(f"RELEASE_BRANCH: {RELEASE_BRANCH}", self.code)
        for digest in SUPERSEDED_SHA256:
            self.assertIn(digest, self.code)

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
        self.assertEqual(self.code.count("scripts/build_release_assets.sh"), 3)
        self.assertIn("scripts/build_release_assets.sh|\\", self.code)
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

    def test_workflow_allowlist_matches_the_release_policy(self):
        guard = self.code.split("case \"$path\" in", 1)[1].split("*)", 1)[0]
        listed = set(
            re.findall(
                r"[A-Za-z0-9_./-]+\.(?:yml|toml|html|py|js|css|woff2|md|gz|sha256|sh|service)",
                guard,
            )
        )

        self.assertEqual(listed, RELEASE_ALLOWLIST | set(APPROVED_OVERRIDES))

    def test_workflow_keeps_local_data_out_of_bundles_and_artifacts(self):
        self.assertIn('grep -Eq "^$root/data(/|\\$)|admin\\.token"', self.code)
        self.assertEqual(self.code.count('test -z "$(git ls-files -- data/)"'), 2)

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
            cwd=self.repo, check=True, stdout=subprocess.PIPE, text=True,
        ).stdout.strip()

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD")

    def run_step(self, name, head_ref=RELEASE_BRANCH, base=None):
        output = self.runner_temp / "github_output"
        output.write_text("", encoding="utf-8")
        environment = dict(os.environ)
        environment.update(
            RELEASE_VERSION=RELEASE_VERSION,
            RELEASE_BRANCH=RELEASE_BRANCH,
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
        for head_ref in (
            "feature/other",
            "release/v1.0.6-assets",
            "release/v1.0.6-assets-2",
            "fix/v1.0.6-release-publication",
            "fix/v1.0.6-collection-schedule-2",
        ):
            with self.subTest(head_ref=head_ref):
                result = self.guard(head_ref=head_ref)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(
                    f"Only {RELEASE_BRANCH} may prepare release assets", result.stdout
                )

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

    def write(self, relative, content):
        path = self.repo / relative
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")

    def test_stage_detection_follows_changes_from_the_base(self):
        self.assertEqual(self.stage()[1], "stage=A")
        bundle = f"release/pihole-speedtest-v6-{RELEASE_VERSION}.tar.gz"
        self.write(bundle, b"bundle")
        self.write(f"{bundle}.sha256", "x\n")
        self.commit("bundle")
        self.assertEqual(self.stage()[1], "stage=B")
        self.write("release/pihole-speedtest-v6-bootstrap.sh", f'version="{RELEASE_VERSION}"\n')
        self.commit("bootstrap")
        self.assertEqual(self.stage()[1], "stage=C")

    def test_recut_does_not_reuse_assets_inherited_from_the_base(self):
        bundle = f"release/pihole-speedtest-v6-{RELEASE_VERSION}.tar.gz"
        self.write(bundle, b"old bundle")
        self.write(f"{bundle}.sha256", "old\n")
        self.write("release/pihole-speedtest-v6-bootstrap.sh", f'version="{RELEASE_VERSION}"\n')
        self.base = self.commit("released assets on main")
        self.write("docs/WIKI.md", "recut\n")
        self.commit("tool fix")
        self.assertEqual(self.stage()[1], "stage=A")
        self.write(bundle, b"new bundle")
        self.write(f"{bundle}.sha256", "new\n")
        self.commit("recut bundle")
        self.assertEqual(self.stage()[1], "stage=B")

    def test_stage_detection_rejects_inconsistent_assets(self):
        self.write("release/pihole-speedtest-v6-bootstrap.sh", f'version="{RELEASE_VERSION}"\n')
        self.commit("bootstrap only")
        result, _ = self.stage()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("bootstrap is committed without a new bundle", result.stdout)

        self.write(f"release/pihole-speedtest-v6-{RELEASE_VERSION}.tar.gz", b"x")
        self.commit("bundle without checksum")
        result, _ = self.stage()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be committed together", result.stdout)

    def test_stage_c_requires_a_release_version_bootstrap(self):
        bundle = f"release/pihole-speedtest-v6-{RELEASE_VERSION}.tar.gz"
        self.write(bundle, b"bundle")
        self.write(f"{bundle}.sha256", "x\n")
        self.write("release/pihole-speedtest-v6-bootstrap.sh", 'version="9.9.9"\n')
        self.commit("wrong bootstrap")
        result, _ = self.stage()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"is not version {RELEASE_VERSION}", result.stdout)


class BootstrapBundleStateTests(unittest.TestCase):
    def text(self, bundle_sha256, source_commit):
        return f'bundle_sha256="{bundle_sha256}"\nsource_commit="{source_commit}"\n'

    def test_states(self):
        bundle, source = "a" * 64, "b" * 40
        self.assertEqual(bootstrap_bundle_state(self.text(bundle, source), bundle, source), "match")
        self.assertEqual(
            bootstrap_bundle_state(self.text("c" * 64, "d" * 40), bundle, source), "awaiting-render"
        )
        self.assertEqual(bootstrap_bundle_state(self.text("c" * 64, source), bundle, source), "mismatch")
        self.assertEqual(bootstrap_bundle_state(self.text(bundle, "d" * 40), bundle, source), "mismatch")


if __name__ == "__main__":
    unittest.main()

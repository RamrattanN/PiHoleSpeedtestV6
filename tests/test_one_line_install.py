import hashlib
import io
import os
import re
import subprocess
import tarfile
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "install.sh"
BOOTSTRAP = ROOT / "release" / "bootstrap.template.sh"
VERSION = re.search(
    r'^version = "([^"]+)"$',
    (ROOT / "pyproject.toml").read_text(encoding="utf-8"),
    flags=re.MULTILINE,
).group(1)
SOURCE_COMMIT = "a" * 40
ASSET_COMMIT = "b" * 40
DEVICE_ADDRESS = "203.0.113.10"
PRIVATE_IPV4 = re.compile(
    r"\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|"
    r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b"
)
SYSTEM_PREFIXES = (
    "/var/lib/pihole-speedtest",
    "/opt/pihole-speedtest",
    "/var/www/html",
    "/etc/pihole",
    "/etc/systemd/system",
    "/etc/default/pihole-speedtest-v6",
)


def write_executable(path, content):
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    path.chmod(0o755)


def stub_sudo(bin_dir):
    write_executable(
        bin_dir / "sudo",
        f"""
        #!/usr/bin/env python3
        import os
        import sys

        root = os.environ["FAKE_ROOT"]
        prefixes = {SYSTEM_PREFIXES!r}
        args = []
        for arg in sys.argv[1:]:
            for prefix in prefixes:
                if arg.startswith(prefix):
                    arg = root + arg
                    break
            args.append(arg)
        with open(os.path.join(root, "calls.log"), "a", encoding="utf-8") as log:
            log.write("sudo " + " ".join(sys.argv[1:]) + "\\n")
        os.execvp(args[0], args)
        """,
    )


# Fake bundle scripts model the installed state under FAKE_ROOT and record the
# order in which the bootstrap invokes each privileged phase.
FAKE_SCRIPT_HEADER = """
#!/usr/bin/env bash
set -euo pipefail
F="$FAKE_ROOT"
data="$F/var/lib/pihole-speedtest"
manifest="$data/install-manifest.txt"
units="$F/etc/systemd/system"
echo "$(basename "$0") $*" >> "$F/phases.log"
set_manifest() {
  grep -v -e '^pihole_adapter_installed=' -e '^pihole_adapter_manifest=' "$manifest" > "$manifest.tmp" || true
  mv "$manifest.tmp" "$manifest"
  printf '%s\\n' "$@" >> "$manifest"
}
"""

FAKE_SCRIPTS = {
    "install_release.sh": """
        if [ -e "$F/opt/pihole-speedtest" ]; then echo "STOP: exists" >&2; exit 1; fi
        mkdir -p "$F/opt/pihole-speedtest" "$units" "$data" "$F/etc/default" \\
          "$F/state/active" "$F/state/enabled"
        [ -f "$data/speedtest.db" ] || echo "history" > "$data/speedtest.db"
        [ -f "$data/settings.json" ] || echo '{"collection_interval_minutes":15}' > "$data/settings.json"
        touch "$units/pihole-speedtest-dashboard.service" \\
          "$units/pihole-speedtest-collect.service" \\
          "$units/pihole-speedtest-collect.timer" \\
          "$F/etc/default/pihole-speedtest-v6" "$F/state/user"
        touch "$F/state/active/pihole-speedtest-dashboard.service" \\
          "$F/state/active/pihole-speedtest-collect.timer" \\
          "$F/state/enabled/pihole-speedtest-dashboard.service" \\
          "$F/state/enabled/pihole-speedtest-collect.timer"
        printf 'installed_at=now\\nsource_commit=%s\\npihole_adapter_installed=false\\n' "$2" > "$manifest"
        """,
    "uninstall_release.sh": """
        if ! grep -q '^pihole_adapter_installed=false$' "$manifest"; then exit 1; fi
        rm -rf -- "$F/opt/pihole-speedtest" "$units" "$F/etc/default/pihole-speedtest-v6" \\
          "$F/state/user" "$F/state/active" "$F/state/enabled"
        echo "uninstalled_at=now" >> "$manifest"
        """,
    "install_pihole_adapter.sh": """
        if [ -f "$F/state/fail-adapter" ]; then echo "adapter preflight failed" >&2; exit 1; fi
        admin="$F/var/www/html/admin"
        recovery="/var/lib/pihole-speedtest-adapter-recovery/1"
        mkdir -p "$F$recovery"
        cp "$admin/scripts/lua/sidebar.lp" "$F$recovery/sidebar.lp.before"
        echo "-- BEGIN PIHOLE-SPEEDTEST-V6" >> "$admin/scripts/lua/sidebar.lp"
        echo overview > "$admin/speedtest.lp"
        echo setup > "$admin/speedtest-setup.lp"
        python3 - "$admin" "$F$recovery" <<'PY'
        import hashlib, json, pathlib, sys
        admin, recovery = map(pathlib.Path, sys.argv[1:])
        sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
        sidebar = admin / "scripts" / "lua" / "sidebar.lp"
        backup = recovery / "sidebar.lp.before"
        pages = [admin / "speedtest.lp", admin / "speedtest-setup.lp"]
        manifest = {
            "sidebar": {"path": str(sidebar), "backup": str(backup),
                        "before_sha256": sha(backup), "installed_sha256": sha(sidebar)},
            "created": [{"path": str(page), "sha256": sha(page)} for page in pages],
        }
        (recovery / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        PY
        set_manifest "pihole_adapter_installed=true" "pihole_adapter_manifest=$recovery/manifest.json"
        if [ -f "$F/state/fail-adapter-late" ]; then echo "late adapter failure" >&2; exit 1; fi
        """,
    "remove_pihole_adapter.sh": """
        adapter="$F$(sed -n 's/^pihole_adapter_manifest=//p' "$manifest")"
        python3 - "$adapter" <<'PY'
        import json, pathlib, shutil, sys
        manifest = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
        shutil.copy2(manifest["sidebar"]["backup"], manifest["sidebar"]["path"])
        for created in manifest["created"]:
            pathlib.Path(created["path"]).unlink()
        PY
        set_manifest "pihole_adapter_installed=false"
        """,
}


class BootstrapHarness:
    def __init__(self, root):
        self.root = Path(root)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.fake = self.root / "fake"
        (self.fake / "state").mkdir(parents=True)
        sidebar = self.fake / "var/www/html/admin/scripts/lua/sidebar.lp"
        sidebar.parent.mkdir(parents=True)
        sidebar.write_text("original sidebar\n", encoding="utf-8")
        self.bundle = self.root / f"pihole-speedtest-v6-{VERSION}.tar.gz"
        self._build_bundle()
        self._write_stubs()
        self.bootstrap = self.root / "bootstrap.sh"
        self.render()

    def _build_bundle(self):
        top = f"pihole-speedtest-v6-{VERSION}"
        with tarfile.open(self.bundle, "w:gz") as archive:
            files = {"release/SOURCE-COMMIT": SOURCE_COMMIT + "\n"}
            for name, body in FAKE_SCRIPTS.items():
                files[f"scripts/{name}"] = (
                    textwrap.dedent(FAKE_SCRIPT_HEADER).lstrip()
                    + textwrap.dedent(body)
                )
            for name, content in files.items():
                data = content.encode("utf-8")
                info = tarfile.TarInfo(f"{top}/{name}")
                info.size = len(data)
                info.mode = 0o755
                archive.addfile(info, io.BytesIO(data))

    def render(self, bundle_sha256=None):
        digest = bundle_sha256 or hashlib.sha256(self.bundle.read_bytes()).hexdigest()
        rendered = (
            BOOTSTRAP.read_text(encoding="utf-8")
            .replace("@SOURCE_COMMIT@", SOURCE_COMMIT)
            .replace("@ASSET_COMMIT@", ASSET_COMMIT)
            .replace("@BUNDLE_SHA256@", digest)
        )
        self.bootstrap.write_text(rendered, encoding="utf-8")

    def _write_stubs(self):
        stub_sudo(self.bin)
        write_executable(
            self.bin / "curl",
            f"""
            #!/usr/bin/env python3
            import os
            import shutil
            import sys

            root = os.environ["FAKE_ROOT"]
            args = sys.argv[1:]
            url = args[-1]
            if "--output" in args:
                shutil.copyfile({str(self.bundle)!r}, args[args.index("--output") + 1])
            elif url.endswith("/api/health"):
                if not os.path.exists(os.path.join(root, "state/active/pihole-speedtest-dashboard.service")):
                    sys.exit(7)
                print('{{"status": "ok", "version": "{VERSION}", "measurements": 1}}')
            elif "/admin/" in url:
                page = url.rsplit("/admin/", 1)[1]
                if page and not os.path.exists(os.path.join(root, "var/www/html/admin", page + ".lp")):
                    sys.exit(22)
            else:
                sys.exit(22)
            """,
        )
        write_executable(
            self.bin / "systemctl",
            """
            #!/usr/bin/env python3
            import fnmatch
            import os
            import sys

            root = os.environ["FAKE_ROOT"]
            args = [arg for arg in sys.argv[1:] if arg not in ("--quiet", "--no-legend")]
            command = args[0]
            if command == "is-active":
                unit = args[1]
                if unit == "pihole-FTL":
                    sys.exit(1 if os.path.exists(os.path.join(root, "state/ftl-down")) else 0)
                sys.exit(0 if os.path.exists(os.path.join(root, "state/active", unit)) else 3)
            if command == "list-unit-files":
                unit_dir = os.path.join(root, "etc/systemd/system")
                units = sorted(os.listdir(unit_dir)) if os.path.isdir(unit_dir) else []
                pattern = next(arg for arg in args[1:] if not arg.startswith("--"))
                for unit in units:
                    if not fnmatch.fnmatch(unit, pattern):
                        continue
                    if "--type=timer" in args and not unit.endswith(".timer"):
                        continue
                    enabled = os.path.exists(os.path.join(root, "state/enabled", unit))
                    if "--state=enabled" in args and not enabled:
                        continue
                    print(f"{unit} {'enabled' if enabled else 'disabled'}")
                sys.exit(0)
            sys.exit(2)
            """,
        )
        write_executable(
            self.bin / "id",
            """
            #!/usr/bin/env bash
            if [ "${1:-}" = "-u" ]; then echo 1000; exit 0; fi
            [ -f "$FAKE_ROOT/state/user" ]
            """,
        )
        write_executable(
            self.bin / "hostname",
            f"""
            #!/usr/bin/env bash
            echo "{DEVICE_ADDRESS} 2001:db8::10"
            """,
        )
        write_executable(
            self.bin / "pihole-FTL",
            """
            #!/usr/bin/env bash
            [ "${1:-}" = "--config" ] || exit 2
            case "${2:-}" in
              webserver.domain)
                [ -f "$FAKE_ROOT/state/https" ] && printf '%s\n' 'pi.hole'
                ;;
              webserver.port)
                if [ -f "$FAKE_ROOT/state/https" ]; then
                  printf '%s\n' '80o,443os,[::]:80o,[::]:443os'
                else
                  printf '%s\n' '80o,[::]:80o'
                fi
                ;;
              webserver.tls.cert)
                [ -f "$FAKE_ROOT/state/https" ] && printf '%s\n' '/etc/pihole/tls.pem'
                ;;
              *) exit 2 ;;
            esac
            """,
        )

    def run(self, *args):
        environment = dict(os.environ)
        environment["PATH"] = f"{self.bin}:{environment['PATH']}"
        environment["FAKE_ROOT"] = str(self.fake)
        return subprocess.run(
            ["bash", str(self.bootstrap), *args],
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=60,
        )

    def phases(self):
        log = self.fake / "phases.log"
        if not log.exists():
            return []
        return [line.split()[0] for line in log.read_text(encoding="utf-8").splitlines()]

    def clear_phases(self):
        (self.fake / "phases.log").unlink(missing_ok=True)

    def path(self, relative):
        return self.fake / relative

    def manifest(self):
        return self.path("var/lib/pihole-speedtest/install-manifest.txt").read_text(
            encoding="utf-8"
        )


class RunnerHarness:
    def __init__(self, root):
        self.root = Path(root)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.releases = self.root / "releases"
        self.served = self.releases / "latest" / "download"
        self.served.mkdir(parents=True)
        self.log = self.root / "bootstrap.log"
        self.url_log = self.root / "urls.log"
        self.bootstrap = self.served / "pihole-speedtest-v6-bootstrap.sh"
        self.publish_bootstrap(self.fake_bootstrap())
        write_executable(
            self.bin / "curl",
            f"""
            #!/usr/bin/env python3
            import shutil
            import sys

            args = sys.argv[1:]
            url = args[-1]
            with open({str(self.url_log)!r}, "a", encoding="utf-8") as log:
                log.write(url + "\\n")
            prefix = "https://github.com/RamrattanN/PiHoleSpeedtestV6/releases/"
            if not url.startswith(prefix) or "--proto" not in args:
                sys.exit(22)
            source = {str(self.releases)!r} + "/" + url[len(prefix):]
            try:
                shutil.copyfile(source, args[args.index("--output") + 1])
            except (FileNotFoundError, IsADirectoryError):
                sys.exit(22)
            """,
        )
        write_executable(
            self.bin / "id",
            """
            #!/usr/bin/env bash
            echo "${FAKE_UID:-1000}"
            """,
        )

    def fake_bootstrap(self, version=VERSION):
        return (
            "#!/usr/bin/env bash\n"
            'repository="RamrattanN/PiHoleSpeedtestV6"\n'
            f'version="{version}"\n'
            "# install-all|uninstall-all|install|uninstall\n"
            f'echo "$*" >> "{self.log}"\n'
        )

    def publish_bootstrap(self, content, checksum=None, release="latest/download"):
        directory = self.releases / release
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "pihole-speedtest-v6-bootstrap.sh").write_text(content, encoding="utf-8")
        digest = checksum or hashlib.sha256(content.encode("utf-8")).hexdigest()
        (directory / "pihole-speedtest-v6-bootstrap.sh.sha256").write_text(
            f"{digest}  pihole-speedtest-v6-bootstrap.sh\n", encoding="utf-8"
        )

    def urls(self):
        if not self.url_log.exists():
            return []
        return self.url_log.read_text(encoding="utf-8").splitlines()

    def run(self, *args, uid="1000", tag=None):
        environment = dict(os.environ)
        environment["PATH"] = f"{self.bin}:{environment['PATH']}"
        environment["FAKE_UID"] = uid
        environment["TMPDIR"] = str(self.root)
        environment.pop("PIHOLE_SPEEDTEST_RELEASE_TAG", None)
        if tag is not None:
            environment["PIHOLE_SPEEDTEST_RELEASE_TAG"] = tag
        return subprocess.run(
            ["bash", "-s", "--", *args],
            input=RUNNER.read_text(encoding="utf-8"),
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=60,
        )

    def calls(self):
        if not self.log.exists():
            return []
        return self.log.read_text(encoding="utf-8").splitlines()


class RunnerStaticTests(unittest.TestCase):
    def test_runner_has_valid_bash_syntax(self):
        subprocess.run(["bash", "-n", str(RUNNER)], check=True)

    def test_runner_downloads_verified_release_bootstrap_without_privilege(self):
        runner = RUNNER.read_text(encoding="utf-8")
        without_usage = re.sub(r"(?s)usage\(\) \{.*?\n\}\n", "", runner)
        code = "\n".join(
            line
            for line in without_usage.splitlines()
            if not line.lstrip().startswith(("#", "echo ", "fail "))
            and "|| fail " not in line
        )

        self.assertTrue(runner.startswith("#!/usr/bin/env bash\n"))
        self.assertIn("set -euo pipefail", runner)
        self.assertIn(
            'latest_release_url="https://github.com/${repository}/releases/latest/download"',
            runner,
        )
        self.assertIn(
            'tagged_release_url="https://github.com/${repository}/releases/download"',
            runner,
        )
        self.assertIn('repository="RamrattanN/PiHoleSpeedtestV6"', runner)
        self.assertIn("--proto '=https' --tlsv1.2", runner)
        self.assertLess(
            code.index("sha256sum --check"), code.index('bash "$bootstrap"')
        )
        self.assertNotRegex(code, r"\beval\b")
        self.assertNotRegex(code, r"\bsudo\b")
        self.assertNotRegex(code, r"\|\s*(sudo\s+)?(ba)?sh\b")
        self.assertIn('"$bootstrap_action" "$@" </dev/null', code)
        self.assertTrue(runner.rstrip().endswith('main "$@"'))

    def test_scripts_contain_no_private_ipv4_addresses(self):
        for path in (RUNNER, BOOTSTRAP):
            self.assertEqual(PRIVATE_IPV4.findall(path.read_text(encoding="utf-8")), [])


class RunnerBehaviourTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.harness = RunnerHarness(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_default_action_installs_everything(self):
        result = self.harness.run()

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.harness.calls(), ["install-all"])

    def test_explicit_install_and_uninstall_map_to_full_actions(self):
        self.assertEqual(self.harness.run("install").returncode, 0)
        self.assertEqual(self.harness.run("uninstall").returncode, 0)
        self.assertEqual(
            self.harness.run("install", "--interval-minutes", "60").returncode, 0
        )

        self.assertEqual(
            self.harness.calls(),
            ["install-all", "uninstall-all", "install-all --interval-minutes 60"],
        )

    def test_unknown_action_and_uninstall_options_are_rejected(self):
        self.assertEqual(self.harness.run("purge-data").returncode, 2)
        self.assertEqual(self.harness.run("uninstall", "--force").returncode, 2)
        self.assertEqual(self.harness.calls(), [])

    def test_checksum_mismatch_prevents_execution(self):
        self.harness.publish_bootstrap(
            self.harness.bootstrap.read_text(encoding="utf-8"), checksum="0" * 64
        )
        result = self.harness.run()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checksum verification failed", result.stdout)
        self.assertEqual(self.harness.calls(), [])

    def test_missing_checksum_prevents_execution(self):
        (self.harness.served / "pihole-speedtest-v6-bootstrap.sh.sha256").unlink()
        result = self.harness.run()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Download failed", result.stdout)
        self.assertEqual(self.harness.calls(), [])

    def test_unexpected_checksum_content_prevents_execution(self):
        checksum = self.harness.served / "pihole-speedtest-v6-bootstrap.sh.sha256"
        checksum.write_text(checksum.read_text(encoding="utf-8") + "extra\n", encoding="utf-8")
        result = self.harness.run()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unexpected content", result.stdout)
        self.assertEqual(self.harness.calls(), [])

    def test_unrendered_bootstrap_is_rejected_even_with_matching_checksum(self):
        self.harness.publish_bootstrap(
            self.harness.bootstrap.read_text(encoding="utf-8")
            + 'source_commit="@SOURCE_COMMIT@"\n'
        )
        result = self.harness.run()

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.harness.calls(), [])

    def test_root_invocation_is_refused(self):
        result = self.harness.run(uid="0")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not as root", result.stdout)
        self.assertEqual(self.harness.calls(), [])

    def test_temporary_files_are_removed(self):
        self.harness.run()

        self.assertEqual(list(Path(self.temporary.name).glob("pihole-speedtest-install.*")), [])


class RunnerReleaseTagTests(unittest.TestCase):
    RELEASES = "https://github.com/RamrattanN/PiHoleSpeedtestV6/releases/"
    ASSETS = ("pihole-speedtest-v6-bootstrap.sh.sha256", "pihole-speedtest-v6-bootstrap.sh")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.harness = RunnerHarness(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def expected_urls(self, release):
        return [f"{self.RELEASES}{release}/{asset}" for asset in self.ASSETS]

    def test_default_and_empty_tag_use_latest_stable_release(self):
        self.assertEqual(self.harness.run().returncode, 0)
        self.assertEqual(self.harness.run(tag="").returncode, 0)

        self.assertEqual(self.harness.urls(), self.expected_urls("latest/download") * 2)
        self.assertEqual(self.harness.calls(), ["install-all", "install-all"])

    def test_prerelease_tag_uses_exact_tagged_release(self):
        release = "download/v1.0.6-rc.1"
        self.harness.publish_bootstrap(self.harness.fake_bootstrap("1.0.6"), release=release)
        result = self.harness.run(tag="v1.0.6-rc.1")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("explicitly selected release v1.0.6-rc.1", result.stdout)
        self.assertEqual(self.harness.urls(), self.expected_urls(release))
        self.assertEqual(self.harness.calls(), ["install-all"])

    def test_stable_tag_uses_exact_tagged_release(self):
        release = "download/v1.0.6"
        self.harness.publish_bootstrap(self.harness.fake_bootstrap("1.0.6"), release=release)
        result = self.harness.run(tag="v1.0.6")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.harness.urls(), self.expected_urls(release))

    def test_tagged_release_keeps_actions_and_options(self):
        release = "download/v1.0.6-rc.1"
        self.harness.publish_bootstrap(self.harness.fake_bootstrap("1.0.6"), release=release)
        self.assertEqual(self.harness.run("uninstall", tag="v1.0.6-rc.1").returncode, 0)
        self.assertEqual(
            self.harness.run(
                "install", "--interval-minutes", "60",
                "--pihole-origin", "https://pihole.example.net",
                tag="v1.0.6-rc.1",
            ).returncode,
            0,
        )

        self.assertEqual(
            self.harness.calls(),
            [
                "uninstall-all",
                "install-all --interval-minutes 60 --pihole-origin https://pihole.example.net",
            ],
        )

    def test_invalid_tags_fail_before_any_request_or_execution(self):
        invalid = [
            "1.0.6",
            "v1.0",
            "v01.0.6",
            "v1.0.6-rc.0",
            "v1.0.6-beta.1",
            "v1.0.6 ",
            " v1.0.6",
            "v1.0.6 v1.0.7",
            "v1.0.6\nv1.0.7",
            "v1.0.6/",
            "v1.0.6/../latest",
            "../v1.0.6",
            "..",
            "v1.0.6;id",
            "v1.0.6$(id)",
            "`id`",
            "v1.0.6|cat",
            "v1.0.6&",
            "v1.0.6?x=1",
            "v1.0.6#fragment",
            "v1.0.6%2F..",
            "latest",
            "https://example.com/v1.0.6",
            "//example.com/v1.0.6",
        ]
        for tag in invalid:
            with self.subTest(tag=tag):
                result = self.harness.run(tag=tag)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("PIHOLE_SPEEDTEST_RELEASE_TAG must be a release tag", result.stdout)
        self.assertEqual(self.harness.urls(), [])
        self.assertEqual(self.harness.calls(), [])

    def test_tagged_bootstrap_must_match_the_tag_version(self):
        release = "download/v1.0.6"
        self.harness.publish_bootstrap(self.harness.fake_bootstrap("1.0.5"), release=release)
        result = self.harness.run(tag="v1.0.6")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match release v1.0.6", result.stdout)
        self.assertEqual(self.harness.calls(), [])

    def test_missing_tagged_release_executes_nothing(self):
        result = self.harness.run(tag="v9.9.9")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Download failed", result.stdout)
        self.assertEqual(self.harness.calls(), [])

    def test_documented_pipeline_forms_pass_the_tag_to_bash(self):
        release = "download/v1.0.6-rc.1"
        self.harness.publish_bootstrap(self.harness.fake_bootstrap("1.0.6"), release=release)
        environment = dict(os.environ)
        environment["PATH"] = f"{self.harness.bin}:{environment['PATH']}"
        environment["TMPDIR"] = str(self.harness.root)
        environment["RUNNER"] = str(RUNNER)
        environment.pop("PIHOLE_SPEEDTEST_RELEASE_TAG", None)
        for pipeline in (
            'cat "$RUNNER" | PIHOLE_SPEEDTEST_RELEASE_TAG=v1.0.6-rc.1 bash',
            'cat "$RUNNER" |\n  PIHOLE_SPEEDTEST_RELEASE_TAG=v1.0.6-rc.1 \\\n  bash -s -- uninstall',
        ):
            result = subprocess.run(
                ["/bin/sh", "-c", pipeline],
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stdout)

        self.assertEqual(self.harness.calls(), ["install-all", "uninstall-all"])
        self.assertEqual(self.harness.urls(), self.expected_urls(release) * 2)

    def test_truncated_bootstrap_executes_nothing(self):
        content = self.harness.fake_bootstrap()
        release = "download/v1.0.6-rc.1"
        self.harness.publish_bootstrap(
            content[: len(content) // 2],
            checksum=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            release=release,
        )
        result = self.harness.run(tag="v1.0.6-rc.1")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checksum verification failed", result.stdout)
        self.assertEqual(self.harness.calls(), [])


class BootstrapStaticTests(unittest.TestCase):
    def test_full_actions_are_documented_and_granular_actions_remain(self):
        bootstrap = BOOTSTRAP.read_text(encoding="utf-8")

        self.assertIn(
            "  install-all|uninstall-all|install|uninstall|install-adapter|remove-adapter|purge-data) ;;",
            bootstrap,
        )
        self.assertNotRegex(bootstrap, r"\beval\b")
        self.assertNotIn("rm -rf -- \"$data_dir\"", bootstrap)
        self.assertNotIn("purge_preserved_data.sh\" \"$@\"\n    ;;\n  install-all", bootstrap)

    def test_install_all_phase_order(self):
        body = BOOTSTRAP.read_text(encoding="utf-8").split("run_install_all() {", 1)[1]
        order = [
            "install_companion",
            "verify_dashboard",
            "verify_single_timer",
            "install_pihole_adapter.sh",
            'verify_pihole "$pihole_origin"',
            "verify_adapter_installed",
            "Pi-hole Overview",
        ]
        positions = [body.index(marker) for marker in order]

        self.assertEqual(positions, sorted(positions))

    def test_uninstall_all_removes_adapter_before_companion(self):
        body = BOOTSTRAP.read_text(encoding="utf-8").split("remove_installed_product() {", 1)[1]
        order = [
            "remove_pihole_adapter.sh",
            "verify_adapter_absent",
            "uninstall_release.sh",
            "verify_data_preserved",
            'verify_pihole ""',
            "verify_companion_absent",
        ]
        positions = [body.index(marker) for marker in order]

        self.assertEqual(positions, sorted(positions))


class BootstrapBehaviourTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.harness = BootstrapHarness(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def install_all(self, *args):
        result = self.harness.run("install-all", *args)
        self.assertEqual(result.returncode, 0, result.stdout)
        return result

    def test_install_all_installs_companion_then_adapter_and_reports_addresses(self):
        result = self.install_all()

        self.assertEqual(
            self.harness.phases(), ["install_release.sh", "install_pihole_adapter.sh"]
        )
        self.assertIn(f"Dashboard: http://{DEVICE_ADDRESS}:8765/", result.stdout)
        self.assertIn(f"Pi-hole Overview: http://{DEVICE_ADDRESS}/admin/speedtest", result.stdout)
        self.assertIn(f"Pi-hole Setup: http://{DEVICE_ADDRESS}/admin/speedtest-setup", result.stdout)
        self.assertIn("exactly one enabled and active", result.stdout)
        self.assertIn(f"source_commit={SOURCE_COMMIT}", self.harness.manifest())

    def test_install_all_passes_explicit_origins_and_interval(self):
        self.install_all(
            "--pihole-origin", "https://pihole.example.net",
            "--companion-url", "https://speedtest.example.net",
            "--interval-minutes", "60",
        )
        log = (self.harness.fake / "phases.log").read_text(encoding="utf-8")

        self.assertIn("--pihole-origin https://pihole.example.net", log)
        self.assertIn("--companion-url https://speedtest.example.net", log)
        self.assertIn("--interval-minutes 60", log)

    def test_install_all_detects_pihole_https_and_uses_https_companion(self):
        (self.harness.path("state") / "https").touch()
        certificate = self.harness.path("etc/pihole/tls.pem")
        certificate.parent.mkdir(parents=True)
        certificate.write_text("test certificate\n", encoding="utf-8")

        result = self.install_all()
        log = (self.harness.fake / "phases.log").read_text(encoding="utf-8")

        self.assertIn("Dashboard: https://pi.hole:8765/", result.stdout)
        self.assertIn("Pi-hole Overview: https://pi.hole/admin/speedtest", result.stdout)
        self.assertIn("--pihole-origin https://pi.hole", log)
        self.assertIn("--companion-url https://pi.hole:8765", log)

    def test_repeated_install_all_is_idempotent(self):
        self.install_all()
        self.harness.clear_phases()
        result = self.install_all()

        self.assertEqual(self.harness.phases(), [])
        self.assertIn("already installed", result.stdout)

    def test_install_all_requires_exactly_one_enabled_timer(self):
        self.install_all()
        extra = "pihole-speedtest-legacy.timer"
        (self.harness.path("etc/systemd/system") / extra).touch()
        (self.harness.path("state/enabled") / extra).touch()
        result = self.harness.run("install-all")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exactly one enabled collection timer", result.stdout)

    def test_adapter_failure_preserves_companion_and_pihole(self):
        (self.harness.path("state") / "fail-adapter").touch()
        result = self.harness.run("install-all")
        sidebar = self.harness.path("var/www/html/admin/scripts/lua/sidebar.lp")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Install the Pi-hole sidebar adapter", result.stdout)
        self.assertIn("install-adapter", result.stdout)
        self.assertEqual(sidebar.read_text(encoding="utf-8"), "original sidebar\n")
        self.assertTrue(self.harness.path("opt/pihole-speedtest").is_dir())
        self.assertTrue(self.harness.path("var/lib/pihole-speedtest/speedtest.db").is_file())
        self.assertIn("pihole_adapter_installed=false", self.harness.manifest())

    def test_late_adapter_failure_removes_adapter_through_its_manifest(self):
        (self.harness.path("state") / "fail-adapter-late").touch()
        result = self.harness.run("install-all")
        sidebar = self.harness.path("var/www/html/admin/scripts/lua/sidebar.lp")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(
            self.harness.phases(),
            ["install_release.sh", "install_pihole_adapter.sh", "remove_pihole_adapter.sh"],
        )
        self.assertEqual(sidebar.read_text(encoding="utf-8"), "original sidebar\n")
        self.assertFalse(self.harness.path("var/www/html/admin/speedtest.lp").exists())
        self.assertTrue(self.harness.path("opt/pihole-speedtest").is_dir())
        self.assertIn("no sidebar adapter changes", result.stdout)

    def test_uninstall_all_removes_adapter_first_and_preserves_data(self):
        self.install_all()
        database = self.harness.path("var/lib/pihole-speedtest/speedtest.db")
        settings = self.harness.path("var/lib/pihole-speedtest/settings.json")
        database.write_text("measurement history\n", encoding="utf-8")
        settings.write_text('{"collection_interval_minutes":60}\n', encoding="utf-8")
        self.harness.clear_phases()
        result = self.harness.run("uninstall-all")
        sidebar = self.harness.path("var/www/html/admin/scripts/lua/sidebar.lp")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(
            self.harness.phases(), ["remove_pihole_adapter.sh", "uninstall_release.sh"]
        )
        self.assertEqual(database.read_text(encoding="utf-8"), "measurement history\n")
        self.assertEqual(settings.read_text(encoding="utf-8"), '{"collection_interval_minutes":60}\n')
        self.assertEqual(sidebar.read_text(encoding="utf-8"), "original sidebar\n")
        self.assertFalse(self.harness.path("opt/pihole-speedtest").exists())
        self.assertIn("USER DATA PRESERVED", result.stdout)

    def test_repeated_uninstall_all_is_safe(self):
        self.install_all()
        self.assertEqual(self.harness.run("uninstall-all").returncode, 0)
        self.harness.clear_phases()
        result = self.harness.run("uninstall-all")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.harness.phases(), [])
        self.assertIn("already uninstalled", result.stdout)
        self.assertTrue(self.harness.path("var/lib/pihole-speedtest/speedtest.db").is_file())

    def test_uninstall_all_without_installation_changes_nothing(self):
        result = self.harness.run("uninstall-all")

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("not installed", result.stdout)
        self.assertEqual(self.harness.phases(), [])

    def test_install_all_reuses_preserved_data_after_uninstall(self):
        self.install_all()
        database = self.harness.path("var/lib/pihole-speedtest/speedtest.db")
        database.write_text("measurement history\n", encoding="utf-8")
        self.assertEqual(self.harness.run("uninstall-all").returncode, 0)
        self.install_all()

        self.assertEqual(database.read_text(encoding="utf-8"), "measurement history\n")

    def test_install_all_upgrades_older_installation_by_preserving_reinstall(self):
        self.install_all()
        manifest = self.harness.path("var/lib/pihole-speedtest/install-manifest.txt")
        manifest.write_text(
            self.harness.manifest().replace(SOURCE_COMMIT, "c" * 40), encoding="utf-8"
        )
        database = self.harness.path("var/lib/pihole-speedtest/speedtest.db")
        database.write_text("measurement history\n", encoding="utf-8")
        self.harness.clear_phases()
        self.install_all()

        self.assertEqual(
            self.harness.phases(),
            [
                "remove_pihole_adapter.sh",
                "uninstall_release.sh",
                "install_release.sh",
                "install_pihole_adapter.sh",
            ],
        )
        self.assertEqual(database.read_text(encoding="utf-8"), "measurement history\n")
        self.assertIn(f"source_commit={SOURCE_COMMIT}", self.harness.manifest())

    def test_partial_installation_stops_without_changes(self):
        units = self.harness.path("etc/systemd/system")
        units.mkdir(parents=True)
        (units / "pihole-speedtest-collect.timer").touch()
        for action in ("install-all", "uninstall-all"):
            result = self.harness.run(action)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("incomplete companion installation", result.stdout)
        self.assertEqual(self.harness.phases(), [])

    def test_bundle_checksum_mismatch_stops_before_privileged_execution(self):
        self.harness.render(bundle_sha256="0" * 64)
        result = self.harness.run("install-all")

        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.harness.fake / "calls.log").exists())
        self.assertEqual(self.harness.phases(), [])


if __name__ == "__main__":
    unittest.main()

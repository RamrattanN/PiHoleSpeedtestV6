"""Run the real guarded adapter scripts against an isolated, path-rewritten tree.

Absolute production paths, the root-only guard and the approved sidebar checksum
are rewritten into a temporary directory; system commands are stubbed. Nothing
here touches a live Pi-hole.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11; the installer itself requires tomllib
    tomllib = None

ROOT = Path(__file__).resolve().parents[1]
APPROVED = "83943cbdf5258fe43e819108a5135e070d6742e273753ba398a8d28e1a008fdb"
SOURCE_COMMIT = "b" * 40
INSTALLED_COMMIT = "fea0efe90e7b61e2e763bb18017525f381169e22"
COMPANION = "http://pihole.example.test:8765"
ORIGIN = "http://pihole.example.test"
SIDEBAR = """<aside>
<ul class="sidebar-menu" data-widget="tree">
                <!-- Donate button -->
</ul>
</aside>
"""
HEADERS = [
    "X-Frame-Options: DENY",
    "Content-Security-Policy: default-src 'self'; frame-ancestors 'none'",
]


def _bash_has_mapfile():
    bash = shutil.which("bash")
    return bool(bash) and (
        subprocess.run([bash, "-c", "mapfile -t x < /dev/null"]).returncode == 0
    )


def executable(path, content):
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    path.chmod(0o755)


@unittest.skipUnless(tomllib and _bash_has_mapfile(), "Python 3.11+ and bash 4+ are required")
class _Sandbox(unittest.TestCase):
    origin = ORIGIN
    companion = COMPANION
    # Web releases the *installed* companion's adapter accepts; None means the
    # same code as the bundle under test.
    installed_supports = None

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.t = Path(temporary.name).resolve()
        self.state = self.t / "state"
        self.data = self.t / "var/lib/pihole-speedtest"
        self.recovery = self.t / "var/lib/pihole-speedtest-adapter-recovery"
        self.web = self.t / "var/www/html/admin"
        self.sidebar = self.web / "scripts/lua/sidebar.lp"
        self.pages = [self.web / "speedtest.lp", self.web / "speedtest-setup.lp"]
        self.toml = self.t / "etc/pihole/pihole.toml"
        for directory in (self.state, self.data, self.sidebar.parent, self.toml.parent,
                          self.t / "run", self.t / "bin"):
            directory.mkdir(parents=True, exist_ok=True)
        self.sidebar.write_text(SIDEBAR, encoding="utf-8")
        self.sidebar.chmod(0o644)
        self.write_headers(HEADERS)
        self.bundle = self.t / "bundle"
        self._build_bundle()
        self._write_stubs()
        for name in ("install-manifest.txt", "collection-manifest.txt"):
            path = self.data / name
            path.write_text(
                f"installed_at=20260926T031124Z\nsource_commit={INSTALLED_COMMIT}\n"
                f"pihole_origin={self.origin}\ncompanion_url={self.companion}\n"
                "pihole_adapter_installed=false\n",
                encoding="utf-8",
            )
            path.chmod(0o600)
        self.user_data = {
            self.data / "speedtest.db": b"SQLite format 3\x00 measurement history",
            self.data / "settings.json": b'{"collection_interval_minutes": 15}\n',
            self.data / "tls/companion.pem": b"companion TLS material",
        }
        for path, content in self.user_data.items():
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(content)

        # Reproduce production: a guarded install, then a filesystem-level
        # restore that left the recorded deployment state untouched.
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.historical = Path(self.value("pihole_adapter_manifest"))
        self.installed_headers = self.headers()
        shutil.copy2(self.historical.with_name("sidebar.lp.before"), self.sidebar)
        for page in self.pages:
            page.unlink()
        self.stale = self.records()
        self.evidence = self.tree(self.historical.parent)

    def _build_bundle(self):
        for relative in ("scripts/install_pihole_adapter.sh",
                         "scripts/remove_pihole_adapter.sh",
                         "scripts/reconcile_pihole_adapter.py"):
            (self.bundle / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, self.bundle / relative)
        shutil.copytree(ROOT / "src/pihole_speedtest", self.bundle / "src/pihole_speedtest",
                        ignore=shutil.ignore_patterns("__pycache__"))
        (self.bundle / "release").mkdir()
        (self.bundle / "release/SOURCE-COMMIT").write_text(SOURCE_COMMIT + "\n")
        sidebar_sha = hashlib.sha256(SIDEBAR.encode()).hexdigest()
        paths = re.compile(
            r"/(opt/pihole-speedtest|var/lib/pihole-speedtest|var/www/html/admin"
            r"|run/pihole-speedtest-adapter\.lock|etc/pihole/pihole\.toml)"
        )
        rewrites = {
            "scripts/install_pihole_adapter.sh": ['if [ "${EUID}" -ne 0 ]; then'],
            "scripts/remove_pihole_adapter.sh": ['if [ "${EUID}" -ne 0 ]; then'],
            "scripts/reconcile_pihole_adapter.py": ["ROOT_UID = 0"],
            "src/pihole_speedtest/adapter_reconcile.py": [],
        }
        for relative, required in rewrites.items():
            path = self.bundle / relative
            text = path.read_text(encoding="utf-8")
            for marker in required:
                self.assertIn(marker, text, f"{relative} changed; update the sandbox")
            text = paths.sub(lambda match: f"{self.t}/{match.group(1)}", text)
            text = text.replace(APPROVED, sidebar_sha)
            text = text.replace('if [ "${EUID}" -ne 0 ]; then', "if false; then")
            text = text.replace("ROOT_UID = 0", f"ROOT_UID = {os.getuid()}")
            path.write_text(text, encoding="utf-8")

    def _write_stubs(self):
        bin_dir, python, state = self.t / "bin", sys.executable, self.state
        real_grep = shutil.which("grep")
        scheme = self.companion.split(":", 1)[0]
        venv = self.t / "opt/pihole-speedtest/venv/bin"
        venv.mkdir(parents=True)
        installed_src = self.bundle / "src"
        if self.installed_supports is not None:
            installed_src = self.t / "installed-src"
            shutil.copytree(self.bundle / "src", installed_src)
            adapter = installed_src / "pihole_speedtest/adapter.py"
            text = adapter.read_text()
            gate = 'SUPPORTED_WEB_VERSIONS = frozenset({"v6.6", "v6.6.1"})'
            self.assertIn(gate, text)
            adapter.write_text(text.replace(gate, f"SUPPORTED_WEB_VERSIONS = {set(self.installed_supports)!r}"))
        # The installer runs the bundle's install_adapter through python3 -I.
        executable(bin_dir / "python3", f"""
            #!{python}
            import os, signal, sys
            args = sys.argv[1:]
            if (os.path.exists("{state}/kill-during-install") and args[:2] == ["-I", "-"]
                    and args[-1] == "{self.recovery}"):
                os.killpg(os.getpgrp(), signal.SIGKILL)  # simulated power loss
            os.execv("{python}", ["{python}", *args])
            """)
        executable(venv / "python", f"""
            #!/bin/sh
            PYTHONPATH="{installed_src}" exec "{python}" "$@"
            """)
        executable(venv / "pihole-speedtest", f"""
            #!{python}
            import sys
            sys.path.insert(0, "{installed_src}")
            from pihole_speedtest.cli import main
            sys.exit(main())
            """)
        executable(bin_dir / "systemctl", f"""
            #!{python}
            import sys
            args = [a for a in sys.argv[1:] if a not in ("--quiet", "--no-pager", "--no-legend")]
            if args[0] == "is-active":
                print("active")
            elif args[0] == "is-enabled":
                print("enabled")
            elif args[0] == "list-unit-files":
                print("pihole-speedtest-collect.timer enabled")
            elif args[0] != "status":
                sys.exit(2)
            """)
        executable(bin_dir / "curl", f"""
            #!{python}
            import json, os, sys, tomllib
            from urllib.parse import urlparse
            args, url = sys.argv[1:], sys.argv[-1]
            with open("{self.t}/curl.log", "a", encoding="utf-8") as log:
                log.write(json.dumps(args) + "\\n")
            target = urlparse(url)
            if target.scheme == "https":
                # TLS endpoints are reached only through the installer's loopback mechanism.
                if not any(a.startswith("-") and not a.startswith("--") and "k" in a for a in args):
                    sys.exit(60)
                if target.hostname != "127.0.0.1" and (
                    "--resolve" not in args
                    or args[args.index("--resolve") + 1] != f"{{target.hostname}}:443:127.0.0.1"
                ):
                    sys.exit(6)
            if url == "{scheme}://127.0.0.1:8765/api/health":
                ok = not os.path.exists("{state}/companion-unhealthy")
                print(json.dumps({{"status": "ok" if ok else "degraded", "version": "1.0.6"}}))
            elif url == "{scheme}://127.0.0.1:8765/":
                print("Content-Security-Policy: frame-ancestors 'self' {self.origin}")
            elif url == "{self.origin}/admin/":
                pass
            elif url == "{self.origin}/admin/speedtest":
                if not os.path.exists("{self.pages[0]}"):
                    sys.exit(22)
                if not os.path.exists("{state}/no-frame-policy"):
                    with open("{self.toml}", "rb") as source:
                        print("\\n".join(tomllib.load(source)["webserver"]["headers"]))
            else:
                sys.exit(22)
            """)
        # The first command after both deployment records name the new manifest.
        executable(bin_dir / "grep", f"""
            #!{python}
            import os, signal, sys
            if "BEGIN PIHOLE-SPEEDTEST-V6" in sys.argv[1:] and os.path.exists("{state}/kill-after-record"):
                os.killpg(os.getpgrp(), signal.SIGKILL)  # simulated power loss
            os.execv("{real_grep}", ["grep", *sys.argv[1:]])
            """)
        executable(bin_dir / "pihole", f"""
            #!/bin/sh
            case "$1" in
              -v) echo "Core version is v6.3"; echo "Web version is $(cat "{state}/web-version" 2>/dev/null || echo v6.6)" ;;
              status) echo "FTL is listening on port 53" ;;
              *) exit 2 ;;
            esac
            """)
        executable(bin_dir / "pihole-FTL", f"""
            #!{python}
            import sys
            if sys.argv[1:3] != ["--config", "webserver.headers"] or len(sys.argv) != 4:
                sys.exit(2)
            with open("{self.toml}", "w", encoding="utf-8") as target:
                target.write("[webserver]\\nheaders = " + sys.argv[3] + "\\n")
            """)
        executable(bin_dir / "sha256sum", f"""
            #!{python}
            import hashlib, sys
            for name in sys.argv[1:]:
                with open(name, "rb") as source:
                    print(hashlib.sha256(source.read()).hexdigest() + "  " + name)
            """)
        # Root ownership cannot be created unprivileged; report it as Debian stat would.
        executable(bin_dir / "stat", f"""
            #!{python}
            import os, sys
            assert sys.argv[1] == "-c"
            info = os.stat(sys.argv[3])
            print({{"%a": format(info.st_mode & 0o777, "o"), "%u:%g": "0:0"}}[sys.argv[2]])
            """)
        executable(bin_dir / "flock", f"""
            #!{python}
            import fcntl, sys
            assert sys.argv[1] == "-n"
            try:
                fcntl.flock(int(sys.argv[2]), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                sys.exit(1)
            """)
        executable(bin_dir / "sleep", "#!/bin/sh\nexit 0\n")

    def run_script(self, *command):
        environment = dict(os.environ, PATH=f"{self.t / 'bin'}:{os.environ['PATH']}")
        return subprocess.run(
            command, env=environment, cwd=self.t, start_new_session=True,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, timeout=120,
        )

    def install(self, companion=None):
        return self.run_script(
            "bash", str(self.bundle / "scripts/install_pihole_adapter.sh"),
            "--expected-source-commit", SOURCE_COMMIT,
            "--expected-installed-commit", INSTALLED_COMMIT,
            "--companion-url", companion or self.companion, "--pihole-origin", self.origin,
        )

    def remove(self):
        return self.run_script("bash", str(self.bundle / "scripts/remove_pihole_adapter.sh"))

    def helper(self, operation):
        return self.run_script(
            "python3", "-I", str(self.bundle / "scripts/reconcile_pihole_adapter.py"), operation
        )

    def write_headers(self, headers):
        self.toml.write_text("[webserver]\nheaders = " + json.dumps(headers) + "\n")

    def headers(self):
        with self.toml.open("rb") as source:
            return tomllib.load(source)["webserver"]["headers"]

    def value(self, key):
        lines = (self.data / "install-manifest.txt").read_text().splitlines()
        return [line.split("=", 1)[1] for line in lines if line.startswith(key + "=")][-1]

    def records(self):
        return {name: (self.data / name).read_bytes()
                for name in ("install-manifest.txt", "collection-manifest.txt")}

    @staticmethod
    def tree(directory):
        return {path.relative_to(directory): path.read_bytes()
                for path in sorted(directory.rglob("*")) if path.is_file()}

    def journals(self):
        return sorted(self.recovery.glob("reconciliation-*"))

    def assert_preserved(self):
        self.assertEqual(self.tree(self.historical.parent), self.evidence)
        for path, content in self.user_data.items():
            self.assertEqual(path.read_bytes(), content)

    @property
    def pending(self):
        return self.recovery / "reconciliation.pending.json"


    # Post-installation interruption: records name the new manifest, pending remains.

    def interrupt_after_record(self):
        (self.state / "kill-after-record").touch()
        result = self.install()
        (self.state / "kill-after-record").unlink()
        self.assertEqual(result.returncode, -9, result.stdout)
        new = Path(self.value("pihole_adapter_manifest"))
        self.assertNotEqual(new, self.historical)
        for content in self.records().values():
            self.assertIn(f"pihole_adapter_manifest={new}\n".encode(), content)
        self.assertTrue(self.pending.is_file())
        journal = self.journals()[-1]
        self.assertEqual(json.loads(self.pending.read_text())["journal"], str(journal))
        self.assertFalse((journal / "completed.json").exists())
        return new, journal


class GuardedInstallerReconciliationTests(_Sandbox):

    def test_restored_state_is_reconciled_and_reinstalled_with_new_evidence(self):
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stdout)

        new = Path(self.value("pihole_adapter_manifest"))
        self.assertNotEqual(new, self.historical)
        for content in self.records().values():
            self.assertIn(b"pihole_adapter_installed=true\n", content)
            self.assertIn(f"pihole_adapter_manifest={new}\n".encode(), content)
        (journal,) = self.journals()
        self.assertEqual(self.value("pihole_adapter_reconciliation"), str(journal))
        for name in ("reconciliation.json", "completed.json",
                     "install-manifest.txt", "collection-manifest.txt"):
            self.assertTrue((journal / name).is_file(), name)
        self.assertEqual((journal / "install-manifest.txt").read_bytes(),
                         self.stale["install-manifest.txt"])
        evidence = json.loads((journal / "reconciliation.json").read_text())
        self.assertEqual(evidence["historical_manifest"], str(self.historical))
        self.assertFalse((self.recovery / "reconciliation.pending.json").exists())
        self.assertTrue(all(page.is_file() for page in self.pages))
        self.assertEqual(self.headers(), self.installed_headers)
        # The new removal record restores the original pre-adapter header policy.
        self.assertEqual(json.loads(new.with_name("pihole-web-headers.before.json").read_text()),
                         HEADERS)
        self.assert_preserved()

        # A healthy installation is never reconciled again.
        healthy = self.records()
        repeat = self.install()
        self.assertNotEqual(repeat.returncode, 0)
        self.assertIn("Adapter reconciliation refused", repeat.stdout)
        self.assertEqual(self.records(), healthy)
        self.assertEqual(self.journals(), [journal])

        # Existing removal reverses the repaired adapter to the true original.
        removal = self.remove()
        self.assertEqual(removal.returncode, 0, removal.stdout)
        self.assertEqual(self.sidebar.read_text(), SIDEBAR)
        self.assertFalse(any(page.exists() for page in self.pages))
        self.assertEqual(self.headers(), HEADERS)
        self.assertEqual(self.value("pihole_adapter_installed"), "false")
        self.assert_preserved()

    def test_restored_headers_are_also_accepted(self):
        self.write_headers(HEADERS)
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.headers(), self.installed_headers)

    def test_failed_reinstall_rolls_back_and_restores_the_stale_record(self):
        (self.state / "no-frame-policy").touch()
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Pre-reconciliation deployment records restored", result.stdout)
        self.assertEqual(self.records(), self.stale)
        self.assertEqual(self.sidebar.read_text(), SIDEBAR)
        self.assertFalse(any(page.exists() or page.is_symlink() for page in self.pages))
        self.assertEqual(self.headers(), self.installed_headers)
        self.assertFalse((self.recovery / "reconciliation.pending.json").exists())
        (journal,) = self.journals()
        self.assertTrue((journal / "recovered.json").is_file())
        self.assert_preserved()

        (self.state / "no-frame-policy").unlink()
        retry = self.install()
        self.assertEqual(retry.returncode, 0, retry.stdout)
        self.assertEqual(len(self.journals()), 2)
        self.assert_preserved()

    def test_interrupted_reconciliation_blocks_until_verified_recovery(self):
        (self.state / "kill-during-install").touch()
        result = self.install()
        self.assertEqual(result.returncode, -9)
        self.assertTrue((self.recovery / "reconciliation.pending.json").is_file())
        self.assertEqual(self.value("pihole_adapter_installed"), "false")

        blocked = self.install()
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("Interrupted reconciliation", blocked.stdout)
        self.assertEqual(len(self.journals()), 1)
        self.assertNotEqual(self.remove().returncode, 0)

        recovered = self.helper("recover")
        self.assertEqual(recovered.returncode, 0, recovered.stdout)
        self.assertEqual(self.records(), self.stale)
        self.assertFalse((self.recovery / "reconciliation.pending.json").exists())
        self.assertNotEqual(self.helper("recover").returncode, 0)  # nothing pending

        (self.state / "kill-during-install").unlink()
        retry = self.install()
        self.assertEqual(retry.returncode, 0, retry.stdout)
        self.assert_preserved()

    def test_unsafe_live_states_are_refused_before_any_change(self):
        def one_page():
            self.pages[1].write_text("unexpected wrapper content")

        def custom_sidebar():
            self.sidebar.write_text(SIDEBAR.replace("<aside>", "<aside class='custom'>"))

        def changed_headers():
            self.write_headers(HEADERS + ["X-Custom: operator change"])

        def newer_web():
            (self.state / "web-version").write_text("v6.7")

        def unhealthy_companion():
            (self.state / "companion-unhealthy").touch()

        def unsafe_manifest_reference():
            for name in self.stale:
                path = self.data / name
                path.write_text(path.read_text().replace(
                    str(self.historical), str(self.historical.parent / ".." / "x/manifest.json")))

        cases = {
            "one page present": (one_page, None),
            "custom sidebar": (custom_sidebar, None),
            "changed headers": (changed_headers, None),
            "newer Pi-hole web": (newer_web, None),
            "unhealthy companion": (unhealthy_companion, None),
            "different companion URL": (lambda: None, "http://other.example.test:8765"),
            "unsafe manifest reference": (unsafe_manifest_reference, None),
        }
        for label, (mutate, companion) in cases.items():
            with self.subTest(label):
                web_before = self.tree(self.web)
                headers_before = self.toml.read_bytes()
                mutate()
                records = self.records()
                recovery = sorted(self.recovery.iterdir())
                web = self.tree(self.web)
                result = self.install(companion)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertEqual(self.records(), records)
                self.assertEqual(sorted(self.recovery.iterdir()), recovery)
                self.assertEqual(self.tree(self.web), web)
                self.assertEqual(self.journals(), [])
                self.assert_preserved()
                # Reset for the next case.
                for name, content in self.stale.items():
                    (self.data / name).write_bytes(content)
                for page in self.pages:
                    page.unlink(missing_ok=True)
                self.sidebar.write_text(SIDEBAR)
                self.assertEqual(self.tree(self.web), web_before)
                self.toml.write_bytes(headers_before)
                for flag in self.state.iterdir():
                    flag.unlink()


    def test_kill_point_is_after_both_records_and_before_completion(self):
        script = (ROOT / "scripts/install_pihole_adapter.sh").read_text()
        record = script.index("state_updated=1")
        hook = script.index("grep -q 'BEGIN PIHOLE-SPEEDTEST-V6' \"$sidebar\"")
        self.assertLess(record, hook)
        self.assertLess(hook, script.index('(journal / "completed.json")'))
        self.assertEqual(script.count("BEGIN PIHOLE-SPEEDTEST-V6"), 1)

    def test_power_loss_after_records_is_finalized_by_recover(self):
        new, journal = self.interrupt_after_record()
        web, records, headers = self.tree(self.web), self.records(), self.toml.read_bytes()

        blocked = self.install()
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("Interrupted reconciliation", blocked.stdout)
        self.assertNotEqual(self.remove().returncode, 0)

        result = self.helper("recover")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Verified adapter installation finalized", result.stdout)
        self.assertFalse(self.pending.exists())
        completed = json.loads((journal / "completed.json").read_text())
        self.assertEqual(completed["installed_manifest"], str(new))
        self.assertTrue((journal / "finalized.json").is_file())
        # Finalization changes no web file, header policy or deployment record.
        self.assertEqual(self.tree(self.web), web)
        self.assertEqual(self.records(), records)
        self.assertEqual(self.toml.read_bytes(), headers)
        self.assert_preserved()

        journal_files = self.tree(journal)
        again = self.helper("recover")
        self.assertNotEqual(again.returncode, 0)
        self.assertIn("nothing to recover", again.stdout)
        self.assertEqual(self.tree(journal), journal_files)
        self.assertEqual(self.records(), records)

        removal = self.remove()
        self.assertEqual(removal.returncode, 0, removal.stdout)
        self.assertEqual(self.sidebar.read_text(), SIDEBAR)
        self.assertFalse(any(page.exists() for page in self.pages))
        self.assertEqual(self.headers(), HEADERS)
        self.assertEqual(self.value("pihole_adapter_installed"), "false")
        self.assert_preserved()

    def test_interruption_after_completion_record_and_repeated_recovery(self):
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stdout)
        (journal,) = self.journals()
        completed = (journal / "completed.json").read_bytes()
        web, records = self.tree(self.web), self.records()
        for attempt in range(2):
            with self.subTest(attempt=attempt):
                # Power loss before the pending marker's removal reached disk.
                self.pending.write_text(json.dumps({"journal": str(journal)}) + "\n")
                self.pending.chmod(0o600)
                recovered = self.helper("recover")
                self.assertEqual(recovered.returncode, 0, recovered.stdout)
                self.assertIn("finalized", recovered.stdout)
                self.assertFalse(self.pending.exists())
                self.assertEqual((journal / "completed.json").read_bytes(), completed)
                self.assertEqual(self.tree(self.web), web)
                self.assertEqual(self.records(), records)
        self.assert_preserved()

    def test_finalization_refuses_modified_or_inconsistent_installs(self):
        new, journal = self.interrupt_after_record()
        collection = self.data / "collection-manifest.txt"
        snapshot = new.with_name("install-manifest.before.txt")

        def edit(path, change):
            content = path.read_bytes()
            change(path)
            return lambda: path.write_bytes(content)

        def append(path, text):
            return edit(path, lambda p: p.write_text(p.read_text() + text))

        def chmod(path, mode):
            original = path.stat().st_mode & 0o777
            path.chmod(mode)
            return lambda: path.chmod(original)

        def replace_with_symlink(path):
            content = path.read_bytes()
            target = path.with_name("elsewhere.txt")
            target.write_bytes(content)
            path.unlink()
            path.symlink_to(target)

            def undo():
                path.unlink()
                target.unlink()
                path.write_bytes(content)
                path.chmod(0o600)
            return undo

        def json_edit(path, change):
            def apply(p):
                value = json.loads(p.read_text())
                change(value)
                p.write_text(json.dumps(value))
            return edit(path, apply)

        def completion(manifest):
            path = journal / "completed.json"
            path.write_text(json.dumps({"installed_manifest": manifest}))
            path.chmod(0o600)
            return path.unlink

        cases = {
            "modified sidebar": lambda: append(self.sidebar, "<!-- local -->\n"),
            "modified overview page": lambda: append(self.pages[0], "<!-- local -->\n"),
            "modified setup page": lambda: append(self.pages[1], "<!-- local -->\n"),
            "disagreeing records": lambda: edit(collection, lambda p: p.write_text(
                p.read_text().replace(str(new), str(self.historical)))),
            "unrelated record change": lambda: append(collection, "operator=change\n"),
            "untrusted new manifest": lambda: chmod(new, 0o666),
            "inconsistent new manifest": lambda: json_edit(
                new, lambda m: m.update(pihole_origin="http://elsewhere.example.test")),
            "inconsistent pre-install snapshot": lambda: append(snapshot, "extra=value\n"),
            "symlinked pre-install snapshot": lambda: replace_with_symlink(snapshot),
            "changed historical evidence": lambda: append(
                self.historical.with_name("collection-manifest.before.txt"), "late=edit\n"),
            "completion record for another manifest": lambda: completion(str(self.historical)),
        }
        for label, mutate in cases.items():
            with self.subTest(label):
                undo = mutate()
                web, records = self.tree(self.web), self.records()
                pending = self.pending.read_bytes()
                journal_files = self.tree(journal)
                result = self.helper("recover")
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("Adapter reconciliation refused", result.stdout)
                self.assertEqual(self.pending.read_bytes(), pending)
                self.assertEqual(self.tree(journal), journal_files)
                self.assertEqual(self.tree(self.web), web)
                self.assertEqual(self.records(), records)
                undo()
        # With every mutation undone, the verified state finalizes.
        result = self.helper("recover")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("finalized", result.stdout)


class HttpsReconciliationTests(_Sandbox):
    origin = "https://pi.hole"
    companion = "https://pi.hole:8765"

    def test_https_reconciliation_uses_tls_aware_requests(self):
        log = self.t / "curl.log"
        log.unlink()
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stdout)
        (journal,) = self.journals()
        self.assertTrue((journal / "completed.json").is_file())
        self.assertIn("frame-src https://pi.hole:8765", "\n".join(self.headers()))
        requests = [json.loads(line) for line in log.read_text().splitlines()]
        pihole = [r for r in requests if r[-1].startswith("https://pi.hole/")]
        companion = [r for r in requests if r[-1].startswith("https://127.0.0.1:8765/")]
        self.assertIn("https://pi.hole/admin/", [r[-1] for r in pihole])
        self.assertIn("https://pi.hole/admin/speedtest", [r[-1] for r in pihole])
        self.assertTrue(companion)
        for request in pihole:
            self.assertEqual(request[request.index("--resolve") + 1], "pi.hole:443:127.0.0.1")
        self.assertFalse([r for r in requests if r[-1].startswith("http://")])
        self.assert_preserved()

    def test_https_frame_policy_failure_restores_the_stale_record(self):
        (self.state / "no-frame-policy").touch()
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("did not serve the installed companion frame policy", result.stdout)
        self.assertIn("Pre-reconciliation deployment records restored", result.stdout)
        self.assertEqual(self.records(), self.stale)
        self.assertFalse(self.pending.exists())
        self.assert_preserved()



class ProductionShapedUpgradeTests(_Sandbox):
    """Historical v6.6 evidence, live Web upgraded to v6.6.1, HTTPS origins."""

    origin = "https://pi.hole"
    companion = "https://pi.hole:8765"
    installed_supports = ("v6.6",)  # companion v1.0.6 (fea0efe) on the Pi

    def setUp(self):
        super().setUp()
        self.upgrade("v6.6.1")

    def upgrade(self, version):
        (self.state / "web-version").write_text(version)

    def manifest(self, path):
        return json.loads(Path(path).read_text())

    def assert_tls_requests(self):
        requests = [json.loads(line) for line in (self.t / "curl.log").read_text().splitlines()]
        pihole = [r for r in requests if r[-1].startswith("https://pi.hole/")]
        self.assertIn("https://pi.hole/admin/speedtest", [r[-1] for r in pihole])
        for request in pihole:
            self.assertEqual(request[request.index("--resolve") + 1], "pi.hole:443:127.0.0.1")
        self.assertFalse([r for r in requests if r[-1].startswith("http://")])

    def test_v66_evidence_reconciles_on_v661_then_installs_and_removes(self):
        self.assertEqual(self.manifest(self.historical)["web_version"], "v6.6")
        (self.t / "curl.log").unlink()
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assert_tls_requests()
        new = Path(self.value("pihole_adapter_manifest"))
        self.assertEqual(self.manifest(new)["web_version"], "v6.6.1")
        # The historical v6.6 evidence is accepted as written, never rewritten.
        self.assertEqual(self.manifest(self.historical)["web_version"], "v6.6")
        self.assert_preserved()
        (journal,) = self.journals()
        self.assertTrue((journal / "completed.json").is_file())
        self.assertIn("frame-src https://pi.hole:8765", "\n".join(self.headers()))

        removal = self.remove()
        self.assertEqual(removal.returncode, 0, removal.stdout)
        self.assertEqual(self.sidebar.read_text(), SIDEBAR)
        self.assertEqual(self.headers(), HEADERS)

        # A plain install on v6.6.1 after removal records the live release.
        fresh = self.install()
        self.assertEqual(fresh.returncode, 0, fresh.stdout)
        self.assertEqual(self.manifest(self.value("pihole_adapter_manifest"))["web_version"], "v6.6.1")
        self.assertEqual(len(self.journals()), 1)
        self.assertEqual(self.remove().returncode, 0)
        self.assertEqual(self.sidebar.read_text(), SIDEBAR)
        self.assert_preserved()

    def test_unapproved_releases_or_sidebar_are_refused_before_any_change(self):
        cases = {f"Web {v or 'unknown'}": (v, None) for v in
                 ("v6.6.2", "v6.7", "v6.5", "v6.6.1-rc1", "v6.6.10", "")}
        cases["unexpected sidebar on v6.6.1"] = ("v6.6.1", "<!-- local -->\n")
        for label, (version, sidebar_suffix) in cases.items():
            with self.subTest(label):
                self.upgrade(version)
                if sidebar_suffix:
                    self.sidebar.write_text(SIDEBAR + sidebar_suffix)
                records, web = self.records(), self.tree(self.web)
                recovery = sorted(self.recovery.iterdir())
                result = self.install()
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("STOP:", result.stdout)
                self.assertEqual(self.records(), records)
                self.assertEqual(self.tree(self.web), web)
                self.assertEqual(sorted(self.recovery.iterdir()), recovery)
                self.sidebar.write_text(SIDEBAR)
        self.upgrade("v6.6.1")
        self.assertEqual(self.install().returncode, 0)

    def test_failed_reinstall_on_v661_restores_the_stale_record(self):
        (self.state / "no-frame-policy").touch()
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Pre-reconciliation deployment records restored", result.stdout)
        self.assertEqual(self.records(), self.stale)
        self.assertEqual(self.headers(), self.installed_headers)
        self.assertFalse(self.pending.exists())
        self.assert_preserved()

    def test_interruptions_on_v661_recover_and_repeat_safely(self):
        (self.state / "kill-during-install").touch()
        self.assertEqual(self.install().returncode, -9)
        (self.state / "kill-during-install").unlink()
        restored = self.helper("recover")
        self.assertIn("Pre-reconciliation deployment records restored", restored.stdout)
        self.assertEqual(self.records(), self.stale)

        new, journal = self.interrupt_after_record()
        self.assertEqual(self.manifest(new)["web_version"], "v6.6.1")
        finalized = self.helper("recover")
        self.assertEqual(finalized.returncode, 0, finalized.stdout)
        self.assertIn("Verified adapter installation finalized", finalized.stdout)
        records, web = self.records(), self.tree(self.web)
        self.assertIn("nothing to recover", self.helper("recover").stdout)
        self.assertEqual((self.records(), self.tree(self.web)), (records, web))
        self.assertEqual(self.remove().returncode, 0)
        self.assertEqual(self.headers(), HEADERS)
        self.assert_preserved()

    def test_tampered_historical_evidence_is_refused_on_v661(self):
        manifest = self.historical.read_bytes()
        value = json.loads(manifest)
        value["web_version"] = "v6.7"
        self.historical.write_text(json.dumps(value))
        records = self.records()
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Adapter reconciliation refused", result.stdout)
        self.assertEqual(self.records(), records)
        self.assertEqual(self.journals(), [])
        self.historical.write_bytes(manifest)

        self.interrupt_after_record()
        before = self.historical.with_name("pihole-web-headers.before.json")
        content = before.read_bytes()
        before.write_text(json.dumps(HEADERS, indent=1))  # same value, different bytes
        refused = self.helper("recover")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("evidence changed", refused.stdout)
        self.assertTrue(self.pending.is_file())
        before.write_bytes(content)
        self.assertIn("finalized", self.helper("recover").stdout)

if __name__ == "__main__":
    unittest.main()

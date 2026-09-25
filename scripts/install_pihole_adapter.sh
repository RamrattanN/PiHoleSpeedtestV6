#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: sudo scripts/install_pihole_adapter.sh \
  --expected-source-commit SHA \
  --expected-installed-commit SHA \
  --companion-url URL \
  --pihole-origin ORIGIN

Installs the version-gated Pi-hole Web v6.6 sidebar adapter, verifies the
result, and records its recovery manifest in the companion deployment state.
EOF
}

expected_source_commit=""
expected_installed_commit=""
companion_url=""
pihole_origin=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --expected-source-commit) expected_source_commit="$2"; shift 2 ;;
    --expected-installed-commit) expected_installed_commit="$2"; shift 2 ;;
    --companion-url) companion_url="$2"; shift 2 ;;
    --pihole-origin) pihole_origin="$2"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [ "${EUID}" -ne 0 ]; then
  echo "STOP: Run this command with sudo." >&2
  exit 1
fi
if ! [[ "$expected_source_commit" =~ ^[0-9a-f]{40}$ ]] ||
  ! [[ "$expected_installed_commit" =~ ^[0-9a-f]{40}$ ]]
then
  echo "STOP: Both commit arguments must be full lowercase Git SHAs." >&2
  exit 1
fi
if [ -z "$companion_url" ] || [ -z "$pihole_origin" ]; then
  echo "STOP: Both --companion-url and --pihole-origin are required." >&2
  exit 1
fi

source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
source_commit="$(git -C "$source_root" rev-parse HEAD 2>/dev/null || true)"
if [ -z "$source_commit" ] && [ -f "$source_root/release/SOURCE-COMMIT" ]; then
  source_commit="$(tr -d '\r\n' < "$source_root/release/SOURCE-COMMIT")"
fi
if [ "$source_commit" != "$expected_source_commit" ]; then
  echo "STOP: Source commit does not match the approved commit." >&2
  exit 1
fi
if [ -d "$source_root/.git" ]; then
  if ! git -C "$source_root" diff --quiet -- ||
    ! git -C "$source_root" diff --cached --quiet --
  then
    echo "STOP: Source worktree has tracked changes." >&2
    exit 1
  fi
fi

application_cli="/opt/pihole-speedtest/venv/bin/pihole-speedtest"
application_python="/opt/pihole-speedtest/venv/bin/python"
data_dir="/var/lib/pihole-speedtest"
install_manifest="${data_dir}/install-manifest.txt"
collection_manifest="${data_dir}/collection-manifest.txt"
web_root="/var/www/html/admin"
sidebar="${web_root}/scripts/lua/sidebar.lp"
overview="${web_root}/speedtest.lp"
setup="${web_root}/speedtest-setup.lp"
backup_root="/var/lib/pihole-speedtest-adapter-recovery"
expected_sidebar_sha="83943cbdf5258fe43e819108a5135e070d6742e273753ba398a8d28e1a008fdb"
dashboard_unit="pihole-speedtest-dashboard.service"
timer_unit="pihole-speedtest-collect.timer"
adapter_manifest=""
adapter_installed=0
state_updated=0
header_policy_attempted=0
headers_before=""
headers_installed=""

for command in python3 systemctl curl sha256sum pihole pihole-FTL stat tr; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "STOP: Required command is unavailable: $command" >&2
    exit 1
  }
done

mapfile -t validated_origins < <(python3 - "$companion_url" "$pihole_origin" <<'PY'
import sys
from urllib.parse import urlparse


def origin(value, label):
    parsed = urlparse(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise SystemExit(f"STOP: {label} must be an HTTP(S) origin without a path, credentials, query, or fragment.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise SystemExit(f"STOP: {label} has an invalid port: {exc}") from exc
    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    port_text = f":{port}" if port is not None else ""
    return f"{parsed.scheme.lower()}://{host}{port_text}"


companion = origin(sys.argv[1], "companion URL")
pihole = origin(sys.argv[2], "Pi-hole origin")
if pihole.startswith("https://") and companion.startswith("http://"):
    raise SystemExit("STOP: An HTTPS Pi-hole page cannot embed an HTTP companion dashboard.")
print(companion)
print(pihole)
PY
)
if [ "${#validated_origins[@]}" -ne 2 ]; then
  echo "STOP: Origin validation did not return the expected values." >&2
  exit 1
fi
companion_url="${validated_origins[0]}"
pihole_origin="${validated_origins[1]}"

companion_curl() {
  path="$1"
  shift
  if [[ "$companion_url" == https://* ]]; then
    curl -kfsS "$@" "https://127.0.0.1:8765${path}"
  else
    curl -fsS "$@" "http://127.0.0.1:8765${path}"
  fi
}

pihole_curl() {
  path="$1"
  shift
  if [[ "$pihole_origin" == https://* ]]; then
    mapfile -t target < <(python3 - "$pihole_origin" <<'PY'
import sys
from urllib.parse import urlparse

parsed = urlparse(sys.argv[1])
print(parsed.hostname)
print(parsed.port or 443)
PY
)
    curl -kfsS --resolve "${target[0]}:${target[1]}:127.0.0.1" \
      "$@" "$pihole_origin${path}"
  else
    curl -fsS "$@" "$pihole_origin${path}"
  fi
}
for path in "$application_cli" "$install_manifest" "$collection_manifest" "$sidebar"; do
  if [ ! -e "$path" ]; then
    echo "STOP: Required installed target is missing: $path" >&2
    exit 1
  fi
done

installed_commit="$(sed -n 's/^source_commit=//p' "$install_manifest")"
if [ "$installed_commit" != "$expected_installed_commit" ]; then
  echo "STOP: Installed commit does not match the approved baseline." >&2
  echo "Expected: $expected_installed_commit" >&2
  echo "Actual:   ${installed_commit:-unknown}" >&2
  exit 1
fi
if [ "$(sed -n 's/^pihole_adapter_installed=//p' "$install_manifest")" != "false" ]; then
  echo "STOP: Deployment manifest does not record an absent adapter." >&2
  exit 1
fi
if grep -q '^pihole_adapter_manifest=' "$install_manifest"; then
  echo "STOP: Deployment manifest already records an adapter recovery manifest." >&2
  exit 1
fi
for unit in "$dashboard_unit" "$timer_unit"; do
  if [ "$(systemctl is-active "$unit")" != "active" ] ||
    [ "$(systemctl is-enabled "$unit")" != "enabled" ]
  then
    echo "STOP: Required unit is not active and enabled: $unit" >&2
    exit 1
  fi
done
if [ "$(sha256sum "$sidebar" | awk '{print $1}')" != "$expected_sidebar_sha" ]; then
  echo "STOP: Live Pi-hole v6.6 sidebar checksum is not approved." >&2
  exit 1
fi
if grep -q 'PIHOLE-SPEEDTEST-V6' "$sidebar" || [ -e "$overview" ] || [ -e "$setup" ]; then
  echo "STOP: Adapter markers or target pages already exist." >&2
  exit 1
fi
installed_web_version="$(python3 - <<'PY'
import re
import subprocess


completed = subprocess.run(
    ["pihole", "-v"],
    check=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
)
plain = re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", completed.stdout)
match = re.search(r"(?m)^Web version is (v\S+)", plain)
if match:
    print(match.group(1))
PY
)"
if [ "$installed_web_version" != "v6.6" ]; then
  echo "STOP: Installed Pi-hole Web version is not v6.6." >&2
  echo "Detected: ${installed_web_version:-unknown}" >&2
  exit 1
fi
companion_curl /api/health >/dev/null
companion_curl / -D - -o /dev/null |
  tr -d '\r' |
  grep -Fq "frame-ancestors 'self' $pihole_origin" || {
    echo "STOP: Companion frame policy does not allow $pihole_origin." >&2
    exit 1
  }

rollback() {
  status=$?
  if [ "$status" -eq 0 ]; then
    return
  fi
  trap - EXIT
  echo >&2
  echo "Sidebar adapter installation failed.  Restoring the prior state..." >&2
  if [ "$header_policy_attempted" -eq 1 ] && [ -s "$headers_before" ]; then
    pihole-FTL --config webserver.headers "$(cat "$headers_before")" >/dev/null 2>&1 || true
  fi
  if [ "$adapter_installed" -eq 1 ] && [ -n "$adapter_manifest" ]; then
    "$application_cli" adapter-remove --manifest "$adapter_manifest" >/dev/null 2>&1 || true
  fi
  if [ "$state_updated" -eq 1 ] && [ -n "$adapter_manifest" ]; then
    recovery_dir="$(dirname "$adapter_manifest")"
    cp -a "$recovery_dir/install-manifest.before.txt" "$install_manifest" 2>/dev/null || true
    cp -a "$recovery_dir/collection-manifest.before.txt" "$collection_manifest" 2>/dev/null || true
  fi
  echo "Rollback attempt finished.  Pi-hole status follows:" >&2
  pihole status >&2 || true
  exit "$status"
}
trap rollback EXIT

install_output="$($application_cli adapter-install \
  --web-root "$web_root" \
  --web-version v6.6 \
  --companion-url "$companion_url" \
  --backup-root "$backup_root")"
adapter_manifest="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["manifest"])' <<<"$install_output")"
if [ -z "$adapter_manifest" ] || [ ! -f "$adapter_manifest" ]; then
  echo "STOP: Adapter recovery manifest was not created." >&2
  exit 1
fi
adapter_installed=1
recovery_dir="$(dirname "$adapter_manifest")"
cp -a "$install_manifest" "$recovery_dir/install-manifest.before.txt"
cp -a "$collection_manifest" "$recovery_dir/collection-manifest.before.txt"
headers_before="$recovery_dir/pihole-web-headers.before.json"
headers_installed="$recovery_dir/pihole-web-headers.installed.json"

"$application_python" - \
  /etc/pihole/pihole.toml \
  "$companion_url" \
  "$headers_before" \
  "$headers_installed" <<'PY'
import json
import os
import pathlib
import sys
import tomllib

from pihole_speedtest.pihole_headers import allow_companion_frame


config_path, companion_url, before_path, installed_path = sys.argv[1:]
with open(config_path, "rb") as source:
    headers = tomllib.load(source)["webserver"]["headers"]
installed = allow_companion_frame(headers, companion_url)
for path, value in ((before_path, headers), (installed_path, installed)):
    target = pathlib.Path(path)
    target.write_text(json.dumps(value, separators=(",", ":")) + "\n", encoding="utf-8")
    os.chmod(target, 0o600)
PY

header_policy_attempted=1
pihole-FTL --config webserver.headers "$(cat "$headers_installed")"

"$application_python" - /etc/pihole/pihole.toml "$headers_installed" <<'PY'
import json
import sys
import tomllib


with open(sys.argv[1], "rb") as source:
    actual = tomllib.load(source)["webserver"]["headers"]
with open(sys.argv[2], encoding="utf-8") as source:
    expected = json.load(source)
if actual != expected:
    raise SystemExit("Pi-hole web header configuration did not match the installed policy")
PY

policy_verified=0
for _ in {1..20}; do
  if pihole_curl /admin/speedtest -D - -o /dev/null |
    tr -d '\r' |
    grep -Fq "frame-src $companion_url"
  then
    policy_verified=1
    break
  fi
  sleep 1
done
if [ "$policy_verified" -ne 1 ]; then
  echo "STOP: Pi-hole did not serve the installed companion frame policy." >&2
  exit 1
fi

python3 - "$adapter_manifest" <<'PY'
import hashlib
import json
import pathlib
import stat
import sys


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


manifest = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
sidebar = pathlib.Path(manifest["sidebar"]["path"])
if sha256(sidebar) != manifest["sidebar"]["installed_sha256"]:
    raise SystemExit("installed sidebar checksum verification failed")
paths = [sidebar]
for created in manifest["created"]:
    path = pathlib.Path(created["path"])
    if sha256(path) != created["sha256"]:
        raise SystemExit(f"installed adapter page checksum verification failed: {path}")
    paths.append(path)
for path in paths:
    if stat.S_IMODE(path.stat().st_mode) != 0o644:
        raise SystemExit(f"installed web path is not mode 0644: {path}")
PY

state_updated=1
python3 - "$install_manifest" "$collection_manifest" "$adapter_manifest" <<'PY'
import os
import pathlib
import tempfile
import sys


for raw_path in sys.argv[1:3]:
    path = pathlib.Path(raw_path)
    lines = [
        line for line in path.read_text(encoding="utf-8").splitlines()
        if not line.startswith("pihole_adapter_installed=")
        and not line.startswith("pihole_adapter_manifest=")
    ]
    lines.extend(("pihole_adapter_installed=true", f"pihole_adapter_manifest={sys.argv[3]}"))
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
            destination.write("\n".join(lines) + "\n")
            destination.flush()
            os.fsync(destination.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
PY

grep -q 'BEGIN PIHOLE-SPEEDTEST-V6' "$sidebar"
grep -q 'END PIHOLE-SPEEDTEST-V6' "$sidebar"
test "$(stat -c '%a' "$sidebar")" = "644"
test "$(stat -c '%a' "$overview")" = "644"
test "$(stat -c '%a' "$setup")" = "644"
test "$(stat -c '%u:%g' "$sidebar")" = "0:0"
test "$(stat -c '%u:%g' "$overview")" = "0:0"
test "$(stat -c '%u:%g' "$setup")" = "0:0"
curl -fsS http://127.0.0.1:8765/api/health > "$recovery_dir/health.after.json"
pihole status > "$recovery_dir/pihole-status.after.txt"
systemctl status "$dashboard_unit" --no-pager > "$recovery_dir/dashboard-status.after.txt"
systemctl status "$timer_unit" --no-pager > "$recovery_dir/timer-status.after.txt"

echo "$install_output"
echo
echo "=== LIVE PI-HOLE SIDEBAR ADAPTER INSTALLED ==="
echo "Recovery manifest: $adapter_manifest"
echo "Overview: $pihole_origin/admin/speedtest"
echo "Setup: $pihole_origin/admin/speedtest-setup"
echo "Pi-hole frame policy: exact prior value archived and companion origin allowed"
echo "Companion dashboard and collection timer: active and enabled"
echo "Pi-hole status: verified"

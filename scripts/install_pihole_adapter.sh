#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: sudo scripts/install_pihole_adapter.sh \
  --expected-source-commit SHA \
  --expected-installed-commit SHA \
  --companion-url URL

Installs the version-gated Pi-hole Web v6.6 sidebar adapter, verifies the
result, and records its recovery manifest in the companion deployment state.
EOF
}

expected_source_commit=""
expected_installed_commit=""
companion_url=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --expected-source-commit) expected_source_commit="$2"; shift 2 ;;
    --expected-installed-commit) expected_installed_commit="$2"; shift 2 ;;
    --companion-url) companion_url="$2"; shift 2 ;;
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
if [ "$companion_url" != "http://192.168.2.14:8765" ]; then
  echo "STOP: Companion URL does not match the approved Pi deployment." >&2
  exit 1
fi

source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
source_commit="$(git -C "$source_root" rev-parse HEAD 2>/dev/null || true)"
if [ "$source_commit" != "$expected_source_commit" ]; then
  echo "STOP: Source commit does not match the approved commit." >&2
  exit 1
fi
if ! git -C "$source_root" diff --quiet -- ||
  ! git -C "$source_root" diff --cached --quiet --
then
  echo "STOP: Source worktree has tracked changes." >&2
  exit 1
fi

application_cli="/opt/pihole-speedtest/venv/bin/pihole-speedtest"
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

for command in git python3 systemctl curl sha256sum pihole stat; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "STOP: Required command is unavailable: $command" >&2
    exit 1
  }
done
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
if ! pihole -v | grep -q '^Web version is v6\.6 '; then
  echo "STOP: Installed Pi-hole Web version is not v6.6." >&2
  exit 1
fi
curl -fsS http://127.0.0.1:8765/api/health >/dev/null
curl -fsS -D - -o /dev/null http://127.0.0.1:8765/ |
  tr -d '\r' |
  grep -Fq "frame-ancestors 'self' http://192.168.2.14" || {
    echo "STOP: Companion frame policy does not allow the approved Pi-hole origin." >&2
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
echo "Overview: http://192.168.2.14/admin/speedtest"
echo "Setup: http://192.168.2.14/admin/speedtest-setup"
echo "Companion dashboard and collection timer: active and enabled"
echo "Pi-hole status: verified"

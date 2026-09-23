#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: sudo scripts/upgrade_and_enable_collection.sh \
  --expected-source-commit SHA \
  --expected-installed-commit SHA \
  --expected-count NUMBER \
  --interval-minutes NUMBER

Upgrades an approved dashboard-only installation, verifies the authenticated
manual speed-test API with one measurement, and enables the schedule-aware
collection timer.  Pi-hole web files are not modified.
EOF
}

expected_source_commit=""
expected_installed_commit=""
expected_count=""
interval_minutes=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --expected-source-commit) expected_source_commit="$2"; shift 2 ;;
    --expected-installed-commit) expected_installed_commit="$2"; shift 2 ;;
    --expected-count) expected_count="$2"; shift 2 ;;
    --interval-minutes) interval_minutes="$2"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [ "${EUID}" -ne 0 ]; then
  echo "STOP: Run this command with sudo." >&2
  exit 1
fi
for value in expected_count interval_minutes; do
  if ! [[ "${!value}" =~ ^[0-9]+$ ]]; then
    echo "STOP: --${value//_/-} must be a non-negative integer." >&2
    exit 1
  fi
done
if ! [[ "$expected_source_commit" =~ ^[0-9a-f]{40}$ ]] ||
  ! [[ "$expected_installed_commit" =~ ^[0-9a-f]{40}$ ]]
then
  echo "STOP: Both commit arguments must be full lowercase Git SHAs." >&2
  exit 1
fi
case "$interval_minutes" in
  15|30|60|120|240|360|720|1440) ;;
  *) echo "STOP: Unsupported collection interval: $interval_minutes" >&2; exit 1 ;;
esac

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
for command in python3 systemctl curl sha256sum runuser pihole git grep find; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "STOP: Required command is unavailable: $command" >&2
    exit 1
  fi
done

application_dir="/opt/pihole-speedtest"
data_dir="/var/lib/pihole-speedtest"
dashboard_unit="pihole-speedtest-dashboard.service"
dashboard_unit_path="/etc/systemd/system/${dashboard_unit}"
collection_unit="pihole-speedtest-collect.service"
collection_unit_path="/etc/systemd/system/${collection_unit}"
timer_unit="pihole-speedtest-collect.timer"
timer_unit_path="/etc/systemd/system/${timer_unit}"
settings_path="${data_dir}/settings.json"
token_path="${data_dir}/admin.token"
database_path="${data_dir}/speedtest.db"
install_manifest="${data_dir}/install-manifest.txt"
collection_manifest="${data_dir}/collection-manifest.txt"
recovery_root="/var/lib/pihole-speedtest-upgrade-recovery"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
recovery_dir="${recovery_root}/${timestamp}"
old_application_moved=0
units_installed=0
settings_changed=0
upgrade_complete=0

for path in \
  "$application_dir" "$data_dir" "$dashboard_unit_path" \
  "$settings_path" "$token_path" "$database_path" "$install_manifest"
do
  if [ ! -e "$path" ]; then
    echo "STOP: Required staged-install target is missing: $path" >&2
    exit 1
  fi
done
for path in "$collection_unit_path" "$timer_unit_path" "$collection_manifest"; do
  if [ -e "$path" ]; then
    echo "STOP: Collection or upgrade target already exists: $path" >&2
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
if [ ! -x /usr/bin/speedtest ]; then
  echo "STOP: Official Ookla CLI is unavailable at /usr/bin/speedtest." >&2
  exit 1
fi
if ! /usr/bin/speedtest --version | grep -q 'Speedtest by Ookla'; then
  echo "STOP: /usr/bin/speedtest is not the expected official Ookla CLI." >&2
  exit 1
fi
if [ "$(systemctl is-active "$dashboard_unit")" != "active" ]; then
  echo "STOP: Dashboard service is not active." >&2
  exit 1
fi

rollback() {
  status=$?
  if [ "$status" -eq 0 ] || [ "$upgrade_complete" -eq 1 ]; then
    return
  fi
  trap - EXIT
  echo
  echo "Collection upgrade failed.  Restoring the dashboard baseline..." >&2
  systemctl disable --now "$timer_unit" >/dev/null 2>&1 || true
  systemctl stop "$collection_unit" >/dev/null 2>&1 || true
  if [ "$units_installed" -eq 1 ]; then
    rm -f -- "$collection_unit_path" "$timer_unit_path"
  fi
  systemctl stop "$dashboard_unit" >/dev/null 2>&1 || true
  if [ "$old_application_moved" -eq 1 ] && [ -d "$application_dir" ]; then
    rm -rf -- "$application_dir"
  fi
  if [ "$old_application_moved" -eq 1 ] && [ -d "$recovery_dir/application-before" ]; then
mv "$recovery_dir/application-before" "$application_dir"
  fi
  if [ -f "$recovery_dir/dashboard-unit.before" ]; then
    cp -a "$recovery_dir/dashboard-unit.before" "$dashboard_unit_path"
  fi
  if [ "$settings_changed" -eq 1 ] && [ -f "$recovery_dir/settings.before.json" ]; then
    cp -a "$recovery_dir/settings.before.json" "$settings_path"
  fi
  if [ -f "$recovery_dir/install-manifest.before.txt" ]; then
    cp -a "$recovery_dir/install-manifest.before.txt" "$install_manifest"
  fi
  systemctl daemon-reload >/dev/null 2>&1 || true
  systemctl start "$dashboard_unit" >/dev/null 2>&1 || true
  echo "Rollback finished.  Database backup and evidence: $recovery_dir" >&2
  echo "Any successfully completed measurement was deliberately preserved." >&2
  exit "$status"
}
trap rollback EXIT

install -d -m 0700 "$recovery_root" "$recovery_dir"
cp -a "$dashboard_unit_path" "$recovery_dir/dashboard-unit.before"
cp -a "$settings_path" "$recovery_dir/settings.before.json"
cp -a "$install_manifest" "$recovery_dir/install-manifest.before.txt"
pihole status > "$recovery_dir/pihole-status.before.txt"
systemctl status "$dashboard_unit" --no-pager > "$recovery_dir/dashboard-status.before.txt"

python3 - "$database_path" "$recovery_dir/speedtest.before.db" "$expected_count" <<'PY'
import sqlite3
import sys

source_path, backup_path, expected = sys.argv[1], sys.argv[2], int(sys.argv[3])
with sqlite3.connect(source_path) as source:
    count = source.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]
    if count != expected:
        raise SystemExit(f"measurement count mismatch: {count} != {expected}")
    with sqlite3.connect(backup_path) as destination:
        source.backup(destination)
        integrity = destination.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise SystemExit(f"backup integrity check failed: {integrity}")
PY
sha256sum "$recovery_dir/speedtest.before.db" > "$recovery_dir/speedtest.before.db.sha256"

python3 -m venv "$recovery_dir/build-venv"
"$recovery_dir/build-venv/bin/python" -m pip wheel \
  --wheel-dir "$recovery_dir/wheels" \
  "$source_root"
wheel_path="$(find "$recovery_dir/wheels" -maxdepth 1 -type f -name 'pihole_speedtest_v6-*.whl' -print -quit)"
if [ -z "$wheel_path" ] || [ ! -f "$wheel_path" ]; then
  echo "STOP: The approved application wheel was not created." >&2
  exit 1
fi

systemctl stop "$dashboard_unit"
mv "$application_dir" "$recovery_dir/application-before"
old_application_moved=1
install -d -m 0755 -o root -g root "$application_dir"
python3 -m venv "$application_dir/venv"
"$application_dir/venv/bin/python" -m pip install "$wheel_path"
rm -rf -- "$recovery_dir/build-venv"

settings_changed=1
runuser -u pihole-speedtest -- \
  "$application_dir/venv/bin/python" - "$settings_path" "$interval_minutes" <<'PY'
import sys
from pathlib import Path
from pihole_speedtest.settings import save_settings

save_settings(Path(sys.argv[1]), int(sys.argv[2]))
PY

units_installed=1
install -m 0644 "$source_root/deploy/systemd/pihole-speedtest-dashboard.service" "$dashboard_unit_path"
install -m 0644 "$source_root/deploy/systemd/pihole-speedtest-collect.service" "$collection_unit_path"
install -m 0644 "$source_root/deploy/systemd/pihole-speedtest-collect.timer" "$timer_unit_path"
systemctl daemon-reload
systemctl start "$dashboard_unit"

for attempt in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS http://127.0.0.1:8765/api/health > "$recovery_dir/health.before-collection.json"; then
    break
  fi
  sleep 1
done

"$application_dir/venv/bin/python" - \
  "$token_path" "$recovery_dir/manual-collection.json" <<'PY'
import json
import sys
import time
from urllib.request import Request, urlopen

token_path, result_path = sys.argv[1:3]
with open(token_path, encoding="utf-8") as source:
    token = source.read().strip()
request = Request(
    "http://127.0.0.1:8765/api/collect",
    data=b"{}",
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    },
    method="POST",
)
with urlopen(request, timeout=10) as response:
    started = json.loads(response.read())
if response.status != 202 or started.get("state") != "running":
    raise SystemExit(f"manual collection was not accepted: {started}")

deadline = time.monotonic() + 190
while time.monotonic() < deadline:
    time.sleep(1)
    with urlopen("http://127.0.0.1:8765/api/collection-status", timeout=10) as response:
        status = json.loads(response.read())
    if status.get("state") != "running":
        break
else:
    raise SystemExit("manual collection exceeded the verification window")
with open(result_path, "w", encoding="utf-8") as destination:
    json.dump(status, destination, separators=(",", ":"))
    destination.write("\n")
if status.get("state") != "succeeded":
    raise SystemExit(f"manual collection failed: {status.get('message', 'unknown error')}")
PY

expected_after=$((expected_count + 1))
"$application_dir/venv/bin/python" - "$database_path" "$expected_after" <<'PY'
import sqlite3
import sys

with sqlite3.connect(sys.argv[1]) as connection:
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    count = connection.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]
if integrity != "ok":
    raise SystemExit(f"SQLite integrity check failed: {integrity}")
if count != int(sys.argv[2]):
    raise SystemExit(f"measurement count mismatch: {count} != {sys.argv[2]}")
PY

systemctl enable --now "$timer_unit"
systemctl is-active --quiet "$timer_unit"
systemctl is-enabled --quiet "$timer_unit"

{
  echo "installed_at=$timestamp"
  echo "source_commit=$source_commit"
  echo "upgraded_from=$installed_commit"
  echo "database_sha256=$(sha256sum "$database_path" | awk '{print $1}')"
  echo "dashboard_unit_sha256=$(sha256sum "$dashboard_unit_path" | awk '{print $1}')"
  echo "collection_unit_sha256=$(sha256sum "$collection_unit_path" | awk '{print $1}')"
  echo "timer_unit_sha256=$(sha256sum "$timer_unit_path" | awk '{print $1}')"
  echo "collection_interval_minutes=$interval_minutes"
  echo "pihole_adapter_installed=false"
} > "$install_manifest"
chmod 0600 "$install_manifest"
cp -a "$install_manifest" "$collection_manifest"

curl -fsS http://127.0.0.1:8765/api/health > "$recovery_dir/health.after-collection.json"
systemctl status "$dashboard_unit" --no-pager > "$recovery_dir/dashboard-status.after.txt"
systemctl status "$timer_unit" --no-pager > "$recovery_dir/timer-status.after.txt"
systemctl list-timers "$timer_unit" --no-pager > "$recovery_dir/timer-schedule.after.txt"
pihole status > "$recovery_dir/pihole-status.after.txt"
upgrade_complete=1

echo
echo "=== COLLECTION ACTIVATION PASSED ==="
cat "$recovery_dir/manual-collection.json"
cat "$recovery_dir/health.after-collection.json"
echo
echo "Capture frequency: every $interval_minutes minutes"
echo "Collection timer: active and enabled"
echo "Manual speed-test control: enabled"
echo "Pi-hole sidebar adapter: not installed"
echo "Recovery evidence: $recovery_dir"

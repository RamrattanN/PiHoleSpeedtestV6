#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: sudo scripts/upgrade_companion.sh \
  --expected-source-commit SHA \
  --expected-installed-commit SHA

Safely upgrades an existing keyless Pi-hole Speedtest companion installation.
The database, settings, collection schedule, prior application, deployment
files, and verification evidence are preserved.  Pi-hole web files are not
modified.
EOF
}

expected_source_commit=""
expected_installed_commit=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --expected-source-commit) expected_source_commit="$2"; shift 2 ;;
    --expected-installed-commit) expected_installed_commit="$2"; shift 2 ;;
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
for command in python3 systemctl curl sha256sum pihole git find seq; do
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
database_path="${data_dir}/speedtest.db"
settings_path="${data_dir}/settings.json"
token_path="${data_dir}/admin.token"
install_manifest="${data_dir}/install-manifest.txt"
collection_manifest="${data_dir}/collection-manifest.txt"
recovery_root="/var/lib/pihole-speedtest-upgrade-recovery"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
recovery_dir="${recovery_root}/${timestamp}"
old_application_moved=0
dashboard_unit_changed=0
timer_stopped=0
upgrade_complete=0

for path in \
  "$application_dir" "$data_dir" "$dashboard_unit_path" \
  "$collection_unit_path" "$timer_unit_path" "$database_path" \
  "$settings_path" "$install_manifest" "$collection_manifest"
do
  if [ ! -e "$path" ]; then
    echo "STOP: Required installed target is missing: $path" >&2
    exit 1
  fi
done
if [ -e "$token_path" ]; then
  echo "STOP: This upgrader requires the approved keyless installation." >&2
  exit 1
fi

installed_commit="$(sed -n 's/^source_commit=//p' "$install_manifest")"
if [ "$installed_commit" != "$expected_installed_commit" ]; then
  echo "STOP: Installed commit does not match the approved baseline." >&2
  echo "Expected: $expected_installed_commit" >&2
  echo "Actual:   ${installed_commit:-unknown}" >&2
  exit 1
fi
adapter_installed="$(sed -n 's/^pihole_adapter_installed=//p' "$install_manifest")"
adapter_manifest="$(sed -n 's/^pihole_adapter_manifest=//p' "$install_manifest")"
case "$adapter_installed" in
  true)
    if [ -z "$adapter_manifest" ] || [ ! -f "$adapter_manifest" ]; then
      echo "STOP: The installed adapter recovery manifest is missing." >&2
      exit 1
    fi
    python3 - "$adapter_manifest" <<'PY'
import hashlib
import json
import pathlib
import sys


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


manifest_path = pathlib.Path(sys.argv[1])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
sidebar = pathlib.Path(manifest["sidebar"]["path"])
if sha256(sidebar) != manifest["sidebar"]["installed_sha256"]:
    raise SystemExit("STOP: Installed adapter sidebar no longer matches its manifest.")
for created in manifest["created"]:
    path = pathlib.Path(created["path"])
    if sha256(path) != created["sha256"]:
        raise SystemExit(f"STOP: Installed adapter page no longer matches: {path}")
PY
    ;;
  false)
    if [ -n "$adapter_manifest" ]; then
      echo "STOP: Adapter state is false but a recovery manifest is recorded." >&2
      exit 1
    fi
    ;;
  *)
    echo "STOP: Installed adapter state is missing or invalid." >&2
    exit 1
    ;;
esac
for unit in "$dashboard_unit" "$timer_unit"; do
  if [ "$(systemctl is-active "$unit")" != "active" ] ||
    [ "$(systemctl is-enabled "$unit")" != "enabled" ]
  then
    echo "STOP: Required unit is not active and enabled: $unit" >&2
    exit 1
  fi
done

rollback() {
  status=$?
  if [ "$status" -eq 0 ] || [ "$upgrade_complete" -eq 1 ]; then
    return
  fi
  trap - EXIT
  echo
  echo "Companion upgrade failed.  Restoring the prior dashboard..." >&2
  systemctl stop "$dashboard_unit" >/dev/null 2>&1 || true
  if [ "$old_application_moved" -eq 1 ] && [ -d "$application_dir" ]; then
    rm -rf -- "$application_dir"
  fi
  if [ "$old_application_moved" -eq 1 ] && [ -d "$recovery_dir/application-before" ]; then
    mv "$recovery_dir/application-before" "$application_dir"
  fi
  if [ "$dashboard_unit_changed" -eq 1 ] && [ -f "$recovery_dir/dashboard-unit.before" ]; then
    cp -a "$recovery_dir/dashboard-unit.before" "$dashboard_unit_path"
  fi
  if [ -f "$recovery_dir/install-manifest.before.txt" ]; then
    cp -a "$recovery_dir/install-manifest.before.txt" "$install_manifest"
  fi
  if [ -f "$recovery_dir/collection-manifest.before.txt" ]; then
    cp -a "$recovery_dir/collection-manifest.before.txt" "$collection_manifest"
  fi
  systemctl daemon-reload >/dev/null 2>&1 || true
  systemctl start "$dashboard_unit" >/dev/null 2>&1 || true
  if [ "$timer_stopped" -eq 1 ]; then
    systemctl start "$timer_unit" >/dev/null 2>&1 || true
  fi
  echo "Rollback finished.  Recovery evidence: $recovery_dir" >&2
  echo "Measurement data was deliberately preserved." >&2
  exit "$status"
}
trap rollback EXIT

install -d -m 0700 "$recovery_root" "$recovery_dir"
cp -a "$dashboard_unit_path" "$recovery_dir/dashboard-unit.before"
cp -a "$collection_unit_path" "$recovery_dir/collection-unit.before"
cp -a "$timer_unit_path" "$recovery_dir/timer-unit.before"
cp -a "$settings_path" "$recovery_dir/settings.before.json"
cp -a "$install_manifest" "$recovery_dir/install-manifest.before.txt"
cp -a "$collection_manifest" "$recovery_dir/collection-manifest.before.txt"
systemctl status "$dashboard_unit" --no-pager > "$recovery_dir/dashboard-status.before.txt"
systemctl status "$timer_unit" --no-pager > "$recovery_dir/timer-status.before.txt"
pihole status > "$recovery_dir/pihole-status.before.txt"

systemctl stop "$timer_unit"
timer_stopped=1
for attempt in $(seq 1 190); do
  if ! systemctl is-active --quiet "$collection_unit"; then
    break
  fi
  sleep 1
done
if systemctl is-active --quiet "$collection_unit"; then
  echo "STOP: Active collection did not finish within the safe wait period." >&2
  exit 1
fi

before_count="$(python3 - "$database_path" "$recovery_dir/speedtest.before.db" <<'PY'
import sqlite3
import sys

source_path, backup_path = sys.argv[1:3]
with sqlite3.connect(source_path) as source:
    count = source.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]
    integrity = source.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        raise SystemExit(f"source integrity check failed: {integrity}")
    with sqlite3.connect(backup_path) as destination:
        source.backup(destination)
        backup_integrity = destination.execute("PRAGMA integrity_check").fetchone()[0]
        if backup_integrity != "ok":
            raise SystemExit(f"backup integrity check failed: {backup_integrity}")
print(count)
PY
)"
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

install -m 0644 "$source_root/deploy/systemd/pihole-speedtest-dashboard.service" "$dashboard_unit_path"
dashboard_unit_changed=1
systemctl daemon-reload
systemctl start "$dashboard_unit"

for attempt in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS http://127.0.0.1:8765/api/health > "$recovery_dir/health.after.json"; then
    break
  fi
  sleep 1
done
curl -fsS http://127.0.0.1:8765/ > "$recovery_dir/dashboard.after.html"

"$application_dir/venv/bin/python" - \
  "$database_path" "$before_count" \
  "$recovery_dir/health.after.json" \
  "$recovery_dir/dashboard.after.html" <<'PY'
import json
import sqlite3
import sys

database_path, expected_count, health_path, dashboard_path = sys.argv[1:5]
with sqlite3.connect(database_path) as connection:
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    count = connection.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]
if integrity != "ok":
    raise SystemExit(f"SQLite integrity check failed: {integrity}")
if count != int(expected_count):
    raise SystemExit(f"measurement count changed during upgrade: {count} != {expected_count}")
with open(health_path, encoding="utf-8") as source:
    health = json.load(source)
if health.get("status") != "ok" or health.get("measurements") != count:
    raise SystemExit(f"health verification failed: {health}")
with open(dashboard_path, encoding="utf-8") as source:
    dashboard = source.read()
for required in ('class="run-speedtest-button"', 'id="history-tooltip"', 'id="latency-tooltip"'):
    if required not in dashboard:
        raise SystemExit(f"dashboard marker is missing: {required}")
if "<details" in dashboard or "<summary" in dashboard:
    raise SystemExit("collapsible Setup markup is still present")
PY

interval_minutes="$("$application_dir/venv/bin/python" - "$settings_path" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as source:
    print(int(json.load(source)["collection_interval_minutes"]))
PY
)"

{
  echo "installed_at=$timestamp"
  echo "source_commit=$source_commit"
  echo "upgraded_from=$installed_commit"
  echo "database_sha256=$(sha256sum "$database_path" | awk '{print $1}')"
  echo "dashboard_unit_sha256=$(sha256sum "$dashboard_unit_path" | awk '{print $1}')"
  echo "collection_unit_sha256=$(sha256sum "$collection_unit_path" | awk '{print $1}')"
  echo "timer_unit_sha256=$(sha256sum "$timer_unit_path" | awk '{print $1}')"
  echo "collection_interval_minutes=$interval_minutes"
  echo "administrator_key_enabled=false"
  echo "pihole_adapter_installed=$adapter_installed"
  if [ "$adapter_installed" = "true" ]; then
    echo "pihole_adapter_manifest=$adapter_manifest"
  fi
} > "$install_manifest"
chmod 0600 "$install_manifest"
cp -a "$install_manifest" "$collection_manifest"

systemctl start "$timer_unit"
systemctl is-active --quiet "$dashboard_unit"
systemctl is-enabled --quiet "$dashboard_unit"
systemctl is-active --quiet "$timer_unit"
systemctl is-enabled --quiet "$timer_unit"
systemctl status "$dashboard_unit" --no-pager > "$recovery_dir/dashboard-status.after.txt"
systemctl status "$timer_unit" --no-pager > "$recovery_dir/timer-status.after.txt"
systemctl list-timers "$timer_unit" --no-pager > "$recovery_dir/timer-schedule.after.txt"
pihole status > "$recovery_dir/pihole-status.after.txt"
upgrade_complete=1

echo
echo "=== COMPANION UPGRADE PASSED ==="
cat "$recovery_dir/health.after.json"
echo
echo "Dashboard navigation: verified"
echo "Chart mouseover details: verified"
echo "Setup sections: permanently expanded"
echo "Collection timer: active and enabled"
if [ "$adapter_installed" = "true" ]; then
  echo "Pi-hole sidebar adapter: installed and verified"
else
  echo "Pi-hole sidebar adapter: not installed"
fi
echo "Recovery evidence: $recovery_dir"

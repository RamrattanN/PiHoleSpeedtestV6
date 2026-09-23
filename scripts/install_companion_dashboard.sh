#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: sudo scripts/install_companion_dashboard.sh \
  --legacy-csv PATH \
  --frame-origin ORIGIN \
  --expected-commit SHA \
  --expected-count NUMBER \
  --expected-rejected NUMBER \
  --expected-collisions NUMBER

Installs and starts only the companion dashboard.  It does not install or
enable the collection timer and does not modify the Pi-hole web tree.
EOF
}

legacy_csv=""
frame_origin=""
expected_commit=""
expected_count=""
expected_rejected=""
expected_collisions=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --legacy-csv) legacy_csv="$2"; shift 2 ;;
    --frame-origin) frame_origin="$2"; shift 2 ;;
    --expected-commit) expected_commit="$2"; shift 2 ;;
    --expected-count) expected_count="$2"; shift 2 ;;
    --expected-rejected) expected_rejected="$2"; shift 2 ;;
    --expected-collisions) expected_collisions="$2"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [ "${EUID}" -ne 0 ]; then
  echo "STOP: Run this installer with sudo." >&2
  exit 1
fi

for value in expected_count expected_rejected expected_collisions; do
  if ! [[ "${!value}" =~ ^[0-9]+$ ]]; then
    echo "STOP: --${value//_/-} must be a non-negative integer." >&2
    exit 1
  fi
done

if [ ! -f "$legacy_csv" ]; then
  echo "STOP: Legacy CSV not found: $legacy_csv" >&2
  exit 1
fi

if ! [[ "$frame_origin" =~ ^https?://[A-Za-z0-9._:-]+$ ]]; then
  echo "STOP: --frame-origin must be one HTTP(S) origin without a path." >&2
  exit 1
fi

if ! [[ "$expected_commit" =~ ^[0-9a-f]{40}$ ]]; then
  echo "STOP: --expected-commit must be one full lowercase Git commit SHA." >&2
  exit 1
fi

source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
source_commit="$(git -C "$source_root" rev-parse HEAD 2>/dev/null || true)"
if [ "$source_commit" != "$expected_commit" ]; then
  echo "STOP: Source commit does not match the approved commit." >&2
  echo "Expected: $expected_commit" >&2
  echo "Actual:   ${source_commit:-unknown}" >&2
  exit 1
fi
if ! git -C "$source_root" diff --quiet -- ||
  ! git -C "$source_root" diff --cached --quiet --
then
  echo "STOP: Source worktree has tracked changes." >&2
  exit 1
fi
application_dir="/opt/pihole-speedtest"
data_dir="/var/lib/pihole-speedtest"
service_user="pihole-speedtest"
unit_name="pihole-speedtest-dashboard.service"
unit_path="/etc/systemd/system/${unit_name}"
environment_path="/etc/default/pihole-speedtest-v6"
recovery_root="/var/lib/pihole-speedtest-install-recovery"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
recovery_dir="${recovery_root}/${timestamp}"
failed_data="${recovery_dir}/failed-data"
created_user=0
created_application=0
created_data=0
created_unit=0
created_environment=0
installation_complete=0

for path in "$application_dir" "$data_dir" "$unit_path" "$environment_path"; do
  if [ -e "$path" ]; then
    echo "STOP: Installation target already exists: $path" >&2
    exit 1
  fi
done

if id "$service_user" >/dev/null 2>&1; then
  echo "STOP: Service account already exists: $service_user" >&2
  exit 1
fi

for command in python3 systemctl curl sha256sum runuser; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "STOP: Required command is unavailable: $command" >&2
    exit 1
  fi
done

rollback() {
  status=$?
  if [ "$status" -eq 0 ] || [ "$installation_complete" -eq 1 ]; then
    return
  fi
  trap - EXIT
  echo
  echo "Installation failed.  Rolling back the dashboard service..." >&2
  if [ "$created_unit" -eq 1 ]; then
    systemctl disable --now "$unit_name" >/dev/null 2>&1 || true
    rm -f "$unit_path"
    systemctl daemon-reload >/dev/null 2>&1 || true
  fi
  if [ "$created_application" -eq 1 ]; then
    rm -rf -- "$application_dir"
  fi
  if [ "$created_environment" -eq 1 ]; then
    rm -f "$environment_path"
  fi
  if [ "$created_data" -eq 1 ] && [ -d "$data_dir" ]; then
    mkdir -p "$recovery_dir"
    mv "$data_dir" "$failed_data"
  fi
  if [ "$created_user" -eq 1 ]; then
    userdel "$service_user" >/dev/null 2>&1 || true
  fi
  echo "Rollback finished.  Evidence is retained at: $recovery_dir" >&2
  exit "$status"
}
trap rollback EXIT

mkdir -p "$recovery_dir"
chmod 0700 "$recovery_root" "$recovery_dir"

{
  echo "timestamp=$timestamp"
  echo "source_root=$source_root"
  echo "source_commit=$source_commit"
  echo "legacy_csv=$legacy_csv"
  echo "legacy_csv_sha256=$(sha256sum "$legacy_csv" | awk '{print $1}')"
  pihole -v 2>/dev/null || true
  pihole status 2>/dev/null || true
} > "$recovery_dir/preflight.txt"

useradd \
  --system \
  --home-dir "$data_dir" \
  --shell /usr/sbin/nologin \
  --user-group \
  "$service_user"
created_user=1

install -d -m 0755 -o root -g root "$application_dir"
created_application=1
python3 -m venv "$application_dir/venv"
"$application_dir/venv/bin/python" -m pip install "$source_root"

install -d -m 0750 -o "$service_user" -g "$service_user" "$data_dir"
created_data=1
install -d -m 0750 -o "$service_user" -g "$service_user" "$data_dir/backups"
install -d -m 0750 -o "$service_user" -g "$service_user" "$data_dir/migration"

install -m 0640 -o "$service_user" -g "$service_user" \
  "$legacy_csv" "$data_dir/migration/legacy-speedtest.csv"

set +e
runuser -u "$service_user" -- \
  "$application_dir/venv/bin/pihole-speedtest" import-legacy-csv \
    "$data_dir/migration/legacy-speedtest.csv" \
    --database "$data_dir/speedtest.db" \
    --issue-limit 500 \
    > "$data_dir/migration/import-report.json"
import_status=$?
set -e

if [ "$import_status" -ne 0 ] && [ "$import_status" -ne 2 ]; then
  echo "STOP: Legacy import failed with status $import_status." >&2
  exit 1
fi

"$application_dir/venv/bin/python" - \
  "$data_dir/migration/import-report.json" \
  "$data_dir/speedtest.db" \
  "$expected_count" \
  "$expected_rejected" \
  "$expected_collisions" <<'PY'
import json
import sqlite3
import sys

report_path, database_path = sys.argv[1:3]
expected_count, expected_rejected, expected_collisions = map(int, sys.argv[3:6])

with open(report_path, encoding="utf-8") as source:
    report = json.load(source)

with sqlite3.connect(database_path) as connection:
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    count = connection.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]

if integrity != "ok":
    raise SystemExit(f"SQLite integrity check failed: {integrity}")
if count != expected_count:
    raise SystemExit(f"measurement count mismatch: {count} != {expected_count}")
if report["inserted"] != expected_count:
    raise SystemExit("inserted count does not match expected measurement count")
if report["rejected"] != expected_rejected:
    raise SystemExit("rejected count does not match the accepted migration baseline")
if report["timestamp_collisions"] != expected_collisions:
    raise SystemExit("collision count does not match the accepted migration baseline")
PY

chown -R "$service_user:$service_user" "$data_dir"
chmod 0600 "$data_dir/speedtest.db" "$data_dir/migration/import-report.json"

printf '{"collection_interval_minutes":60}\n' > "$data_dir/settings.json"
chown "$service_user:$service_user" "$data_dir/settings.json"

printf 'PIHOLE_SPEEDTEST_FRAME_ANCESTORS=%s\n' "$frame_origin" > "$environment_path"
created_environment=1
chmod 0600 "$environment_path"

install -m 0644 \
  "$source_root/deploy/systemd/pihole-speedtest-dashboard.service" \
  "$unit_path"
created_unit=1

systemctl daemon-reload
systemctl enable --now "$unit_name"

health_file="$recovery_dir/dashboard-health.json"
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS http://127.0.0.1:8765/api/health > "$health_file"; then
    break
  fi
  sleep 1
done

"$application_dir/venv/bin/python" - "$health_file" "$expected_count" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as source:
    health = json.load(source)
if health.get("status") != "ok":
    raise SystemExit("dashboard health is not ok")
if health.get("measurements") != int(sys.argv[2]):
    raise SystemExit("dashboard measurement count does not match")
PY

{
  echo "installed_at=$timestamp"
  echo "source_commit=$source_commit"
  echo "database_sha256=$(sha256sum "$data_dir/speedtest.db" | awk '{print $1}')"
  echo "unit_sha256=$(sha256sum "$unit_path" | awk '{print $1}')"
  echo "environment_sha256=$(sha256sum "$environment_path" | awk '{print $1}')"
  echo "collection_timer_enabled=false"
  echo "pihole_adapter_installed=false"
} > "$data_dir/install-manifest.txt"
chown root:root "$data_dir/install-manifest.txt"
chmod 0600 "$data_dir/install-manifest.txt"

systemctl status "$unit_name" --no-pager > "$recovery_dir/service-status.txt"
pihole status > "$recovery_dir/pihole-status.after.txt"
installation_complete=1

echo
echo "=== DASHBOARD-ONLY INSTALLATION PASSED ==="
cat "$health_file"
echo
echo "Dashboard: http://$(hostname -I | awk '{print $1}'):8765/"
echo "Collection timer: disabled and not installed"
echo "Pi-hole sidebar adapter: not installed"
echo "Recovery evidence: $recovery_dir"

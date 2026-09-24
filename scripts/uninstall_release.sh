#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: sudo scripts/uninstall_release.sh --expected-commit SHA

Removes the companion services, application, and service account while
preserving the database, settings, backups, logs, manifests, and recovery
evidence under /var/lib/pihole-speedtest.  Remove the optional Pi-hole sidebar
adapter first if it is installed.
EOF
}

expected_commit=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --expected-commit) expected_commit="$2"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [ "${EUID}" -ne 0 ]; then
  echo "STOP: Run this uninstaller with sudo." >&2
  exit 1
fi
if ! [[ "$expected_commit" =~ ^[0-9a-f]{40}$ ]]; then
  echo "STOP: --expected-commit must be one full lowercase Git commit SHA." >&2
  exit 1
fi
for command in python3 systemctl sha256sum pihole useradd userdel grep sed pgrep; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "STOP: Required command is unavailable: $command" >&2
    exit 1
  fi
done

application_dir="/opt/pihole-speedtest"
data_dir="/var/lib/pihole-speedtest"
service_user="pihole-speedtest"
environment_path="/etc/default/pihole-speedtest-v6"
dashboard_unit="pihole-speedtest-dashboard.service"
collection_unit="pihole-speedtest-collect.service"
timer_unit="pihole-speedtest-collect.timer"
dashboard_unit_path="/etc/systemd/system/${dashboard_unit}"
collection_unit_path="/etc/systemd/system/${collection_unit}"
timer_unit_path="/etc/systemd/system/${timer_unit}"
manifest_path="${data_dir}/install-manifest.txt"
database_path="${data_dir}/speedtest.db"
recovery_root="/var/lib/pihole-speedtest-uninstall-recovery"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
recovery_dir="${recovery_root}/${timestamp}"
removal_started=0
removal_complete=0

for path in "$application_dir" "$data_dir" "$environment_path" "$dashboard_unit_path" "$collection_unit_path" "$timer_unit_path" "$manifest_path"; do
  if [ ! -e "$path" ]; then
    echo "STOP: Expected installation target is missing: $path" >&2
    exit 1
  fi
done
installed_commit="$(sed -n 's/^source_commit=//p' "$manifest_path")"
if [ "$installed_commit" != "$expected_commit" ]; then
  echo "STOP: Installed source commit does not match --expected-commit." >&2
  echo "Expected: $expected_commit" >&2
  echo "Actual:   ${installed_commit:-unknown}" >&2
  exit 1
fi
if [ "$(sed -n 's/^pihole_adapter_installed=//p' "$manifest_path")" != "false" ]; then
  echo "STOP: Remove the Pi-hole sidebar adapter before uninstalling the companion." >&2
  exit 1
fi
if [ ! -f "$database_path" ]; then
  echo "STOP: Measurement database is missing: $database_path" >&2
  exit 1
fi

rollback() {
  status=$?
  if [ "$status" -eq 0 ] || [ "$removal_started" -eq 0 ] || [ "$removal_complete" -eq 1 ]; then
    return
  fi
  trap - EXIT
  echo "Uninstall failed.  Restoring the installed application..." >&2
  if ! id "$service_user" >/dev/null 2>&1; then
    useradd --system --home-dir "$data_dir" --shell /usr/sbin/nologin --user-group "$service_user" || true
    chown -R "$service_user:$service_user" "$data_dir" || true
  fi
  if [ ! -d "$application_dir" ] && [ -d "$recovery_dir/application" ]; then
    cp -a "$recovery_dir/application" "$application_dir"
  fi
  for item in "$dashboard_unit" "$collection_unit" "$timer_unit"; do
    if [ ! -f "/etc/systemd/system/$item" ] && [ -f "$recovery_dir/$item" ]; then
      cp -a "$recovery_dir/$item" "/etc/systemd/system/$item"
    fi
  done
  if [ ! -f "$environment_path" ] && [ -f "$recovery_dir/pihole-speedtest-v6.environment" ]; then
    cp -a "$recovery_dir/pihole-speedtest-v6.environment" "$environment_path"
  fi
  systemctl daemon-reload >/dev/null 2>&1 || true
  systemctl enable --now "$dashboard_unit" >/dev/null 2>&1 || true
  systemctl enable --now "$timer_unit" >/dev/null 2>&1 || true
  echo "Rollback finished.  User data was never removed." >&2
  exit "$status"
}
trap rollback EXIT

install -d -m 0700 "$recovery_root" "$recovery_dir"
cp -a "$application_dir" "$recovery_dir/application"
cp -a "$dashboard_unit_path" "$collection_unit_path" "$timer_unit_path" "$recovery_dir/"
cp -a "$environment_path" "$recovery_dir/pihole-speedtest-v6.environment"
cp -a "$manifest_path" "$recovery_dir/install-manifest.before.txt"
systemctl status "$dashboard_unit" --no-pager > "$recovery_dir/dashboard-status.before.txt" || true
systemctl list-timers "$timer_unit" --no-pager > "$recovery_dir/timer-schedule.before.txt" || true
pihole status > "$recovery_dir/pihole-status.before.txt"

python3 - "$database_path" "$recovery_dir/speedtest.db" <<'PY'
import sqlite3
import sys
source_path, backup_path = sys.argv[1:]
with sqlite3.connect(source_path) as source:
    integrity = source.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        raise SystemExit(f"STOP: Active database integrity check failed: {integrity}")
    with sqlite3.connect(backup_path) as destination:
        source.backup(destination)
        copied = destination.execute("PRAGMA integrity_check").fetchone()[0]
if copied != "ok":
    raise SystemExit(f"STOP: Recovery database integrity check failed: {copied}")
PY
sha256sum "$recovery_dir/speedtest.db" > "$recovery_dir/speedtest.db.sha256"

removal_started=1
systemctl disable --now "$timer_unit"
systemctl stop "$collection_unit" >/dev/null 2>&1 || true
systemctl disable --now "$dashboard_unit"
rm -f -- "$dashboard_unit_path" "$collection_unit_path" "$timer_unit_path" "$environment_path"
systemctl daemon-reload
rm -rf -- "$application_dir"

if pgrep -u "$service_user" >/dev/null 2>&1; then
  echo "STOP: Service-account processes remain after services stopped." >&2
  exit 1
fi
userdel "$service_user"

cat >> "$manifest_path" <<EOF
uninstalled_at=$timestamp
uninstall_recovery=$recovery_dir
data_preserved=true
EOF
chmod 0600 "$manifest_path"
pihole status > "$recovery_dir/pihole-status.after.txt" || true
{
  echo "uninstalled_at=$timestamp"
  echo "source_commit=$installed_commit"
  echo "data_preserved=$data_dir"
  echo "pihole_web_tree_modified=false"
} > "$recovery_dir/uninstall-manifest.txt"
removal_complete=1

echo
echo "=== PI-HOLE SPEEDTEST UNINSTALL PASSED ==="
echo "Services, application, and service account removed."
echo "User data preserved at: $data_dir"
echo "Recovery evidence: $recovery_dir"
echo "Pi-hole web files were not modified."

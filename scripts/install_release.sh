#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: sudo scripts/install_release.sh \
  --source-commit SHA \
  [--pihole-origin ORIGIN] \
  [--interval-minutes NUMBER]

Installs the verified Pi-hole Speedtest companion, dashboard service, and
collection timer.  Existing preserved data is reused.  The Pi-hole web tree is
not modified; install the optional sidebar adapter as a separate phase.
EOF
}

source_commit=""
pihole_origin=""
interval_minutes="15"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-commit) source_commit="$2"; shift 2 ;;
    --pihole-origin) pihole_origin="$2"; shift 2 ;;
    --interval-minutes) interval_minutes="$2"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [ "${EUID}" -ne 0 ]; then
  echo "STOP: Run this installer with sudo." >&2
  exit 1
fi
if ! [[ "$source_commit" =~ ^[0-9a-f]{40}$ ]]; then
  echo "STOP: --source-commit must be one full lowercase Git commit SHA." >&2
  exit 1
fi
case "$interval_minutes" in
  15|30|60|120|240|360|720|1440) ;;
  *) echo "STOP: Unsupported collection interval: $interval_minutes" >&2; exit 1 ;;
esac

source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
source_marker="$source_root/release/SOURCE-COMMIT"
if [ ! -f "$source_marker" ] || [ "$(tr -d '\r\n' < "$source_marker")" != "$source_commit" ]; then
  echo "STOP: Verified release source marker does not match --source-commit." >&2
  exit 1
fi

for command in python3 systemctl curl sha256sum runuser pihole useradd userdel awk grep sed hostname uname tr head; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "STOP: Required command is unavailable: $command" >&2
    exit 1
  fi
done

architecture="$(uname -m)"
case "$architecture" in
  aarch64|x86_64) ;;
  *) echo "STOP: Unsupported architecture: $architecture" >&2; exit 1 ;;
esac

python3 - <<'PY'
import sys
if sys.version_info < (3, 9):
    raise SystemExit("STOP: Python 3.9 or newer is required.")
PY

core_version="$(pihole -v 2>/dev/null | sed -n 's/^Core version is v\([0-9][^ ]*\).*/\1/p' | head -n1)"
if ! [[ "$core_version" =~ ^6\. ]]; then
  echo "STOP: Pi-hole Core v6 is required.  Detected: ${core_version:-unknown}" >&2
  exit 1
fi
if [ ! -x /usr/bin/speedtest ] || ! /usr/bin/speedtest --version 2>&1 | grep -q 'Speedtest by Ookla'; then
  echo "STOP: The official Ookla CLI is required at /usr/bin/speedtest." >&2
  exit 1
fi

if [ -z "$pihole_origin" ]; then
  detected_address="$(hostname -I 2>/dev/null | awk '{print $1}')"
  if [ -z "$detected_address" ]; then
    echo "STOP: Pi-hole origin could not be detected.  Supply --pihole-origin." >&2
    exit 1
  fi
  pihole_origin="http://${detected_address}"
fi
if ! [[ "$pihole_origin" =~ ^https?://[A-Za-z0-9._:-]+$ ]]; then
  echo "STOP: --pihole-origin must be one HTTP(S) origin without a path." >&2
  exit 1
fi

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
settings_path="${data_dir}/settings.json"
database_path="${data_dir}/speedtest.db"
recovery_root="/var/lib/pihole-speedtest-install-recovery"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
recovery_dir="${recovery_root}/${timestamp}"
created_user=0
created_application=0
created_environment=0
created_units=0
installation_complete=0

for path in "$application_dir" "$environment_path" "$dashboard_unit_path" "$collection_unit_path" "$timer_unit_path"; do
  if [ -e "$path" ]; then
    echo "STOP: Installation target already exists: $path" >&2
    echo "Use the guarded upgrade workflow for an active installation." >&2
    exit 1
  fi
done
if id "$service_user" >/dev/null 2>&1; then
  echo "STOP: Service account already exists without an active installation: $service_user" >&2
  exit 1
fi
if [ -f "$manifest_path" ] &&
  ! grep -Eq '^(uninstalled_at|failed_install_at)=' "$manifest_path"
then
  echo "STOP: Preserved data does not contain an uninstall or failed-install marker." >&2
  exit 1
fi

rollback() {
  status=$?
  if [ "$status" -eq 0 ] || [ "$installation_complete" -eq 1 ]; then
    return
  fi
  trap - EXIT
  echo "Installation failed.  Restoring the pre-install service state..." >&2
  systemctl disable --now "$timer_unit" >/dev/null 2>&1 || true
  systemctl disable --now "$dashboard_unit" >/dev/null 2>&1 || true
  if [ "$created_units" -eq 1 ]; then
    rm -f -- "$dashboard_unit_path" "$collection_unit_path" "$timer_unit_path"
    systemctl daemon-reload >/dev/null 2>&1 || true
  fi
  if [ "$created_application" -eq 1 ]; then
    rm -rf -- "$application_dir"
  fi
  if [ "$created_environment" -eq 1 ]; then
    rm -f -- "$environment_path"
  fi
  if [ -d "$data_dir" ]; then
    {
      echo "failed_install_at=$timestamp"
      echo "source_commit=$source_commit"
      echo "data_preserved=true"
      echo "recovery_evidence=$recovery_dir"
    } > "$manifest_path"
    chmod 0600 "$manifest_path"
  fi
  if [ "$created_user" -eq 1 ]; then
    userdel "$service_user" >/dev/null 2>&1 || true
  fi
  echo "User data was preserved.  Recovery evidence: $recovery_dir" >&2
  exit "$status"
}
trap rollback EXIT

install -d -m 0700 "$recovery_root" "$recovery_dir"
{
  echo "timestamp=$timestamp"
  echo "source_commit=$source_commit"
  echo "architecture=$architecture"
  echo "python_version=$(python3 --version 2>&1)"
  echo "pihole_core_version=$core_version"
  echo "pihole_origin=$pihole_origin"
  pihole status 2>/dev/null || true
} > "$recovery_dir/preflight.txt"

useradd --system --home-dir "$data_dir" --shell /usr/sbin/nologin --user-group "$service_user"
created_user=1
install -d -m 0755 -o root -g root "$application_dir"
created_application=1
python3 -m venv "$application_dir/venv"
"$application_dir/venv/bin/python" -m pip install "$source_root"

install -d -m 0750 -o "$service_user" -g "$service_user" "$data_dir"
install -d -m 0750 -o "$service_user" -g "$service_user" "$data_dir/backups" "$data_dir/migration"
if [ ! -f "$settings_path" ]; then
  printf '{"collection_interval_minutes":%s}\n' "$interval_minutes" > "$settings_path"
fi
chown -R "$service_user:$service_user" "$data_dir"
chmod 0600 "$settings_path"
interval_minutes="$(python3 - "$settings_path" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as source:
    value = json.load(source).get("collection_interval_minutes")
if value not in {15, 30, 60, 120, 240, 360, 720, 1440}:
    raise SystemExit("STOP: Preserved settings contain an unsupported collection interval.")
print(value)
PY
)"

if [ -f "$database_path" ]; then
  runuser -u "$service_user" -- "$application_dir/venv/bin/python" - "$database_path" <<'PY'
import sqlite3
import sys
with sqlite3.connect(sys.argv[1]) as connection:
    result = connection.execute("PRAGMA integrity_check").fetchone()[0]
if result != "ok":
    raise SystemExit(f"STOP: Preserved SQLite database failed integrity check: {result}")
PY
fi

printf 'PIHOLE_SPEEDTEST_FRAME_ANCESTORS=%s\n' "$pihole_origin" > "$environment_path"
chmod 0600 "$environment_path"
created_environment=1
install -m 0644 "$source_root/deploy/systemd/$dashboard_unit" "$dashboard_unit_path"
install -m 0644 "$source_root/deploy/systemd/$collection_unit" "$collection_unit_path"
install -m 0644 "$source_root/deploy/systemd/$timer_unit" "$timer_unit_path"
created_units=1

systemctl daemon-reload
systemctl enable --now "$dashboard_unit"
health_file="$recovery_dir/dashboard-health.json"
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS http://127.0.0.1:8765/api/health > "$health_file"; then
    break
  fi
  sleep 1
done
python3 - "$health_file" <<'PY'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as source:
    health = json.load(source)
if health.get("status") != "ok":
    raise SystemExit("STOP: Dashboard health verification failed.")
PY

systemctl enable --now "$timer_unit"
systemctl is-active --quiet "$dashboard_unit"
systemctl is-enabled --quiet "$dashboard_unit"
systemctl is-active --quiet "$timer_unit"
systemctl is-enabled --quiet "$timer_unit"

{
  echo "installed_at=$timestamp"
  echo "source_commit=$source_commit"
  echo "database_sha256=$(sha256sum "$database_path" | awk '{print $1}')"
  echo "dashboard_unit_sha256=$(sha256sum "$dashboard_unit_path" | awk '{print $1}')"
  echo "collection_unit_sha256=$(sha256sum "$collection_unit_path" | awk '{print $1}')"
  echo "timer_unit_sha256=$(sha256sum "$timer_unit_path" | awk '{print $1}')"
  echo "environment_sha256=$(sha256sum "$environment_path" | awk '{print $1}')"
  echo "collection_interval_minutes=$interval_minutes"
  echo "pihole_origin=$pihole_origin"
  echo "collection_timer_enabled=true"
  echo "pihole_adapter_installed=false"
} > "$manifest_path"
chown root:root "$manifest_path"
chmod 0600 "$manifest_path"
cp -a "$manifest_path" "$data_dir/collection-manifest.txt"

systemctl status "$dashboard_unit" --no-pager > "$recovery_dir/dashboard-status.after.txt"
systemctl list-timers "$timer_unit" --no-pager > "$recovery_dir/timer-schedule.after.txt"
pihole status > "$recovery_dir/pihole-status.after.txt"
installation_complete=1

echo
echo "=== PI-HOLE SPEEDTEST INSTALLATION PASSED ==="
cat "$health_file"
echo
echo "Dashboard: http://$(hostname -I | awk '{print $1}'):8765/"
echo "Capture frequency: every $interval_minutes minutes"
echo "Collection timer: active and enabled"
echo "Pi-hole sidebar adapter: not installed"
echo "Recovery evidence: $recovery_dir"

#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: sudo scripts/remove_companion_dashboard.sh --expected-commit SHA

Stops and removes a dashboard-only staged installation.  The complete data
directory and deployment files are moved or copied into a timestamped recovery
directory.  Pi-hole web files and configuration are not modified.
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
  echo "STOP: Run this recovery command with sudo." >&2
  exit 1
fi
if ! [[ "$expected_commit" =~ ^[0-9a-f]{40}$ ]]; then
  echo "STOP: --expected-commit must be one full lowercase Git commit SHA." >&2
  exit 1
fi

application_dir="/opt/pihole-speedtest"
data_dir="/var/lib/pihole-speedtest"
service_user="pihole-speedtest"
unit_name="pihole-speedtest-dashboard.service"
unit_path="/etc/systemd/system/${unit_name}"
environment_path="/etc/default/pihole-speedtest-v6"
timer_path="/etc/systemd/system/pihole-speedtest-collect.timer"
manifest_path="${data_dir}/install-manifest.txt"
recovery_root="/var/lib/pihole-speedtest-removal-recovery"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
recovery_dir="${recovery_root}/${timestamp}"

for path in "$application_dir" "$data_dir" "$unit_path" "$environment_path"; do
  if [ ! -e "$path" ]; then
    echo "STOP: Expected staged-install target is missing: $path" >&2
    exit 1
  fi
done
if [ -e "$timer_path" ]; then
  echo "STOP: A collection timer is installed.  This dashboard-only recovery command refuses to continue." >&2
  exit 1
fi
if [ ! -f "$manifest_path" ]; then
  echo "STOP: Installation manifest is missing: $manifest_path" >&2
  exit 1
fi

installed_commit="$(sed -n 's/^source_commit=//p' "$manifest_path")"
if [ "$installed_commit" != "$expected_commit" ]; then
  echo "STOP: Installed source commit does not match the approved commit." >&2
  echo "Expected: $expected_commit" >&2
  echo "Actual:   ${installed_commit:-unknown}" >&2
  exit 1
fi
if [ -e "$recovery_dir" ]; then
  echo "STOP: Recovery destination already exists: $recovery_dir" >&2
  exit 1
fi

install -d -m 0700 "$recovery_root" "$recovery_dir"
cp -a "$unit_path" "$recovery_dir/"
cp -a "$environment_path" "$recovery_dir/"
cp -a "$manifest_path" "$recovery_dir/"
sha256sum \
  "$unit_path" \
  "$environment_path" \
  "$manifest_path" \
  > "$recovery_dir/deployment-files.sha256"
systemctl status "$unit_name" --no-pager > "$recovery_dir/service-status.before.txt" || true
pihole status > "$recovery_dir/pihole-status.before.txt"

systemctl disable --now "$unit_name"
rm -f -- "$unit_path" "$environment_path"
systemctl daemon-reload
mv "$data_dir" "$recovery_dir/data"
rm -rf -- "$application_dir"

if pgrep -u "$service_user" >/dev/null 2>&1; then
  echo "STOP: Service-account processes remain after the service stopped." >&2
  exit 1
fi
userdel "$service_user"

pihole status > "$recovery_dir/pihole-status.after.txt"
{
  echo "removed_at=$timestamp"
  echo "source_commit=$installed_commit"
  echo "data_archive=$recovery_dir/data"
  echo "pihole_web_tree_modified=false"
} > "$recovery_dir/removal-manifest.txt"

echo
echo "=== DASHBOARD-ONLY REMOVAL PASSED ==="
echo "Service and application removed."
echo "Data and deployment evidence preserved at: $recovery_dir"
echo "Pi-hole web files were not modified."

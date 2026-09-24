#!/usr/bin/env bash
set -euo pipefail

required_confirmation="DELETE /var/lib/pihole-speedtest"
confirmation=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --confirm) confirmation="$2"; shift 2 ;;
    --help|-h)
      echo "Usage: sudo scripts/purge_preserved_data.sh --confirm '$required_confirmation'"
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [ "${EUID}" -ne 0 ]; then
  echo "STOP: Run this purge command with sudo." >&2
  exit 1
fi
if [ "$confirmation" != "$required_confirmation" ]; then
  echo "STOP: Exact purge confirmation was not supplied." >&2
  exit 1
fi

data_dir="/var/lib/pihole-speedtest"
if [ "$data_dir" != "/var/lib/pihole-speedtest" ]; then
  echo "STOP: Refusing an unexpected purge target." >&2
  exit 1
fi
for path in \
  /opt/pihole-speedtest \
  /etc/default/pihole-speedtest-v6 \
  /etc/systemd/system/pihole-speedtest-dashboard.service \
  /etc/systemd/system/pihole-speedtest-collect.service \
  /etc/systemd/system/pihole-speedtest-collect.timer
do
  if [ -e "$path" ]; then
    echo "STOP: Active installation target remains: $path" >&2
    exit 1
  fi
done
if id pihole-speedtest >/dev/null 2>&1; then
  echo "STOP: Service account still exists.  Uninstall before purging data." >&2
  exit 1
fi
if [ ! -f "$data_dir/install-manifest.txt" ] ||
  ! grep -q '^uninstalled_at=' "$data_dir/install-manifest.txt"
then
  echo "STOP: Preserved data does not contain a verified uninstall marker." >&2
  exit 1
fi

rm -rf -- "$data_dir"
echo "Preserved Pi-hole Speedtest data was permanently deleted: $data_dir"

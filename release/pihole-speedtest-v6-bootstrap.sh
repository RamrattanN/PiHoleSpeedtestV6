#!/usr/bin/env bash
set -euo pipefail

repository="RamrattanN/PiHoleSpeedtestV6"
version="1.0.3"
source_commit="8db8852cd4b47bf2c7024ec9c08277a1b87ae2f2"
asset_commit="c34765a28b76abc7f184f6ff155da2bd91a9f99b"
bundle_sha256="d29e7aaee356bd422347363079f2b327face738f9adff93fd5dc392c3444b42a"
bundle_name="pihole-speedtest-v6-${version}.tar.gz"
bundle_url="https://raw.githubusercontent.com/${repository}/${asset_commit}/release/${bundle_name}"

usage() {
  cat <<EOF
Usage: $0 ACTION [options]

Actions:
  install          Install the companion and collection timer.
  uninstall        Remove the companion but preserve all user data.
  install-adapter  Add the optional Pi-hole sidebar pages.
  remove-adapter   Remove the optional Pi-hole sidebar pages.
  purge-data       Permanently delete preserved data after uninstall.

Install options are passed to install_release.sh.  Adapter installation accepts
--pihole-origin ORIGIN and --companion-url URL; both are detected from the
device's primary address when omitted.
EOF
}

if [ "$#" -lt 1 ]; then
  usage >&2
  exit 2
fi
action="$1"
shift
case "$action" in
  install|uninstall|install-adapter|remove-adapter|purge-data) ;;
  --help|-h) usage; exit 0 ;;
  *) echo "Unknown action: $action" >&2; usage >&2; exit 2 ;;
esac

for command in curl sha256sum tar sudo mktemp tr hostname awk sed; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "STOP: Required command is unavailable: $command" >&2
    exit 1
  fi
done

work_dir="$(mktemp -d)"
trap 'rm -rf -- "$work_dir"' EXIT
bundle_path="$work_dir/$bundle_name"

curl --fail --show-error --silent --location \
  --proto '=https' --tlsv1.2 \
  --output "$bundle_path" \
  "$bundle_url"
printf '%s  %s\n' "$bundle_sha256" "$bundle_path" |
  sha256sum --check --status -

tar --extract --gzip --file "$bundle_path" --directory "$work_dir"
source_root="$work_dir/pihole-speedtest-v6-${version}"
source_marker="$source_root/release/SOURCE-COMMIT"
if [ ! -f "$source_marker" ] || [ "$(tr -d '\r\n' < "$source_marker")" != "$source_commit" ]; then
  echo "STOP: Verified bundle source marker is invalid." >&2
  exit 1
fi

case "$action" in
  install)
    sudo bash "$source_root/scripts/install_release.sh" \
      --source-commit "$source_commit" "$@"
    ;;
  uninstall)
    if [ "$#" -ne 0 ]; then
      echo "STOP: uninstall does not accept additional options." >&2
      exit 2
    fi
    sudo bash "$source_root/scripts/uninstall_release.sh" \
      --expected-commit "$source_commit"
    ;;
  install-adapter)
    pihole_origin=""
    companion_url=""
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --pihole-origin) pihole_origin="$2"; shift 2 ;;
        --companion-url) companion_url="$2"; shift 2 ;;
        *) echo "Unknown adapter option: $1" >&2; exit 2 ;;
      esac
    done
    if [ -z "$pihole_origin" ] || [ -z "$companion_url" ]; then
      device_address="$(hostname -I 2>/dev/null | awk '{print $1}')"
      if [ -z "$device_address" ]; then
        echo "STOP: Device address could not be detected.  Supply both origins." >&2
        exit 1
      fi
      pihole_origin="${pihole_origin:-http://${device_address}}"
      companion_url="${companion_url:-http://${device_address}:8765}"
    fi
    installed_commit="$(
      sudo sed -n 's/^source_commit=//p' \
        /var/lib/pihole-speedtest/install-manifest.txt
    )"
    if ! [[ "$installed_commit" =~ ^[0-9a-f]{40}$ ]]; then
      echo "STOP: Installed companion commit could not be verified." >&2
      exit 1
    fi
    sudo bash "$source_root/scripts/install_pihole_adapter.sh" \
      --expected-source-commit "$source_commit" \
      --expected-installed-commit "$installed_commit" \
      --companion-url "$companion_url" \
      --pihole-origin "$pihole_origin"
    ;;
  remove-adapter)
    if [ "$#" -ne 0 ]; then
      echo "STOP: remove-adapter does not accept additional options." >&2
      exit 2
    fi
    sudo bash "$source_root/scripts/remove_pihole_adapter.sh"
    ;;
  purge-data)
    sudo bash "$source_root/scripts/purge_preserved_data.sh" "$@"
    ;;
esac

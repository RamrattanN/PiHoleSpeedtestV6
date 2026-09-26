#!/usr/bin/env bash
set -euo pipefail

repository="RamrattanN/PiHoleSpeedtestV6"
version="1.0.6"
source_commit="1ff5cc315d5fd7e15781793ad3c646d1649b83f8"
asset_commit="136773d6fd83fbd7abc0cf6bd657c497b1d3038e"
bundle_sha256="970a835df12ac165f07706c5b17af826b8020effbe6e43ee199d7c7f33b52108"
bundle_name="pihole-speedtest-v6-${version}.tar.gz"
bundle_url="https://raw.githubusercontent.com/${repository}/${asset_commit}/release/${bundle_name}"

usage() {
  cat <<EOF
Usage: $0 ACTION [options]

Actions:
  install-all      Install or upgrade the companion, then add the Pi-hole
                   sidebar pages.  Accepts --pihole-origin ORIGIN,
                   --companion-url URL, and --interval-minutes NUMBER.
  uninstall-all    Remove the sidebar pages if present, then the companion.
                   All user data is preserved.
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
  install-all|uninstall-all|install|uninstall|install-adapter|remove-adapter|purge-data) ;;
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

read_installed_commit() {
  installed_manifest="/var/lib/pihole-speedtest/install-manifest.txt"
  if ! sudo test -f "$installed_manifest"; then
    echo "STOP: Installed companion manifest could not be found." >&2
    return 1
  fi
  installed_commit="$(
    sudo sed -n 's/^source_commit=//p' "$installed_manifest"
  )"
  if ! [[ "$installed_commit" =~ ^[0-9a-f]{40}$ ]]; then
    echo "STOP: Installed companion commit could not be verified." >&2
    return 1
  fi
  printf '%s\n' "$installed_commit"
}

# Full-product actions compose the verified granular phases above.  They never
# delete user data; permanent deletion remains the separate purge-data action.
data_dir="/var/lib/pihole-speedtest"
product_manifest="${data_dir}/install-manifest.txt"
application_dir="/opt/pihole-speedtest"
environment_path="/etc/default/pihole-speedtest-v6"
unit_dir="/etc/systemd/system"
dashboard_unit="pihole-speedtest-dashboard.service"
collection_unit="pihole-speedtest-collect.service"
timer_unit="pihole-speedtest-collect.timer"
service_user="pihole-speedtest"
sidebar_path="/var/www/html/admin/scripts/lua/sidebar.lp"
overview_path="/var/www/html/admin/speedtest.lp"
setup_path="/var/www/html/admin/speedtest-setup.lp"
health_url="http://127.0.0.1:8765/api/health"
phase_prefix=""
current_phase=""
pihole_origin=""
companion_url=""
interval_minutes=""
adapter_attempted=0

phase() {
  current_phase="$phase_prefix $1: $2"
  echo
  echo "== $current_phase =="
}

manifest_value() {
  sudo sed -n "s/^$1=//p" "$product_manifest" 2>/dev/null | tail -n 1 || true
}

companion_state() {
  if sudo test -d "$application_dir"; then
    if sudo test -f "$product_manifest"; then
      echo installed
    else
      echo partial
    fi
  elif sudo test -e "$environment_path" ||
    sudo test -e "$unit_dir/$dashboard_unit" ||
    sudo test -e "$unit_dir/$collection_unit" ||
    sudo test -e "$unit_dir/$timer_unit" ||
    id "$service_user" >/dev/null 2>&1
  then
    echo partial
  elif sudo test -f "$product_manifest"; then
    echo preserved
  else
    echo absent
  fi
}

detect_origins() {
  if [ -z "$pihole_origin" ]; then
    device_address="$(hostname -I 2>/dev/null | awk '{print $1}')"
    if [ -z "$device_address" ]; then
      echo "STOP: Device address could not be detected.  Supply --pihole-origin and --companion-url." >&2
      exit 1
    fi
    web_domain="$(sudo pihole-FTL --config webserver.domain 2>/dev/null || true)"
    web_ports="$(sudo pihole-FTL --config webserver.port 2>/dev/null || true)"
    tls_certificate="$(sudo pihole-FTL --config webserver.tls.cert 2>/dev/null || true)"
    if [ -n "$web_domain" ] &&
      printf '%s' "$web_ports" | grep -Eq '(^|,)([^,]*:)?443[^,]*s' &&
      [ "$tls_certificate" = "/etc/pihole/tls.pem" ] &&
      sudo test -f "$tls_certificate"
    then
      pihole_origin="https://${web_domain}"
    else
      pihole_origin="http://${device_address}"
    fi
  fi
  if [ -z "$companion_url" ]; then
    companion_url="$(python3 - "$pihole_origin" <<'PY'
import sys
from urllib.parse import urlparse

parsed = urlparse(sys.argv[1])
host = parsed.hostname or ""
if ":" in host:
    host = f"[{host}]"
print(f"{parsed.scheme}://{host}:8765")
PY
)"
  fi
  if [[ "$companion_url" == https://* ]]; then
    health_url="https://127.0.0.1:8765/api/health"
  fi
}

pihole_curl() {
  url="$1"
  shift
  if [[ "$pihole_origin" == https://* ]]; then
    mapfile -t pihole_target < <(python3 - "$pihole_origin" <<'PY'
import sys
from urllib.parse import urlparse

parsed = urlparse(sys.argv[1])
print(parsed.hostname)
print(parsed.port or 443)
PY
)
    curl -kfsS --resolve "${pihole_target[0]}:${pihole_target[1]}:127.0.0.1" "$@" "$url"
  else
    curl -fsS "$@" "$url"
  fi
}

verify_dashboard() {
  health=""
  for attempt in 1 2 3 4 5 6 7 8 9 10; do
    if [[ "$health_url" == https://* ]]; then
      health="$(curl -kfsS "$health_url" 2>/dev/null)" || health=""
    else
      health="$(curl -fsS "$health_url" 2>/dev/null)" || health=""
    fi
    if [ -n "$health" ]; then
      break
    fi
    sleep 1
  done
  if ! printf '%s' "$health" | grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"'; then
    echo "STOP: Companion dashboard health check failed: $health_url" >&2
    return 1
  fi
  if ! printf '%s' "$health" | grep -Eq "\"version\"[[:space:]]*:[[:space:]]*\"${version//./\\.}\""; then
    echo "STOP: Companion dashboard does not report version $version." >&2
    return 1
  fi
  echo "Dashboard health: ok, version $version"
}

verify_single_timer() {
  enabled_timers="$(
    systemctl list-unit-files --type=timer --state=enabled --no-legend 'pihole-speedtest*' |
      awk '{print $1}'
  )"
  if [ "$enabled_timers" != "$timer_unit" ]; then
    echo "STOP: Expected exactly one enabled collection timer: $timer_unit" >&2
    echo "Found: ${enabled_timers:-none}" >&2
    return 1
  fi
  if ! systemctl is-active --quiet "$timer_unit"; then
    echo "STOP: Collection timer is enabled but not active: $timer_unit" >&2
    return 1
  fi
  echo "Collection timer: exactly one enabled and active"
}

verify_pihole() {
  if ! systemctl is-active --quiet pihole-FTL; then
    echo "STOP: Pi-hole FTL is not active." >&2
    return 1
  fi
  if [ -n "${1:-}" ] && ! pihole_curl "$1/admin/" -o /dev/null; then
    echo "STOP: Pi-hole web interface did not respond at $1/admin/" >&2
    return 1
  fi
  echo "Pi-hole: FTL active${1:+ and web interface responding}"
}

verify_adapter_installed() {
  adapter_manifest="$(manifest_value pihole_adapter_manifest)"
  if [ "$(manifest_value pihole_adapter_installed)" != "true" ] ||
    [ -z "$adapter_manifest" ] ||
    ! sudo test -f "$adapter_manifest"
  then
    echo "STOP: Deployment manifest does not record a valid sidebar adapter." >&2
    return 1
  fi
  if ! sudo python3 - "$adapter_manifest" <<'PY'
import hashlib
import json
import pathlib
import sys


def sha256(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


manifest = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
if sha256(manifest["sidebar"]["path"]) != manifest["sidebar"]["installed_sha256"]:
    raise SystemExit("STOP: Installed sidebar does not match the adapter manifest.")
for created in manifest["created"]:
    if sha256(created["path"]) != created["sha256"]:
        raise SystemExit(f"STOP: Adapter page does not match its manifest: {created['path']}")
PY
  then
    return 1
  fi
  for page in speedtest speedtest-setup; do
    if ! pihole_curl "$pihole_origin/admin/$page" -o /dev/null; then
      echo "STOP: Pi-hole did not serve $pihole_origin/admin/$page" >&2
      return 1
    fi
  done
  echo "Sidebar adapter: manifest, sidebar, and wrapper pages verified"
}

verify_adapter_absent() {
  if [ "$(manifest_value pihole_adapter_installed)" = "true" ]; then
    echo "STOP: Deployment manifest still records an installed sidebar adapter." >&2
    return 1
  fi
  if sudo test -e "$overview_path" || sudo test -e "$setup_path"; then
    echo "STOP: Sidebar adapter pages remain in the Pi-hole web tree." >&2
    return 1
  fi
  if sudo test -f "$sidebar_path" && sudo grep -q 'PIHOLE-SPEEDTEST-V6' "$sidebar_path"; then
    echo "STOP: The Pi-hole sidebar still contains adapter markers." >&2
    return 1
  fi
  if [ -n "${1:-}" ] && ! sudo python3 - "$1" <<'PY'
import hashlib
import json
import pathlib
import sys


manifest = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
sidebar = pathlib.Path(manifest["sidebar"]["path"])
if hashlib.sha256(sidebar.read_bytes()).hexdigest() != manifest["sidebar"]["before_sha256"]:
    raise SystemExit("STOP: The Pi-hole sidebar was not restored to its original content.")
PY
  then
    return 1
  fi
  echo "Pi-hole web files: no adapter pages or sidebar markers present"
}

verify_data_preserved() {
  for path in "$data_dir/speedtest.db" "$product_manifest"; do
    if ! sudo test -f "$path"; then
      echo "STOP: Preserved data is missing: $path" >&2
      return 1
    fi
  done
  if [ "$1" -eq 1 ] && ! sudo test -f "$data_dir/settings.json"; then
    echo "STOP: Preserved settings are missing: $data_dir/settings.json" >&2
    return 1
  fi
  if ! sudo grep -q '^uninstalled_at=' "$product_manifest"; then
    echo "STOP: Preserved manifest does not record the completed uninstall." >&2
    return 1
  fi
  echo "User data preserved: $data_dir"
}

verify_companion_absent() {
  for path in "$application_dir" "$environment_path" \
    "$unit_dir/$dashboard_unit" "$unit_dir/$collection_unit" "$unit_dir/$timer_unit"
  do
    if sudo test -e "$path"; then
      echo "STOP: Companion file remains after uninstall: $path" >&2
      return 1
    fi
  done
  if [ -n "$(systemctl list-unit-files --no-legend 'pihole-speedtest*' | awk '{print $1}')" ]; then
    echo "STOP: Companion systemd units remain registered." >&2
    return 1
  fi
  if id "$service_user" >/dev/null 2>&1; then
    echo "STOP: Companion service account remains: $service_user" >&2
    return 1
  fi
  echo "Companion application, services, timer, and service account are absent"
}

remove_installed_product() {
  phase 2/7 "Remove the Pi-hole sidebar adapter"
  removal_manifest=""
  if [ "$(manifest_value pihole_adapter_installed)" = "true" ]; then
    removal_manifest="$(manifest_value pihole_adapter_manifest)"
    sudo bash "$source_root/scripts/remove_pihole_adapter.sh"
  else
    echo "Sidebar adapter is not installed; nothing to remove."
  fi

  phase 3/7 "Verify the original Pi-hole web state"
  verify_adapter_absent "$removal_manifest"

  phase 4/7 "Uninstall the companion"
  had_settings=0
  if sudo test -f "$data_dir/settings.json"; then
    had_settings=1
  fi
  installed_commit="$(read_installed_commit)"
  sudo bash "$source_root/scripts/uninstall_release.sh" \
    --expected-commit "$installed_commit"

  phase 5/7 "Verify preserved user data"
  verify_data_preserved "$had_settings"

  phase 6/7 "Verify Pi-hole"
  verify_pihole ""

  phase 7/7 "Verify companion removal"
  verify_companion_absent
}

run_uninstall_all() {
  if [ "$#" -ne 0 ]; then
    echo "STOP: uninstall-all does not accept additional options." >&2
    exit 2
  fi
  phase_prefix="uninstall-all"
  phase 1/7 "Detect the installed product"
  case "$(companion_state)" in
    absent)
      echo "Pi-hole Speedtest is not installed.  Nothing was changed."
      return 0
      ;;
    preserved)
      echo "The companion is already uninstalled.  Nothing was changed."
      echo "Preserved data remains at $data_dir"
      return 0
      ;;
    partial)
      echo "STOP: An incomplete companion installation was found.  Nothing was changed." >&2
      echo "Review the recovery evidence under /var/lib/pihole-speedtest-*-recovery." >&2
      exit 1
      ;;
  esac
  echo "Installed commit: $(read_installed_commit)"
  echo "Sidebar adapter installed: $(manifest_value pihole_adapter_installed)"
  remove_installed_product
  echo
  echo "=== PI-HOLE SPEEDTEST REMOVED; USER DATA PRESERVED ==="
  echo "Preserved data: $data_dir"
  echo "A later install reuses this history and these settings."
}

install_companion() {
  if [ -n "$interval_minutes" ]; then
    sudo bash "$source_root/scripts/install_release.sh" \
      --source-commit "$source_commit" \
      --pihole-origin "$pihole_origin" \
      --companion-url "$companion_url" \
      --interval-minutes "$interval_minutes"
  else
    sudo bash "$source_root/scripts/install_release.sh" \
      --source-commit "$source_commit" \
      --pihole-origin "$pihole_origin" \
      --companion-url "$companion_url"
  fi
}

companion_failure() {
  echo >&2
  echo "STOP: install-all failed during $current_phase" >&2
  echo "Measurement history, settings, and recovery evidence were preserved." >&2
  echo "To remove the product while keeping data, use the checksum-verified uninstall runner." >&2
  current_phase=""
  exit 1
}

adapter_failure() {
  echo >&2
  echo "STOP: install-all failed during $current_phase" >&2
  if [ "$adapter_attempted" -eq 1 ] &&
    [ "$(manifest_value pihole_adapter_installed)" = "true" ]
  then
    echo "Removing the sidebar adapter installed by this run..." >&2
    sudo bash "$source_root/scripts/remove_pihole_adapter.sh" >&2 ||
      echo "WARNING: Automatic sidebar adapter removal failed." >&2
  fi
  if verify_adapter_absent "" >&2; then
    echo "Pi-hole web files contain no sidebar adapter changes." >&2
  else
    echo "WARNING: Sidebar adapter changes may remain." >&2
    echo "Recovery evidence: /var/lib/pihole-speedtest-adapter-recovery" >&2
  fi
  echo "The companion, measurement history, settings, and recovery evidence were preserved." >&2
  echo "Dashboard: $companion_url/" >&2
  echo "After resolving the problem, rerun the same checksum-verified install command." >&2
  echo "To remove the product while keeping data, use the checksum-verified uninstall runner." >&2
  current_phase=""
  exit 1
}

report_full_action_stop() {
  status=$?
  rm -rf -- "$work_dir"
  if [ "$status" -ne 0 ] && [ -n "$current_phase" ]; then
    echo >&2
    echo "STOP: $action stopped during $current_phase" >&2
    echo "User data under $data_dir was not deleted." >&2
  fi
  exit "$status"
}

run_install_all() {
  while [ "$#" -gt 0 ]; do
    if [ "$#" -lt 2 ]; then
      echo "STOP: Option requires a value: $1" >&2
      exit 2
    fi
    case "$1" in
      --pihole-origin) pihole_origin="$2" ;;
      --companion-url) companion_url="$2" ;;
      --interval-minutes) interval_minutes="$2" ;;
      *) echo "Unknown install-all option: $1" >&2; exit 2 ;;
    esac
    shift 2
  done
  detect_origins
  phase_prefix="install-all"

  phase 1/7 "Install or upgrade the companion"
  case "$(companion_state)" in
    installed)
      installed_commit="$(read_installed_commit)"
      if [ "$installed_commit" = "$source_commit" ]; then
        echo "Version $version is already installed; keeping it and its data."
      else
        echo "Installed commit $installed_commit will be upgraded by a data-preserving reinstall."
        phase_prefix="upgrade"
        remove_installed_product
        phase_prefix="install-all"
        phase 1/7 "Install the companion"
        install_companion
      fi
      ;;
    absent|preserved)
      install_companion
      ;;
    *)
      echo "STOP: An incomplete companion installation was found.  Nothing was changed." >&2
      echo "Review the recovery evidence under /var/lib/pihole-speedtest-*-recovery." >&2
      exit 1
      ;;
  esac

  phase 2/7 "Verify dashboard health"
  verify_dashboard || companion_failure

  phase 3/7 "Verify the collection timer"
  verify_single_timer || companion_failure

  phase 4/7 "Install the Pi-hole sidebar adapter"
  if [ "$(manifest_value pihole_adapter_installed)" = "true" ]; then
    echo "Sidebar adapter is already installed; verifying it."
  else
    installed_commit="$(read_installed_commit)"
    adapter_attempted=1
    sudo bash "$source_root/scripts/install_pihole_adapter.sh" \
      --expected-source-commit "$source_commit" \
      --expected-installed-commit "$installed_commit" \
      --companion-url "$companion_url" \
      --pihole-origin "$pihole_origin" || adapter_failure
  fi

  phase 5/7 "Verify Pi-hole"
  verify_pihole "$pihole_origin" || adapter_failure

  phase 6/7 "Verify the sidebar adapter"
  verify_adapter_installed || adapter_failure

  phase 7/7 "Report addresses"
  echo
  echo "=== PI-HOLE SPEEDTEST $version INSTALLED ==="
  echo "Dashboard: $companion_url/"
  echo "Pi-hole Overview: $pihole_origin/admin/speedtest"
  echo "Pi-hole Setup: $pihole_origin/admin/speedtest-setup"
  echo "Collection timer: $timer_unit"
  echo "Data: $data_dir"
}

case "$action" in
  install-all)
    for command in python3 systemctl grep id pihole-FTL; do
      if ! command -v "$command" >/dev/null 2>&1; then
        echo "STOP: Required command is unavailable: $command" >&2
        exit 1
      fi
    done
    trap report_full_action_stop EXIT
    run_install_all "$@"
    ;;
  uninstall-all)
    for command in python3 systemctl grep id; do
      if ! command -v "$command" >/dev/null 2>&1; then
        echo "STOP: Required command is unavailable: $command" >&2
        exit 1
      fi
    done
    trap report_full_action_stop EXIT
    run_uninstall_all "$@"
    ;;
  install)
    sudo bash "$source_root/scripts/install_release.sh" \
      --source-commit "$source_commit" "$@"
    ;;
  uninstall)
    if [ "$#" -ne 0 ]; then
      echo "STOP: uninstall does not accept additional options." >&2
      exit 2
    fi
    installed_commit="$(read_installed_commit)"
    sudo bash "$source_root/scripts/uninstall_release.sh" \
      --expected-commit "$installed_commit"
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
    if [ -z "$pihole_origin" ]; then
      pihole_origin="$(manifest_value pihole_origin)"
    fi
    if [ -z "$companion_url" ]; then
      companion_url="$(manifest_value companion_url)"
    fi
    if [ -z "$pihole_origin" ] || [ -z "$companion_url" ]; then
      echo "STOP: Installed origins could not be read.  Supply both origins explicitly." >&2
      exit 1
    fi
    installed_commit="$(read_installed_commit)"
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

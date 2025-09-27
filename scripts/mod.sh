#!/usr/bin/env bash
# Pi-hole Speedtest v6 compatible installer
# - No network fetch.  Installs local web assets and sets up a cron job or systemd timer.
set -euo pipefail

# Defaults
WEB_SUBDIR="speedtest"
DATA_DIR_DEFAULT="/etc/pihole/speedtest"
CRON_DEFAULT="*/30 * * * *"
FORCE=0
CRON_SPEC=""
DATA_DIR=""
INSTALL_WEB=1
SETUP_SCHEDULE=1

usage() {
  cat <<'USAGE'
Usage: mod.sh [options]
  --data-dir <path>       Directory to store CSV and JSON output.  Default: /etc/pihole/speedtest
  --no-web                Do not install web assets.
  --no-schedule           Do not create a cron job or systemd timer.
  --cron "<spec>"         Cron spec for schedule.  Default: */30 * * * *
  --force                 Proceed even if some checks fail.
  -h, --help              Show help.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --data-dir) DATA_DIR="${2:-}"; shift 2;;
    --no-web) INSTALL_WEB=0; shift;;
    --no-schedule) SETUP_SCHEDULE=0; shift;;
    --cron) CRON_SPEC="${2:-}"; shift 2;;
    --force) FORCE=1; shift;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown option: $1" >&2; usage; exit 2;;
  esac
done

# Detect Pi-hole web root for v6 safely
detect_web_root() {
  local candidates=(
    "/var/www/html"                # common
    "/var/www/pihole"              # alt
  )
  for p in "${candidates[@]}"; do
    if [[ -d "$p" ]]; then
      echo "$p"
      return 0
    fi
  done
  return 1
}

require_cmd() { command -v "$1" >/dev/null 2>&1; }

if ! require_cmd bash || ! require_cmd awk || ! require_cmd sed; then
  echo "Missing basic shell tools.  Please install bash sed awk." >&2
  [[ $FORCE -eq 1 ]] || exit 3
fi

WEB_ROOT=""
if [[ $INSTALL_WEB -eq 1 ]]; then
  if WEB_ROOT="$(detect_web_root)"; then
    :
  else
    echo "Could not detect Pi-hole web root.  Use --no-web or create one of the known paths." >&2
    [[ $FORCE -eq 1 ]] || exit 4
  fi
fi

DATA_DIR="${DATA_DIR:-$DATA_DIR_DEFAULT}"
mkdir -p "$DATA_DIR"

# Install web assets if requested
if [[ $INSTALL_WEB -eq 1 && -n "${WEB_ROOT:-}" ]]; then
  mkdir -p "${WEB_ROOT}/${WEB_SUBDIR}"
  SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
  ASSET_DIR="$(cd "$SCRIPT_DIR/../web" && pwd)"
  cp -f "${ASSET_DIR}/speedtest.html" "${WEB_ROOT}/${WEB_SUBDIR}/index.html"
  cp -f "${ASSET_DIR}/speedtest.js" "${WEB_ROOT}/${WEB_SUBDIR}/speedtest.js"
  # Create a lightweight JSON symlink if web root can read data dir
  if [[ -w "${WEB_ROOT}/${WEB_SUBDIR}" ]]; then
    ln -sf "${DATA_DIR}/speedtest.json" "${WEB_ROOT}/${WEB_SUBDIR}/speedtest.json" || true
  fi
  echo "Installed web assets to ${WEB_ROOT}/${WEB_SUBDIR}"
fi

# Install runner into a standard path
INSTALL_BIN="/usr/local/bin/pihole-speedtest"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
install -m 0755 "${SCRIPT_DIR}/speedtest.sh" "$INSTALL_BIN"
echo "Installed runner at ${INSTALL_BIN}"

# Create default config env file for the runner
ENV_FILE="/etc/default/pihole-speedtest"
mkdir -p "$(dirname "$ENV_FILE")"
cat > "$ENV_FILE" <<EOF
# Environment for pihole-speedtest runner
SPEEDTEST_DATA_DIR="${DATA_DIR}"
SPEEDTEST_BIN="speedtest"
SPEEDTEST_INTERVAL_SECONDS=0
EOF
chmod 0644 "$ENV_FILE"
echo "Wrote ${ENV_FILE}"

# Setup schedule with cron by default
if [[ $SETUP_SCHEDULE -eq 1 ]]; then
  require_cmd crontab || { echo "crontab not found.  Skipping schedule."; exit 0; }
  SPEC="${CRON_SPEC:-$CRON_DEFAULT}"
  # Write a marker to let users identify the entry
  TMPF="$(mktemp)"
  crontab -l 2>/dev/null | sed '/# pihole-speedtest v6/d;/pihole-speedtest/d' > "$TMPF" || true
  echo "${SPEC} . /etc/default/pihole-speedtest >/dev/null 2>&1; ${INSTALL_BIN} -o "${DATA_DIR}" # pihole-speedtest v6" >> "$TMPF"
  crontab "$TMPF"
  rm -f "$TMPF"
  echo "Scheduled runner with cron: ${SPEC}"
fi

echo "Done."

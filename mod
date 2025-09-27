#!/usr/bin/env bash
# Local wrapper for Pi-hole Speedtest v6 safe mod installer
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
exec "${SCRIPT_DIR}/scripts/mod.sh" "$@"

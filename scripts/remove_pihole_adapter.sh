#!/usr/bin/env bash
set -euo pipefail

if [ "${EUID}" -ne 0 ]; then
  echo "STOP: Run this command with sudo." >&2
  exit 1
fi

application_cli="/opt/pihole-speedtest/venv/bin/pihole-speedtest"
application_python="/opt/pihole-speedtest/venv/bin/python"
data_dir="/var/lib/pihole-speedtest"
install_manifest="${data_dir}/install-manifest.txt"
collection_manifest="${data_dir}/collection-manifest.txt"

for path in "$application_cli" "$install_manifest" "$collection_manifest"; do
  if [ ! -e "$path" ]; then
    echo "STOP: Required installed target is missing: $path" >&2
    exit 1
  fi
done
if [ "$(sed -n 's/^pihole_adapter_installed=//p' "$install_manifest")" != "true" ]; then
  echo "STOP: Deployment manifest does not record an installed adapter." >&2
  exit 1
fi
adapter_manifest="$(sed -n 's/^pihole_adapter_manifest=//p' "$install_manifest")"
if [ -z "$adapter_manifest" ] || [ ! -f "$adapter_manifest" ]; then
  echo "STOP: Adapter recovery manifest is missing." >&2
  exit 1
fi
recovery_dir="$(dirname "$adapter_manifest")"
headers_before="$recovery_dir/pihole-web-headers.before.json"
headers_installed="$recovery_dir/pihole-web-headers.installed.json"
restore_headers=0
if [ -e "$headers_before" ] || [ -e "$headers_installed" ]; then
  if [ ! -s "$headers_before" ] || [ ! -s "$headers_installed" ]; then
    echo "STOP: Pi-hole web header recovery evidence is incomplete." >&2
    exit 1
  fi
  "$application_python" - /etc/pihole/pihole.toml "$headers_installed" <<'PY'
import json
import sys
import tomllib


with open(sys.argv[1], "rb") as source:
    actual = tomllib.load(source)["webserver"]["headers"]
with open(sys.argv[2], encoding="utf-8") as source:
    expected = json.load(source)
if actual != expected:
    raise SystemExit(
        "STOP: Pi-hole web headers changed after adapter installation; "
        "refusing to overwrite them."
    )
PY
  restore_headers=1
fi
cp -a "$install_manifest" "$recovery_dir/install-manifest.before-removal.txt"
cp -a "$collection_manifest" "$recovery_dir/collection-manifest.before-removal.txt"

"$application_cli" adapter-remove --manifest "$adapter_manifest"

if [ "$restore_headers" -eq 1 ]; then
  pihole-FTL --config webserver.headers "$(cat "$headers_before")"
  "$application_python" - /etc/pihole/pihole.toml "$headers_before" <<'PY'
import json
import sys
import tomllib


with open(sys.argv[1], "rb") as source:
    actual = tomllib.load(source)["webserver"]["headers"]
with open(sys.argv[2], encoding="utf-8") as source:
    expected = json.load(source)
if actual != expected:
    raise SystemExit("Pi-hole web header configuration was not restored exactly")
PY
fi

python3 - "$install_manifest" "$collection_manifest" <<'PY'
import os
import pathlib
import tempfile
import sys


for raw_path in sys.argv[1:]:
    path = pathlib.Path(raw_path)
    lines = [
        line for line in path.read_text(encoding="utf-8").splitlines()
        if not line.startswith("pihole_adapter_installed=")
        and not line.startswith("pihole_adapter_manifest=")
    ]
    lines.append("pihole_adapter_installed=false")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
            destination.write("\n".join(lines) + "\n")
            destination.flush()
            os.fsync(destination.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
PY

echo
echo "=== LIVE PI-HOLE SIDEBAR ADAPTER REMOVED ==="
echo "Original sidebar restored through: $adapter_manifest"
if [ "$restore_headers" -eq 1 ]; then
  echo "Original Pi-hole web header configuration restored exactly."
else
  echo "Legacy adapter had no Pi-hole web header change to restore."
fi
echo "Removal evidence: $recovery_dir/removal.json"

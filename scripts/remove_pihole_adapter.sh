#!/usr/bin/env bash
set -euo pipefail

if [ "${EUID}" -ne 0 ]; then
  echo "STOP: Run this command with sudo." >&2
  exit 1
fi

application_cli="/opt/pihole-speedtest/venv/bin/pihole-speedtest"
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
cp -a "$install_manifest" "$recovery_dir/install-manifest.before-removal.txt"
cp -a "$collection_manifest" "$recovery_dir/collection-manifest.before-removal.txt"

"$application_cli" adapter-remove --manifest "$adapter_manifest"

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
echo "Removal evidence: $recovery_dir/removal.json"

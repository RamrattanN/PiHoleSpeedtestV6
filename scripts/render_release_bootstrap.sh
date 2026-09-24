#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/render_release_bootstrap.sh \
  --source-commit SHA \
  --asset-commit SHA \
  --bundle-sha256 SHA256 \
  --output PATH
EOF
}

source_commit=""
asset_commit=""
bundle_sha256=""
output=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-commit) source_commit="$2"; shift 2 ;;
    --asset-commit) asset_commit="$2"; shift 2 ;;
    --bundle-sha256) bundle_sha256="$2"; shift 2 ;;
    --output) output="$2"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

for value in source_commit asset_commit; do
  if ! [[ "${!value}" =~ ^[0-9a-f]{40}$ ]]; then
    echo "STOP: --${value//_/-} must be one full lowercase Git commit SHA." >&2
    exit 1
  fi
done
if ! [[ "$bundle_sha256" =~ ^[0-9a-f]{64}$ ]]; then
  echo "STOP: --bundle-sha256 must be one lowercase SHA-256 value." >&2
  exit 1
fi
if [ -z "$output" ]; then
  echo "STOP: --output is required." >&2
  exit 1
fi

source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
sed \
  -e "s/@SOURCE_COMMIT@/$source_commit/g" \
  -e "s/@ASSET_COMMIT@/$asset_commit/g" \
  -e "s/@BUNDLE_SHA256@/$bundle_sha256/g" \
  "$source_root/release/bootstrap.template.sh" > "$output"
chmod 0755 "$output"

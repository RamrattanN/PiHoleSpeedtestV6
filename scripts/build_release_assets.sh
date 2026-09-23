#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/build_release_assets.sh \
  --source-commit SHA \
  [--archive-commit SHA] \
  --output-directory PATH

Builds a deterministic source bundle containing a release source marker.
The archive commit defaults to the clean current HEAD.  The source commit is
the immutable published commit recorded inside the bundle.  Rendering the
public bootstrap happens later, after the bundle has an immutable asset commit.
EOF
}

source_commit=""
archive_commit=""
output_directory=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-commit) source_commit="$2"; shift 2 ;;
    --archive-commit) archive_commit="$2"; shift 2 ;;
    --output-directory) output_directory="$2"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if ! [[ "$source_commit" =~ ^[0-9a-f]{40}$ ]]; then
  echo "STOP: --source-commit must be one full lowercase Git commit SHA." >&2
  exit 1
fi
if [ -z "$archive_commit" ]; then
  archive_commit="$(git -C "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)" rev-parse HEAD)"
fi
if ! [[ "$archive_commit" =~ ^[0-9a-f]{40}$ ]]; then
  echo "STOP: --archive-commit must be one full lowercase Git commit SHA." >&2
  exit 1
fi
if [ -z "$output_directory" ]; then
  echo "STOP: --output-directory is required." >&2
  exit 1
fi

source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
if [ "$(git -C "$source_root" rev-parse HEAD)" != "$archive_commit" ]; then
  echo "STOP: --archive-commit is not the current HEAD." >&2
  exit 1
fi
if ! git -C "$source_root" diff --quiet -- ||
  ! git -C "$source_root" diff --cached --quiet --
then
  echo "STOP: Source worktree has tracked changes." >&2
  exit 1
fi

version="$(sed -n 's/^version = "\([^"]*\)"/\1/p' "$source_root/pyproject.toml")"
if [ -z "$version" ]; then
  echo "STOP: Project version could not be read." >&2
  exit 1
fi
bundle_root="pihole-speedtest-v6-${version}"
bundle_name="${bundle_root}.tar.gz"
work_dir="$(mktemp -d)"
trap 'rm -rf -- "$work_dir"' EXIT
mkdir -p "$work_dir/$bundle_root/release" "$output_directory"

git -C "$source_root" archive "$archive_commit" |
  tar -x -C "$work_dir/$bundle_root"
printf '%s\n' "$source_commit" > "$work_dir/$bundle_root/release/SOURCE-COMMIT"

tar --sort=name \
  --mtime='UTC 1970-01-01' \
  --owner=0 --group=0 --numeric-owner \
  -C "$work_dir" -cf - "$bundle_root" |
  gzip -n > "$output_directory/$bundle_name"
sha256sum "$output_directory/$bundle_name" > "$output_directory/${bundle_name}.sha256"
echo "$output_directory/$bundle_name"

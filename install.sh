#!/usr/bin/env bash
# Ramrattan Pi-hole Speedtest convenience runner.
#
#   curl -fsSL https://raw.githubusercontent.com/RamrattanN/PiHoleSpeedtestV6/main/install.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/RamrattanN/PiHoleSpeedtestV6/main/install.sh | bash -s -- uninstall
#
# Prerelease acceptance selects one exact release tag instead of the latest
# stable release:
#
#   curl -fsSL https://raw.githubusercontent.com/RamrattanN/PiHoleSpeedtestV6/main/install.sh | PIHOLE_SPEEDTEST_RELEASE_TAG=v1.0.6-rc.1 bash
#
# Downloads the production bootstrap and its published checksum from the
# selected GitHub Release, verifies the bootstrap, and runs it as the current user.  The
# bootstrap verifies the complete release bundle from an immutable commit and
# uses sudo only for privileged phases.  The whole script is read before main
# runs, so a truncated download executes nothing.
set -euo pipefail

repository="RamrattanN/PiHoleSpeedtestV6"
asset_name="pihole-speedtest-v6-bootstrap.sh"
latest_release_url="https://github.com/${repository}/releases/latest/download"
tagged_release_url="https://github.com/${repository}/releases/download"
# vMAJOR.MINOR.PATCH or vMAJOR.MINOR.PATCH-rc.N, without leading zeros.
release_tag_pattern='^v(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})(-rc\.[1-9][0-9]{0,3})?$'
runner_url="https://raw.githubusercontent.com/${repository}/main/install.sh"
max_bytes=1048576
work_dir=""

usage() {
  cat <<EOF
Usage: curl -fsSL $runner_url | bash -s -- [ACTION] [options]

Actions:
  install    Install or upgrade the companion and the Pi-hole sidebar pages.
             This is the default.  Accepts --pihole-origin ORIGIN,
             --companion-url URL, and --interval-minutes NUMBER.
  uninstall  Remove the sidebar pages and the companion.  Measurement history,
             settings, backups, and recovery evidence are preserved.

Set PIHOLE_SPEEDTEST_RELEASE_TAG to one release tag, such as v1.0.6-rc.1, to
run that exact release instead of the latest stable release.

Permanent data deletion is a separate verified action.  See
https://github.com/${repository}/blob/main/docs/CURL-INSTALLATION.md
EOF
}

cleanup() {
  case "$work_dir" in
    */pihole-speedtest-install.*)
      if [ -d "$work_dir" ] && [ ! -L "$work_dir" ]; then
        rm -rf -- "$work_dir"
      fi
      ;;
  esac
}

fail() {
  echo "STOP: $1" >&2
  echo "Nothing was installed or removed by this runner." >&2
  exit 1
}

download() {
  curl --fail --show-error --silent --location \
    --proto '=https' --tlsv1.2 \
    --max-filesize "$max_bytes" \
    --output "$2" \
    "$1" || fail "Download failed: $1"
  [ -s "$2" ] || fail "Downloaded file is empty: $1"
}

main() {
  action="${1:-install}"
  if [ "$#" -gt 0 ]; then
    shift
  fi
  case "$action" in
    install) bootstrap_action="install-all" ;;
    uninstall)
      bootstrap_action="uninstall-all"
      if [ "$#" -ne 0 ]; then
        echo "STOP: uninstall does not accept additional options." >&2
        exit 2
      fi
      ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown action: $action" >&2; usage >&2; exit 2 ;;
  esac

  release_tag="${PIHOLE_SPEEDTEST_RELEASE_TAG:-}"
  expected_version=""
  if [ -z "$release_tag" ]; then
    release_url="$latest_release_url"
  elif [[ "$release_tag" =~ $release_tag_pattern ]]; then
    release_url="$tagged_release_url/$release_tag"
    expected_version="${release_tag#v}"
    expected_version="${expected_version%%-rc.*}"
    echo "Using explicitly selected release $release_tag instead of the latest stable release."
  else
    fail "PIHOLE_SPEEDTEST_RELEASE_TAG must be a release tag such as v1.0.6 or v1.0.6-rc.1."
  fi

  if [ "$(id -u)" -eq 0 ]; then
    fail "Run this command as a regular user with sudo rights, not as root."
  fi
  for command in curl sha256sum mktemp bash grep head id; do
    command -v "$command" >/dev/null 2>&1 || fail "Required command is unavailable: $command"
  done

  work_dir="$(mktemp -d "${TMPDIR:-/tmp}/pihole-speedtest-install.XXXXXXXX")"
  case "$work_dir" in
    */pihole-speedtest-install.*) ;;
    *) fail "Temporary directory was not created safely." ;;
  esac
  if [ ! -d "$work_dir" ] || [ -L "$work_dir" ]; then
    fail "Temporary directory was not created safely."
  fi
  trap cleanup EXIT

  bootstrap="$work_dir/$asset_name"
  checksum="$work_dir/$asset_name.sha256"
  download "$release_url/$asset_name.sha256" "$checksum"
  download "$release_url/$asset_name" "$bootstrap"

  if [ "$(grep -c '' "$checksum")" -ne 1 ] ||
    ! grep -Eq "^[0-9a-f]{64}  ${asset_name//./\\.}\$" "$checksum"
  then
    fail "Published bootstrap checksum has unexpected content."
  fi
  expected_sha256="$(head -c 64 "$checksum")"
  printf '%s  %s\n' "$expected_sha256" "$bootstrap" |
    sha256sum --check --status - ||
    fail "Bootstrap checksum verification failed."

  if [ "$(head -n 1 "$bootstrap")" != "#!/usr/bin/env bash" ] ||
    ! grep -Fqx "repository=\"$repository\"" "$bootstrap" ||
    ! grep -Fq "install-all|uninstall-all|" "$bootstrap" ||
    grep -Eq '@(SOURCE_COMMIT|ASSET_COMMIT|BUNDLE_SHA256)@' "$bootstrap"
  then
    fail "Verified bootstrap is not a rendered Pi-hole Speedtest release bootstrap."
  fi
  if [ -n "$expected_version" ] &&
    ! grep -Fqx "version=\"$expected_version\"" "$bootstrap"
  then
    fail "Verified bootstrap does not match release $release_tag."
  fi

  echo "Verified production bootstrap: $expected_sha256"
  status=0
  bash "$bootstrap" "$bootstrap_action" "$@" </dev/null || status=$?
  if [ "$status" -ne 0 ]; then
    echo >&2
    echo "The $action action stopped with status $status.  User data was not deleted." >&2
    echo "Review the message above, then retry: curl -fsSL $runner_url | ${release_tag:+PIHOLE_SPEEDTEST_RELEASE_TAG=$release_tag }bash -s -- $action" >&2
    echo "Checksum-pinned commands: https://github.com/${repository}/blob/main/docs/CURL-INSTALLATION.md" >&2
  fi
  exit "$status"
}

main "$@"

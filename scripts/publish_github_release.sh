#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/publish_github_release.sh \
  --kind prerelease|production \
  --tag TAG \
  --expected-commit SHA \
  --bootstrap-sha256 SHA256 \
  --asset-dir PATH \
  [--accepted-prerelease TAG] \
  [--publish --confirm PHRASE]

Validates the GitHub Release assets for the runner:

  pihole-speedtest-v6-bootstrap.sh
  pihole-speedtest-v6-bootstrap.sh.sha256

Without --publish this is validation only: it performs every local check and
prints the release command without contacting GitHub, creating a tag, or
uploading anything.

The expected commit must be the checked-out, clean commit that contains the
rendered release/pihole-speedtest-v6-bootstrap.sh.  The asset directory must
contain exactly the byte-identical bootstrap and its one-line checksum.

Prerelease tags are vX.Y.Z-rc.N and require:
  --confirm 'PUBLISH PRERELEASE <tag>'
Production tags are vX.Y.Z, require --accepted-prerelease vX.Y.Z-rc.N, and
require:
  --confirm 'PUBLISH PRODUCTION <tag>'

Publishing requires an authenticated GitHub CLI (gh) with release write access.
EOF
}

repository="RamrattanN/PiHoleSpeedtestV6"
asset_name="pihole-speedtest-v6-bootstrap.sh"
committed_bootstrap="release/${asset_name}"
production_tag_pattern='^v(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})$'
prerelease_tag_pattern='^v(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})-rc\.[1-9][0-9]{0,3}$'

kind=""
tag=""
expected_commit=""
bootstrap_sha256=""
asset_dir=""
accepted_prerelease=""
publish=0
confirm=""

stop() {
  echo "STOP: $1" >&2
  exit 1
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --publish) publish=1; shift; continue ;;
    --help|-h) usage; exit 0 ;;
  esac
  if [ "$#" -lt 2 ]; then
    echo "Option requires a value: $1" >&2
    usage >&2
    exit 2
  fi
  case "$1" in
    --kind) kind="$2" ;;
    --tag) tag="$2" ;;
    --expected-commit) expected_commit="$2" ;;
    --bootstrap-sha256) bootstrap_sha256="$2" ;;
    --asset-dir) asset_dir="$2" ;;
    --accepted-prerelease) accepted_prerelease="$2" ;;
    --confirm) confirm="$2" ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift 2
done

for command in git sha256sum bash cmp grep sed; do
  command -v "$command" >/dev/null 2>&1 || stop "Required command is unavailable: $command"
done

case "$kind" in
  prerelease)
    [[ "$tag" =~ $prerelease_tag_pattern ]] ||
      stop "A prerelease tag must look like v1.0.6-rc.1."
    [ -z "$accepted_prerelease" ] ||
      stop "--accepted-prerelease applies only to production releases."
    required_confirmation="PUBLISH PRERELEASE $tag"
    ;;
  production)
    [[ "$tag" =~ $production_tag_pattern ]] ||
      stop "A production tag must look like v1.0.6."
    [[ "$accepted_prerelease" =~ $prerelease_tag_pattern ]] &&
      [ "${accepted_prerelease%%-rc.*}" = "$tag" ] ||
      stop "--accepted-prerelease must be an accepted ${tag}-rc.N prerelease."
    required_confirmation="PUBLISH PRODUCTION $tag"
    ;;
  *) stop "--kind must be prerelease or production." ;;
esac
tag_version="${tag#v}"
tag_version="${tag_version%%-rc.*}"
if [ "$publish" -eq 1 ] && [ "$confirm" != "$required_confirmation" ]; then
  stop "Publishing this $kind requires --confirm '$required_confirmation'."
fi
if [ "$publish" -eq 0 ] && [ -n "$confirm" ]; then
  stop "--confirm is only accepted together with --publish."
fi
[[ "$expected_commit" =~ ^[0-9a-f]{40}$ ]] ||
  stop "--expected-commit must be one full lowercase Git commit SHA."
[[ "$bootstrap_sha256" =~ ^[0-9a-f]{64}$ ]] ||
  stop "--bootstrap-sha256 must be one lowercase SHA-256 value."
[ -n "$asset_dir" ] || stop "--asset-dir is required."

source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$source_root"
[ "$(git rev-parse HEAD)" = "$expected_commit" ] ||
  stop "The checked-out commit is not --expected-commit."
[ -z "$(git status --porcelain)" ] ||
  stop "The repository working tree is not clean."
git cat-file -e "${expected_commit}:${committed_bootstrap}" 2>/dev/null ||
  stop "The expected commit does not contain ${committed_bootstrap}."

[ -d "$asset_dir" ] && [ ! -L "$asset_dir" ] ||
  stop "--asset-dir must be a real directory."
bootstrap="$asset_dir/$asset_name"
checksum="$asset_dir/$asset_name.sha256"
for path in "$bootstrap" "$checksum"; do
  [ -f "$path" ] && [ ! -L "$path" ] ||
    stop "Release asset must be a regular file, not a link: $path"
done
asset_entries="$(cd "$asset_dir" && find . -mindepth 1 -maxdepth 1 -print | LC_ALL=C sort)"
[ "$asset_entries" = "$(printf './%s\n./%s' "$asset_name" "$asset_name.sha256")" ] ||
  stop "The asset directory must contain only $asset_name and $asset_name.sha256."

[ "$(grep -c '' "$checksum")" -eq 1 ] &&
  grep -Eq "^[0-9a-f]{64}  ${asset_name//./\\.}\$" "$checksum" ||
  stop "The checksum file must be one SHA-256 record for $asset_name."
[ "$(sed -n '1s/  .*//p' "$checksum")" = "$bootstrap_sha256" ] ||
  stop "The checksum file does not record --bootstrap-sha256."
(cd "$asset_dir" && sha256sum --check --status "$asset_name.sha256") ||
  stop "sha256sum --check failed for $asset_name."
git show "${expected_commit}:${committed_bootstrap}" | cmp -s - "$bootstrap" ||
  stop "The bootstrap asset differs from ${committed_bootstrap} at the expected commit."
bash -n "$bootstrap" || stop "The bootstrap failed bash -n."
if grep -Eq '@(SOURCE_COMMIT|ASSET_COMMIT|BUNDLE_SHA256)@' "$bootstrap"; then
  stop "The bootstrap contains unresolved release-template placeholders."
fi

bootstrap_value() {
  sed -n "s/^$1=\"\\([^\"]*\\)\"\$/\\1/p" "$bootstrap"
}
project_version="$(git show "${expected_commit}:pyproject.toml" | sed -n 's/^version = "\([^"]*\)"$/\1/p')"
bootstrap_version="$(bootstrap_value version)"
[ "$bootstrap_version" = "$project_version" ] && [ "$bootstrap_version" = "$tag_version" ] ||
  stop "Bootstrap version ${bootstrap_version:-unknown}, project version ${project_version:-unknown}, and tag $tag do not match."
[ "$(bootstrap_value repository)" = "$repository" ] ||
  stop "The bootstrap does not name repository $repository."
source_commit="$(bootstrap_value source_commit)"
asset_commit="$(bootstrap_value asset_commit)"
bundle_sha256="$(bootstrap_value bundle_sha256)"
for commit in "$source_commit" "$asset_commit"; do
  [[ "$commit" =~ ^[0-9a-f]{40}$ ]] && git merge-base --is-ancestor "$commit" "$expected_commit" ||
    stop "Bootstrap commit $commit is not an ancestor of the expected commit."
done
bundle_path="release/pihole-speedtest-v6-${bootstrap_version}.tar.gz"
[ "$(git show "${asset_commit}:${bundle_path}" 2>/dev/null | sha256sum | sed 's/ .*//')" = "$bundle_sha256" ] ||
  stop "The bundle at the bootstrap's asset commit does not match its embedded checksum."

notes="Pi-hole Speedtest ${tag}

Release commit: ${expected_commit}
Application source commit: ${source_commit}
Bundle asset commit: ${asset_commit}
Bundle SHA-256: ${bundle_sha256}
Bootstrap SHA-256: ${bootstrap_sha256}"
if [ "$kind" = "prerelease" ]; then
  notes="${notes}

Acceptance candidate.  Not the production release.
Install for acceptance with PIHOLE_SPEEDTEST_RELEASE_TAG=${tag}."
  release_flags=(--prerelease --latest=false)
else
  notes="${notes}

Production release of accepted prerelease ${accepted_prerelease}."
  release_flags=(--latest)
fi

echo "Release assets validated for $kind $tag at $expected_commit."
echo "Bootstrap SHA-256: $bootstrap_sha256"
if [ "$publish" -eq 0 ]; then
  echo "Validation only.  Nothing was tagged, created, or uploaded."
  echo "Publication command: gh release create $tag --repo $repository --target $expected_commit ${release_flags[*]} --title 'Pi-hole Speedtest $tag' <assets>"
  exit 0
fi

command -v gh >/dev/null 2>&1 || stop "The GitHub CLI (gh) is required to publish."
work_dir="$(mktemp -d)"
trap 'rm -rf -- "$work_dir"' EXIT
remote_tag_commit() {
  gh api "repos/${repository}/git/ref/tags/$1" --jq .object.sha 2>/dev/null || true
}
[ -z "$(remote_tag_commit "$tag")" ] || stop "Tag $tag already exists on GitHub."
if [ "$kind" = "production" ]; then
  [ "$(gh release view "$accepted_prerelease" --repo "$repository" --json isPrerelease --jq .isPrerelease 2>/dev/null)" = "true" ] ||
    stop "Accepted prerelease $accepted_prerelease is not a published prerelease."
  [ "$(remote_tag_commit "$accepted_prerelease")" = "$expected_commit" ] ||
    stop "Accepted prerelease $accepted_prerelease was not published from the expected commit."
  accepted_dir="$work_dir/accepted"
  mkdir "$accepted_dir"
  gh release download "$accepted_prerelease" --repo "$repository" \
    --pattern "$asset_name" --pattern "$asset_name.sha256" --dir "$accepted_dir"
  cmp -s "$accepted_dir/$asset_name" "$bootstrap" &&
    cmp -s "$accepted_dir/$asset_name.sha256" "$checksum" ||
    stop "Production assets are not byte-identical to accepted prerelease $accepted_prerelease."
fi

notes_file="$work_dir/release-notes.md"
printf '%s\n' "$notes" > "$notes_file"
gh release create "$tag" "$bootstrap" "$checksum" \
  --repo "$repository" \
  --target "$expected_commit" \
  "${release_flags[@]}" \
  --title "Pi-hole Speedtest $tag" \
  --notes-file "$notes_file"

[ "$(remote_tag_commit "$tag")" = "$expected_commit" ] ||
  stop "Published tag $tag does not point at the expected commit.  Review the release before use."
echo "Published $kind $tag from $expected_commit with the verified runner assets."

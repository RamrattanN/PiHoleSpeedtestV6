# Checksum-verified curl workflow

## Status

Version `1.0.5` is the installed and owner-approved production baseline.
Version `1.0.3` is
withdrawn because live download verification correctly detected that its
published bundle bytes did not match its embedded checksum.  Do not use the
version `1.0.3` bootstrap.  Version `1.0.5` supports uninstalling any verified
installed version and corrects post-install cleanup.  Its curl uninstall and
reinstall acceptance passed with measurement history and settings preserved.
Reboot, interrupted-install, and explicit purge acceptance remain tracked in
issue #3.

Version `1.0.6` is in preparation and unpublished.  It adds the one-line
convenience runner, its prerelease acceptance override, guarded release
publication, and the `install-all` and `uninstall-all` bootstrap actions
described below.  Its trust anchors will be recorded here only after its
release assets are published and verified.

## Trust chain

The pinned command below never pipes a mutable branch directly into a shell.
It will:

1. download a small bootstrap from an immutable Git commit over HTTPS;
2. verify the bootstrap against the SHA-256 value printed in the repository;
3. run the verified bootstrap without elevated privileges;
4. download a versioned release bundle from a second immutable Git commit;
5. verify the complete bundle against the checksum embedded in the verified
   bootstrap;
6. validate the bundle's source-commit marker;
7. invoke `sudo` only for the selected, verified installation or removal phase.

The version `1.0.6` convenience runner is the only branch-based entry point.
It performs no privileged operation itself and executes only a bootstrap whose
published checksum matches, so the bundle verification in steps 4 to 7 is
unchanged.

## Version 1.0.6 convenience runner

Not yet available: the runner is added to `main` and its release assets are
published only as part of the approved `1.0.6` release.

```bash
curl -fsSL \
  https://raw.githubusercontent.com/RamrattanN/PiHoleSpeedtestV6/main/install.sh |
  bash
```

`install.sh` accepts one optional action.  No action and `install` run the
bootstrap's `install-all`; `uninstall` runs `uninstall-all`.  Installation
options such as `--pihole-origin`, `--companion-url`, and `--interval-minutes`
follow the action, for example `bash -s -- install --interval-minutes 60`.

The runner:

1. validates any requested release tag before doing anything else;
2. refuses to run as root and requires a user with `sudo` rights;
3. creates a private temporary directory and removes it on exit;
4. downloads `pihole-speedtest-v6-bootstrap.sh` and
   `pihole-speedtest-v6-bootstrap.sh.sha256` from the same selected GitHub
   Release over HTTPS with TLS 1.2 or newer;
5. rejects a failed download, an empty file, or a checksum file that is not
   exactly one SHA-256 line naming the bootstrap;
6. verifies the bootstrap checksum and confirms that it is a rendered
   Pi-hole Speedtest release bootstrap, whose version matches any requested
   tag;
7. runs the verified bootstrap as the current user, which then verifies the
   immutable release bundle and uses `sudo` only for privileged phases.

The runner reads its complete script before executing anything, so a truncated
download does nothing.  The bootstrap and its checksum come from the same
release, so the runner check guards against corruption and substitution in
transit; independently pinned trust anchors remain available through the
production install command below.  Each release must therefore attach both the
rendered bootstrap and its `.sha256` file as release assets.

### Release selection

Without an override, the runner uses
`https://github.com/RamrattanN/PiHoleSpeedtestV6/releases/latest/download/`.
GitHub resolves `releases/latest` only to the latest stable release, never to a
prerelease, so publishing a prerelease cannot silently replace the stable
release used by the ordinary command.

For prerelease acceptance, `PIHOLE_SPEEDTEST_RELEASE_TAG` selects one exact
release, downloaded from
`https://github.com/RamrattanN/PiHoleSpeedtestV6/releases/download/<tag>/`:

```bash
curl -fsSL \
  https://raw.githubusercontent.com/RamrattanN/PiHoleSpeedtestV6/main/install.sh |
  PIHOLE_SPEEDTEST_RELEASE_TAG=v1.0.6-rc.1 bash
```

```bash
curl -fsSL \
  https://raw.githubusercontent.com/RamrattanN/PiHoleSpeedtestV6/main/install.sh |
  PIHOLE_SPEEDTEST_RELEASE_TAG=v1.0.6-rc.1 \
  bash -s -- uninstall
```

The tag must match
`^v(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})(-rc\.[1-9][0-9]{0,3})?$`,
for example `v1.0.6` or `v1.0.6-rc.1`.  Anything else, including whitespace,
slashes, `..`, URLs, query strings, fragments, and shell syntax, stops the
runner before any download.  The repository and GitHub host are fixed.  An
empty value behaves exactly like no override.  The runner prints a notice when
a tag is selected, and it rejects a bootstrap whose version differs from the
tag's version.

## Release sequence

Version `1.0.6` and later releases follow this order.  Every step after
prerelease acceptance reuses the accepted commit and bytes.

1. Merge the approved source into the intended release branch.
2. Ensure `install.sh` is present on `main`.
3. Build and validate the immutable bundle, commit it, render the bootstrap
   with `scripts/render_release_bootstrap.sh`, and commit the rendered
   `release/pihole-speedtest-v6-bootstrap.sh`.  That bootstrap commit is the
   release commit.
4. Publish a GitHub prerelease such as `v1.0.6-rc.1` from the exact release
   commit with `scripts/publish_github_release.sh`.
5. On the Raspberry Pi, run the one-line installation, health, timer, sidebar,
   data-preservation, uninstall, and reinstall acceptance with
   `PIHOLE_SPEEDTEST_RELEASE_TAG=v1.0.6-rc.1`.
6. Preserve the acceptance evidence.
7. Make no source or asset changes after successful prerelease acceptance.
8. Publish the final `v1.0.6` release from the same accepted commit with
   byte-identical bootstrap assets.
9. Verify that the ordinary command without the override resolves the stable
   `1.0.6` release.
10. Close the curl workflow issue only after final production verification.

`releases/latest` must continue to resolve only the latest stable release.  A
prerelease must never be marked as the latest release.

## Publishing release assets

`scripts/publish_github_release.sh` creates the GitHub Release and uploads
exactly `pihole-speedtest-v6-bootstrap.sh` and
`pihole-speedtest-v6-bootstrap.sh.sha256`.  It requires `git`, `sha256sum`,
and, only for publication, an authenticated GitHub CLI (`gh`) with release
write access.  It never triggers Docker publication.

Prepare the assets outside the repository from the checked-out release commit:

```bash
release_commit="$(git rev-parse HEAD)"
asset_dir="$(mktemp -d)"
git show "$release_commit:release/pihole-speedtest-v6-bootstrap.sh" \
  > "$asset_dir/pihole-speedtest-v6-bootstrap.sh"
(cd "$asset_dir" &&
  sha256sum pihole-speedtest-v6-bootstrap.sh \
    > pihole-speedtest-v6-bootstrap.sh.sha256)
bootstrap_sha256="$(cut -c1-64 "$asset_dir/pihole-speedtest-v6-bootstrap.sh.sha256")"
```

Validate without contacting GitHub, creating a tag, or uploading anything:

```bash
scripts/publish_github_release.sh \
  --kind prerelease \
  --tag v1.0.6-rc.1 \
  --expected-commit "$release_commit" \
  --bootstrap-sha256 "$bootstrap_sha256" \
  --asset-dir "$asset_dir"
```

Validation fails closed unless the tag format matches its kind, the checked-out
commit equals `--expected-commit`, the working tree is clean, both assets are
regular files and the only files in the directory, the checksum file is one
record naming the bootstrap and matching `--bootstrap-sha256`,
`sha256sum --check` passes, the asset is byte-identical to the bootstrap
committed at the release commit, `bash -n` passes, no template placeholder
remains, the bootstrap, project, and tag versions agree, the bootstrap's source
and asset commits are ancestors of the release commit, and the committed bundle
matches the bootstrap's embedded checksum.

Publication adds `--publish` and a kind-specific confirmation:

- prerelease: `--confirm 'PUBLISH PRERELEASE v1.0.6-rc.1'`, published with
  `--prerelease --latest=false`;
- production: `--kind production --tag v1.0.6 --accepted-prerelease
  v1.0.6-rc.1 --confirm 'PUBLISH PRODUCTION v1.0.6'`, published with
  `--latest`.

Prerelease tags must end in `-rc.N` and production tags must not, so one
confirmation can never publish the other kind.  Before publishing, the tool
refuses an existing tag.  A production release additionally requires the
accepted prerelease to exist as a prerelease on the same commit with
byte-identical bootstrap and checksum assets.  After publishing, it verifies
that the new tag points at the expected commit.

## Full-product actions

Version `1.0.6` adds two bootstrap actions that compose the verified granular
phases.  Neither action deletes user data.

`install-all`:

1. installs the companion, keeps an already installed copy of the same release,
   or upgrades an older installation by a data-preserving uninstall and
   reinstall;
2. verifies dashboard health and the reported version;
3. verifies exactly one enabled and active collection timer;
4. installs the Pi-hole sidebar adapter unless it is already installed;
5. verifies Pi-hole FTL and the Pi-hole web interface;
6. verifies the adapter manifest, sidebar, and wrapper pages;
7. prints the detected dashboard, Overview, and Setup addresses.

If the sidebar phases fail, the adapter installer's own rollback restores the
Pi-hole web files; any adapter recorded by this run is also removed through its
verified manifest.  The companion, database, settings, and recovery evidence are
kept, and the output names the failed phase with the `install-adapter` retry and
`uninstall-all` recovery commands.

`uninstall-all`:

1. detects the installed companion and sidebar adapter;
2. removes the adapter through its installed manifest when present;
3. verifies that the original sidebar is restored and no adapter pages remain;
4. uninstalls the companion;
5. verifies that the database, settings, and uninstall marker are preserved;
6. verifies that Pi-hole FTL remains active;
7. confirms that the application, services, timer, and service account are
   absent.

Repeating `install-all` on a current installation, or `uninstall-all` after a
completed uninstall, reports the state and changes nothing.  An incomplete
installation stops both actions without changes.  Permanent deletion remains
the separate `purge-data` action.

## Licence files

Each release bundle is a complete archive of the tracked source at its release
commit, so it carries the product [LICENSE](../LICENSE) and
[Third-Party Notices](../THIRD_PARTY_NOTICES.md) for incorporated components.
The installer builds the Python package from that bundle; the installed
package contains only product code and records the product licence in its
package metadata.  Uninstall removes the application directory, including that
metadata, and no other licence files.  Bundles published through version
`1.0.5` predate `THIRD_PARTY_NOTICES.md` and remain immutable.

## Production trust anchors

| Item | Immutable value |
| --- | --- |
| Application source commit | `2400a3108235a477c6d9c2c3af0d2024f1cf9633` |
| GitHub CI | Run 68 passed |
| Bundle asset commit | `0c9f90a10ed418fffd761b8b719351357167b46e` |
| Bundle SHA-256 | `b5da1523ec3b458a694be3d178effa33cb5fa67e0578d43e26b7fcdfe7c323b0` |
| Bootstrap commit | `8d6a779b34341a302a8a6c84502f2d95002dc95e` |
| Bootstrap SHA-256 | `af2d2ca9c17d2420c22bb0ba894a409f00f468b0557eb95e8aacddfe9b430335` |

## Production install command

Run this on the Raspberry Pi.  It downloads and verifies the bootstrap before
the bootstrap downloads and verifies the complete bundle.  `sudo` is invoked
only after both checks pass.

```bash
bootstrap=/tmp/pihole-speedtest-v6-bootstrap.sh && \
curl --fail --show-error --silent --location \
  --proto '=https' --tlsv1.2 \
  --output "$bootstrap" \
  https://raw.githubusercontent.com/RamrattanN/PiHoleSpeedtestV6/8d6a779b34341a302a8a6c84502f2d95002dc95e/release/pihole-speedtest-v6-bootstrap.sh && \
printf '%s  %s\n' \
  'af2d2ca9c17d2420c22bb0ba894a409f00f468b0557eb95e8aacddfe9b430335' \
  "$bootstrap" | sha256sum --check --status - && \
bash "$bootstrap" install
```

The default capture interval is 15 minutes.  A supported alternative can be
selected by adding, for example, `--interval-minutes 60` after `install`.

## Sidebar install command

After the companion installation passes, use the already verified bootstrap:

```bash
bash /tmp/pihole-speedtest-v6-bootstrap.sh install-adapter
```

The adapter action verifies the companion commit recorded by the installed
manifest.  It does not assume that the companion and bootstrap were published
from the same source commit, and it does not upgrade the companion.

Automatic origin detection is suitable for a typical HTTP installation opened
by the Pi's primary address.  A hostname, HTTPS, reverse proxy, or nonstandard
origin must be supplied explicitly:

```bash
bash /tmp/pihole-speedtest-v6-bootstrap.sh install-adapter \
  --pihole-origin https://pihole.example.net \
  --companion-url https://speedtest.example.net
```

## Removal commands

If the sidebar adapter is installed, remove and verify that independent layer
first:

```bash
bash /tmp/pihole-speedtest-v6-bootstrap.sh remove-adapter
```

Then remove the companion while preserving all user data:

```bash
bash /tmp/pihole-speedtest-v6-bootstrap.sh uninstall
```

If `/tmp` has been cleared, repeat the download and bootstrap checksum steps
from the production install command, then replace the final `install` action
with the required removal action.

Permanent deletion remains a separate command and must never be combined with
default uninstall:

```bash
bash /tmp/pihole-speedtest-v6-bootstrap.sh purge-data \
  --confirm 'DELETE /var/lib/pihole-speedtest'
```

## Supported actions

The version `1.0.5` bootstrap exposes five distinct actions.  Version `1.0.6`
retains them and adds `install-all` and `uninstall-all`:

- `install` installs the unprivileged companion service and collection timer;
- `install-adapter` separately installs the Pi-hole Web v6.6 sidebar adapter;
- `remove-adapter` verifies and removes only the sidebar adapter;
- `uninstall` removes services, application files, and the service account but
  preserves all user data;
- `purge-data` is a separate destructive action requiring the exact
  confirmation `DELETE /var/lib/pihole-speedtest`.

## Dynamic device configuration

The installer does not contain a private network address.  It detects the
device's primary address at runtime for a typical HTTP Pi-hole installation.
Users with a hostname, HTTPS, reverse proxy, or nonstandard origin can provide
their own `--pihole-origin` and `--companion-url` values.

## Fail-closed checks

Installation refuses to continue unless all of the following are true:

- the release bundle checksum and source marker match;
- the architecture is `aarch64` or `x86_64`;
- Python 3.9 or newer is available;
- Pi-hole Core v6 is installed;
- the official Ookla CLI is installed at `/usr/bin/speedtest`;
- no conflicting active companion installation exists;
- preserved data comes from a verified uninstall or failed installation;
- any preserved SQLite database passes `PRAGMA integrity_check`;
- the selected collection interval is supported.

The optional adapter retains its stricter Pi-hole Web v6.6 layout and checksum
gates.

## Preservation and recovery

Default uninstall creates and verifies an online SQLite recovery copy before
removing services.  It retains `/var/lib/pihole-speedtest`, including history,
settings, backups, migration reports, manifests, and prior recovery evidence.
A later install reuses that directory and verifies the database before starting
services.  Installation and removal traps restore service files after a partial
failure without deleting user data.

The purge action is unavailable while any application, unit, environment file,
or service account remains.  It also refuses data without a verified uninstall
marker.

## Acceptance

Version `1.0.5` passed curl uninstall and reinstall acceptance with measurement
history and settings preserved, and the owner accepted the restored dashboard
and sidebar.

Still required:

- clean Raspberry Pi 3 ARM64 installation;
- interrupted-install rollback and repeat invocation;
- reboot with dashboard and timer continuity;
- explicit purge test using disposable data only;
- version `1.0.6` `install-all`, `uninstall-all`, and one-line runner
  acceptance on Raspberry Pi 3 against the `v1.0.6-rc.1` prerelease, followed
  by final verification of the stable release.

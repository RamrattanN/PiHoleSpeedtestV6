# Version 1.0.7 release notes

**Status:** prepared, unpublished.  Stable `v1.0.6` remains the published
release until `v1.0.7` passes prerelease acceptance and is published from the
same release commit with byte-identical assets.

Version 1.0.7 is a recovery and compatibility release for the Pi-hole sidebar
adapter.  The companion service, collector, storage, schedule and web UI are
unchanged from 1.0.6 apart from the reported version.  A healthy 1.0.6
installation does not need a companion reinstall to receive these fixes.

## Changes

- **Stale adapter state reconciliation (PR #24).**  A deployment record can say
  the sidebar adapter is installed after Pi-hole itself restored its web files,
  for example during a Pi-hole update.  The guarded installer now reconciles that
  state only when the original sidebar, absent pages and archived recovery
  evidence are all independently verified, then reinstalls the pages.
- **Interrupted-installation recovery (PR #24).**  A pending journal blocks every
  entry point after an interruption.  `recover` either restores the
  pre-reconciliation records (`restored`) or finalizes a fully verified new
  installation (`finalized`), and refuses everything else.  Every historical
  evidence file is checksummed and must remain unchanged.
- **Pi-hole Web v6.6.1 support (PR #25).**  The adapter supports exactly Web
  `v6.6` and `v6.6.1`, whose sidebar and included templates are byte-identical.
  The approved sidebar SHA-256 is unchanged:
  `83943cbdf5258fe43e819108a5135e070d6742e273753ba398a8d28e1a008fdb`.
  Historical recovery evidence recorded under v6.6 remains valid and is never
  rewritten.
- **Adapter-only repair with an older companion (PR #25).**  Pages are generated
  from the checksum-verified release bundle, so `install-adapter` works on a
  1.0.6 companion running Pi-hole Web v6.6.1.  Removal and rollback still use the
  installed companion's checksum-only removal.

See [adapter recovery](ADAPTER-RECOVERY.md) and the
[Pi-hole Web adapter](PIHOLE-V6-ADAPTER.md) for the exact checks.

## Compatibility

| Item | Supported |
|---|---|
| Pi-hole Core | v6 |
| Pi-hole Web, sidebar adapter | exactly `v6.6` or `v6.6.1` with the approved sidebar checksum |
| Installed companion for `install-adapter` | 1.0.6 or 1.0.7 |
| Python on the Pi | 3.11 or newer, for the adapter's `tomllib` checks |
| Origins | HTTP, or native Pi-hole HTTPS with the companion on HTTPS port 8765 |

## Repairing an existing 1.0.6 installation

Use the adapter-only action.  **Do not use `install-all`, `install.sh`, or the
ordinary one-line runner for this repair.**  The 1.0.7 source commit differs
from the installed commit, so those paths run the data-preserving companion
upgrade.  That stops and restarts the dashboard and collection timer and
recreates the environment file, none of which this repair needs.
`install-adapter` does not reinstall, restart or reconfigure the companion, and
it does not touch its database, settings or TLS files.

The reviewed values come from the release-preparation pull request's validated
Stage C summary and must match the published release record:

- `RELEASE_COMMIT`: the release commit that holds the rendered bootstrap;
- `BOOTSTRAP_SHA256`: the SHA-256 of `pihole-speedtest-v6-bootstrap.sh`.

### 1. Read-only preflight

Confirm the following before the repair:

- Web `v6.6` or `v6.6.1`;
- the approved sidebar checksum;
- root-owned evidence and manifests with no group or other write permission;
- both pages absent and no pending marker;
- the historical `companion_url` equal to the installed one;
- live headers equal to an archived policy;
- the companion is healthy and exactly one timer is enabled.

The read-only checks are in
[adapter recovery](ADAPTER-RECOVERY.md#predeployment-verification-separate-approval).
Then record a data baseline, read-only:

```bash
sudo python3 -I -c 'import sqlite3; c = sqlite3.connect("file:/var/lib/pihole-speedtest/speedtest.db?mode=ro", uri=True); print("integrity:", c.execute("PRAGMA integrity_check").fetchone()[0]); print("measurements:", c.execute("SELECT COUNT(*) FROM measurements").fetchone()[0])'
sudo sha256sum /var/lib/pihole-speedtest/settings.json
sudo grep -E '^(source_commit|pihole_origin|companion_url|pihole_adapter_[a-z_]+)=' /var/lib/pihole-speedtest/install-manifest.txt
```

### 2. Verified adapter-only repair

Replace both placeholders with the reviewed values.  The bootstrap is
downloaded from its immutable release commit and checked before anything runs.
The bootstrap then verifies the bundle, and `sudo` is used only after both
checks pass.

```bash
release_commit='RELEASE_COMMIT'
bootstrap_sha256='BOOTSTRAP_SHA256'
bootstrap="$(mktemp -d)/pihole-speedtest-v6-bootstrap.sh" && \
curl --fail --show-error --silent --location \
  --proto '=https' --tlsv1.2 \
  --output "$bootstrap" \
  "https://raw.githubusercontent.com/RamrattanN/PiHoleSpeedtestV6/${release_commit}/release/pihole-speedtest-v6-bootstrap.sh" && \
printf '%s  %s\n' "$bootstrap_sha256" "$bootstrap" | sha256sum --check --status - && \
grep -Fqx 'version="1.0.7"' "$bootstrap" && \
echo "Verified bootstrap: $bootstrap" && \
bash "$bootstrap" install-adapter
```

Without options, `install-adapter` reuses the `pihole_origin` and
`companion_url` recorded in the deployment manifest.  Keep the printed
`$bootstrap` path for removal or recovery.

### 3. Expected result

A successful run ends with `=== LIVE PI-HOLE SIDEBAR ADAPTER INSTALLED ===`.
Then confirm, read-only:

- no `/var/lib/pihole-speedtest-adapter-recovery/reconciliation.pending.json`;
- both deployment manifests record `pihole_adapter_installed=true` and the same
  new `pihole_adapter_manifest`, and that manifest records `web_version` v6.6.1;
- `pihole_adapter_reconciliation` names a `reconciliation-TIMESTAMP` directory
  containing `completed.json`;
- `source_commit` still names the installed 1.0.6 companion, and the dashboard
  health reports version `1.0.6`, because the companion was not reinstalled;
- the historical `20260926T031216666609Z` evidence checksums equal the preflight
  values;
- Overview and Setup render inside Pi-hole over HTTPS, the companion still
  sends `frame-ancestors 'self' https://pi.hole`, and Pi-hole sends
  `frame-src https://pi.hole:8765`;
- FTL is active, DNS resolves, blocking is enabled, and exactly one collection
  timer is enabled and active;
- database integrity is `ok`, and the measurement count is at least its baseline
  (scheduled collection may add rows).  The settings checksum is unchanged.

## If the repair stops or fails

- **Stopped before any change:** a `STOP:` line printed before reconciliation
  means nothing was modified.  Correct the reported condition, or seek review if
  the state is unexpected.  Never edit `sidebar.lp` or the manifests to get past
  a check.
- **Failed after starting:** the installer rolls back its own changes and runs
  verified recovery.  `Pre-reconciliation deployment records restored` means the
  original stale record is back exactly; resolve the cause and rerun step 2.
- **Interrupted (power loss or kill):** every entry point refuses until
  verified recovery runs.  Recover with the helper from the same verified
  release.  This downloads the bundle named by the verified bootstrap, checks
  its SHA-256, and runs `recover`:

  ```bash
  asset_commit="$(sed -n 's/^asset_commit="\([0-9a-f]\{40\}\)"$/\1/p' "$bootstrap")"
  bundle_sha256="$(sed -n 's/^bundle_sha256="\([0-9a-f]\{64\}\)"$/\1/p' "$bootstrap")"
  work="$(mktemp -d)" && \
  curl --fail --show-error --silent --location \
    --proto '=https' --tlsv1.2 \
    --output "$work/bundle.tar.gz" \
    "https://raw.githubusercontent.com/RamrattanN/PiHoleSpeedtestV6/${asset_commit}/release/pihole-speedtest-v6-1.0.7.tar.gz" && \
  printf '%s  %s\n' "$bundle_sha256" "$work/bundle.tar.gz" | sha256sum --check --status - && \
  tar -xzf "$work/bundle.tar.gz" -C "$work" && \
  sudo python3 -I "$work/pihole-speedtest-v6-1.0.7/scripts/reconcile_pihole_adapter.py" recover
  ```

  `restored` means rerun step 2.  `finalized` means the new installation was
  verified complete; continue with step 3.  Any refusal leaves every file as
  found and needs manual review.  Do not delete the pending journal.
- **Undo a successful repair:** `bash "$bootstrap" remove-adapter` verifies the
  installed checksums and header policy, then restores the original sidebar and
  header policy.  Measurements and recovery evidence are kept.

## Known limitations

- Only Pi-hole Web `v6.6` and `v6.6.1` are accepted.  A later Web release is
  refused until it is reviewed and added.
- A future Pi-hole update or repair that resets the web checkout can remove the
  pages again.  Rerun the verified `install-adapter` repair if that happens.
- After an adapter-only repair the companion keeps reporting `1.0.6`.  A later
  full upgrade with `install-all` is optional and changes only that reported
  version.
- Recovery after an interruption needs the verified release bundle, as shown
  above.  The bootstrap removes its own temporary copy when it exits.

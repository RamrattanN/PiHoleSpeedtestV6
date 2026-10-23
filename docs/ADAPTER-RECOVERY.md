# Restored sidebar with stale installation metadata

A retry can stop at `install-all 6/7: Verify the sidebar adapter` with
`STOP: Installed sidebar does not match the adapter manifest.` The deployment
record may say the adapter is installed even though the original sidebar has
been restored and both wrapper pages are absent. This does not justify deleting
or replacing the companion database.

The reconciliation fix is source-only until a new checksum-pinned release is
approved. Older published bootstraps do not acquire this behavior automatically.
Do not manually delete manifests, edit `sidebar.lp`, or download and execute a
repair script independently of the verified release bundle.

## Likely cause (unconfirmed)

The exact operation that restored the sidebar is not recorded. A Pi-hole
update or repair (`pihole -up`, `pihole -r`) resets the `/var/www/html/admin`
Git checkout and stashes or cleans untracked files, which matches a byte-exact
original sidebar, both pages missing and unchanged FTL header configuration.
These read-only checks can help confirm it before any repair:

```bash
sudo git -C /var/www/html/admin stash list
sudo stat -c '%y %n' /var/www/html/admin/scripts/lua/sidebar.lp
ls -la /var/log/pihole/
```

Do not apply or drop a stash; the guarded installer recreates the pages. If
this is the cause, later Pi-hole updates can produce the same state again. The
reconciliation remains available only while Pi-hole Web is still v6.6 with the
approved sidebar baseline; a newer Web release is refused by the version gate.

## Automatic repair boundary

`install-all` first verifies a recorded adapter. If verification fails, it calls
the guarded adapter installer. `install-adapter` also supports this restored
state, without upgrading the companion. All these conditions must pass:

- Both root-owned deployment manifests reference the same timestamped recovery
  manifest under `/var/lib/pihole-speedtest-adapter-recovery`.
- Recovery files are regular files with trusted ownership and no group/other
  write permission; paths cannot traverse symlinks or escape the expected tree.
- The recovery schema, Web version, exact paths, checksums, sidebar backup,
  deployment snapshots and both header-policy snapshots are consistent.
- The sidebar exactly matches the approved Web v6.6 original checksum, contains
  no adapter markers, and neither page exists (including dangling symlinks).
- Live Web is v6.6; the companion is healthy, dashboard and timer are active and
  enabled, exactly one collection timer is enabled, and FTL, Pi-hole status and
  the web interface pass their checks.
- The historical companion URL matches the repair URL, the companion permits
  embedding by the Pi-hole origin, and live Pi-hole headers match either the
  archived original or installed policy.

Unknown sidebar bytes, one surviving page, unexpected page contents, missing
or inconsistent evidence, modified headers, unsafe paths or a pending operation
stop the repair before reconciliation. They require manual review, never force.
Healthy `install-all` retries leave adapter files and recovery records unchanged.

The installer creates a private `reconciliation-TIMESTAMP` directory containing
both deployment snapshots, their SHA-256 values, the historical manifest path
and hash, and the verified restored-state evidence. It then writes a pending
journal before marking the adapter absent in the two deployment records. The
existing adapter installer creates a new timestamped backup and manifest,
installs and verifies the pages, records the new manifest in both deployment
records, and writes `completed.json` before clearing pending intent. Historical
recovery directories are retained. The new removal record restores the original
historical sidebar and header policy; a failed attempt restores the header policy
present immediately before that attempt.

## Preferred incident repair

After approval and publication, download a bootstrap from its immutable release
commit and verify its independently recorded SHA-256 as described in
[CURL-INSTALLATION.md](CURL-INSTALLATION.md). Use the **new verified bootstrap**:

```bash
bash /path/to/verified-bootstrap.sh install-adapter \
  --pihole-origin http://pihole.example.test \
  --companion-url http://pihole.example.test:8765
```

Use the actual historical origins. This action leaves the companion application,
SQLite database, settings, environment and TLS files untouched. It configures
Pi-hole web headers through the existing FTL config command; allow for web/FTL
configuration reload effects and verify DNS and web service after approval on
the real device. It does not explicitly restart companion services or timers.

## Interrupted or failed repair

A pending `/var/lib/pihole-speedtest-adapter-recovery/reconciliation.pending.json`
blocks installer, removal and uninstall entry points. Do not delete it to retry.

On an ordinary failure the installer's error trap restores the header policy
present before the attempt, removes any adapter files it verified as its own,
and then runs the same checksum-verified `recover` step described below while
still holding the deployment lock. The output names the outcome. The
reconciliation and failed-attempt directories are kept as evidence. Resolve the
reported cause and rerun the same verified command.

If that automatic step refuses, or SIGKILL or power loss prevented the trap,
the pending journal remains and every entry point stays blocked. Preserve the
pending journal, its `reconciliation-TIMESTAMP` directory and all newer
timestamped adapter recovery directories, then run the helper from the
**extracted, SHA-256-verified new release bundle**:

```bash
sudo python3 -I /path/to/verified-bundle/scripts/reconcile_pihole_adapter.py recover
```

The helper takes the deployment lock and first proves the journal itself: its
location and permissions, both pre-reconciliation snapshot checksums, the
historical manifest checksum and the checksum of every file in the historical
recovery directory. It refuses if any deployment value other than the adapter
keys changed. It then accepts exactly one of two live states:

- **Restored** (`Pre-reconciliation deployment records restored`): the sidebar
  is the approved original, both pages are absent and the records still name
  the historical manifest. Both records return byte-for-byte to their snapshots
  and `recovered.json` is written. Rerun the verified `install-adapter` action
  after resolving the original failure.
- **Finalized** (`Verified adapter installation finalized`): power was lost
  after the new adapter was installed. Both records must name the same new
  manifest created after this journal. That manifest must pass the same path,
  ownership, layout and recomputed-checksum checks as the historical one. The
  live sidebar and both pages must match its installed checksums. Its archived
  header policy must match the historical original, and its pre-installation
  snapshots must equal the prepared state recorded in the journal. An existing
  `completed.json` is accepted only if it names that same manifest; it is never
  proof on its own. `completed.json` is written if missing, `finalized.json`
  records the recovery, and no web file, header or deployment record changes.

Either outcome then removes the pending marker and syncs its directory. Running
`recover` again after a second interruption repeats the same checks and is
safe; once nothing is pending it reports `nothing to recover` and changes
nothing.

Any other state is refused with every file left as found. Examples are a
modified sidebar or page, partial files from an interrupted write, records that
disagree, an untrusted or inconsistent manifest or snapshot, or changed
historical evidence. That needs manual review. Identify which recovery manifest,
if any, every live file matches, and compare live headers with the archived
`pihole-web-headers.*.json` values. Do not delete or edit the pending journal,
deployment records, manifests or web files to get past the refusal, and do not
run companion uninstall or purge to resolve it.

Successful repair is reversed with the verified bootstrap's `remove-adapter`.
That verifies new installed checksums and headers before restoring the original
sidebar/header policy. Measurement data and historical recovery evidence remain.

## Predeployment verification (separate approval)

These checks are prerequisites for deploying the fix. Make them read-only, and
do not combine them with the repair itself:

- **Ownership and permissions.** Reconciliation refuses unless every path it
  reads is root-owned, has no group or other write permission and contains no
  symlink. Confirm this for the Pi-hole web directories, the sidebar, the
  adapter recovery evidence and both active deployment manifests:

  ```bash
  sudo stat -c '%U:%G %a %F %n' /var/www/html/admin /var/www/html/admin/scripts \
    /var/www/html/admin/scripts/lua /var/www/html/admin/scripts/lua/sidebar.lp \
    /var/lib/pihole-speedtest/install-manifest.txt \
    /var/lib/pihole-speedtest/collection-manifest.txt \
    /var/lib/pihole-speedtest-adapter-recovery \
    /var/lib/pihole-speedtest-adapter-recovery/20260926T031216666609Z \
    /var/lib/pihole-speedtest-adapter-recovery/20260926T031216666609Z/*
  ```

- **Sidebar baseline.** `pihole -v` must report Web `v6.6`, and
  `sha256sum /var/www/html/admin/scripts/lua/sidebar.lp` must equal the approved
  `83943cbdf5258fe43e819108a5135e070d6742e273753ba398a8d28e1a008fdb`.
- **HTTPS origin and frame policy.** Record the installed `pihole_origin` and
  `companion_url`. For an HTTPS origin, confirm that the existing loopback
  requests return the admin page and the current `Content-Security-Policy`, for
  example `curl -kfsS --resolve pi.hole:443:127.0.0.1 -D - -o /dev/null
  https://pi.hole/admin/`. The isolated tests cover this path; the real
  certificate and FTL behaviour still need confirming on the device.
- **Release preparation.** A new version and checksum-verified release assets
  are prepared separately. This fix does not change the version number.

## Upgrade distinction and release procedure

A new release has a new source commit. `install-all` compares commits, not just
version numbers, so it may remove/reinstall the companion. It now repairs a
fully restored recorded adapter **before** attempting upgrade removal. Unsafe
states stop before companion removal. It then follows the existing upgrade path.

That path makes an online SQLite backup using `sqlite3.Connection.backup`, checks
both live and backup databases with `PRAGMA integrity_check`, archives deployment
and environment files in uninstall recovery, stops the collection service and
timer and dashboard, removes/reinstalls the application, and restarts the
dashboard/timer. Reinstall retains history/settings and checks database integrity.
The environment file is recreated; arbitrary custom environment/TLS service
configuration is **not automatically restored**. Review and preserve it before
any full upgrade. The adapter-only action is preferable for this incident.

Build deterministic assets from the reviewed source commit twice, compare their
bytes, validate the source marker and bundle checksum, and render a new bootstrap
with immutable source/asset commits. Publish/rehearse only after separate
approval, first in an isolated Pi-hole copy with fault injection, then on the Pi
with explicit deployment approval, DNS/FTL checks and retained evidence. Never
replace already published bundle bytes or bypass bootstrap verification.

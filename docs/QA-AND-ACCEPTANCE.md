# QA and acceptance

No development build may modify the live Pi-hole until all preceding gates pass.

## Gate 1: source and automated QA

- repository is clean and based on the reviewed commit;
- Python compilation passes;
- unit tests pass;
- shell syntax checks pass for retained shell files;
- browser assets contain no external network references;
- malformed CLI output and failed processes record no result;
- SQLite schema creation and queries are repeatable;
- unsupported collection intervals are rejected;
- configuration writes are available without a separate application key on
  the trusted LAN;
- manual HTTP collection runs asynchronously and shares the scheduled
  collector lock;
- reset verifies a SQLite recovery copy before deleting active history;
- CSV export preserves chronological order and measurement units;
- chart zoom and pan affect only the time axis;
- line and bar modes preserve the same fixed vertical scale;
- bar mode layers unequal paired values without adding them and separates
  equal or nearly equal values so both series remain visible.

### Owner dashboard acceptance

The owner visually accepted the branded dashboard and Setup experience on
September 22, 2026, using the imported 98,627-measurement validation database.
The owner approved the latest live interface on September 23, 2026 after
verifying embedded branding, manual testing, permanently expanded Setup
sections, chart mouseover values, true timestamp gaps, and adaptive layered
bars in version `0.1.0.dev4`.  GitHub CI run 35 and all 61 automated tests
passed for the accepted revision.
The accepted interface is documented in
[`APPROVED-DASHBOARD-BASELINE.md`](APPROVED-DASHBOARD-BASELINE.md).  Later UI
changes must preserve its required behaviors or receive explicit owner
approval for a revised baseline.

Version `1.0.1` corrects the rejected zero-point rendering from version
`1.0.0`.  QA must prove that routine intervals do not create zero-valued
sawtooth lines, substantial outages remain visible as blank time spans, and
SQLite history, health counts, the measurement table, and CSV exports remain
unchanged before owner visual acceptance and live upgrade.

Version `1.0.5` proved that the default view covers the latest
24 hours on a responsive hourly grid, every real measurement uses uniform bar
geometry, mixed five-minute and fifteen-minute history retains consistent
visual delimiters, outage spans remain blank, and the Setup version label
matches `/api/health`.  The guarded live upgrade completed with 98,719
measurements, SQLite integrity `ok`, one active 15-minute timer, and the
sidebar adapter preserved.  The remaining release work exercises the current
curl bootstrap through removal and reinstall while preserving those controls.
The verified bootstrap must also discover the installed source commit from the
root-owned manifest and use that exact commit for data-preserving uninstall,
without requiring the installed and bootstrap versions to match.

## Gate 2: read-only Pi preflight

Capture without modifying the Raspberry Pi:

- Pi-hole Core, Web, and FTL versions;
- operating system, architecture, and Raspberry Pi model;
- free storage and memory;
- current services, web listener, timers, and cron entries;
- installed speed-test CLIs and versions;
- existing speedtest files, databases, web changes, and backups;
- current Pi-hole health and DNS resolution.

Gate 2 was completed on September 22, 2026.  The verified findings, recovery
checksum, and approved legacy-schedule pause are recorded in
[`VERIFIED-PI-BASELINE.md`](VERIFIED-PI-BASELINE.md).

## Gate 3: isolated companion QA

- copy the archived legacy CSV away from the live data directory;
- import it into a temporary SQLite database;
- reconcile imported, duplicate, and rejected row counts;
- reconcile and review every preserved timestamp collision;
- inspect every reported rejection and preserve the report;
- rerun the import and verify that no duplicate rows are added;
- deploy only to a temporary directory;
- use a temporary SQLite database;
- execute one manual official Ookla test;
- validate stored units and values against the CLI result;
- run the dashboard on a temporary non-Pi-hole port;
- verify health and history APIs;
- inspect browser network activity for local-only requests;
- stop and remove the temporary service;
- confirm Pi-hole health and DNS are unchanged.

## Gate 4: controlled service deployment

- create and verify a recovery point;
- install the companion without the Pi-hole adapter;
- use an unprivileged service account;
- enable the service before enabling the timer;
- verify restart and reboot behavior;
- enable a conservative schedule;
- verify that overlapping runs cannot occur;
- confirm history survives an application upgrade.

The dashboard-only portion of Gate 4 passed on September 22, 2026 local time.
The exact approved commit installed under an unprivileged service account,
started automatically through systemd, and served all 98,627 migrated
measurements on port 8765.  Independent verification confirmed zero service
restarts, correct security headers, SQLite integrity, and stable Pi-hole
health.

The collection timer, keyless dashboard controls, and guarded companion
upgrade subsequently passed live verification.  Commit
`897e7d2a8e699f65e762ab6a8908f002443f2abb` was deployed with 98,632
measurements preserved, the timer active and enabled, and recovery evidence at
`/var/lib/pihole-speedtest-upgrade-recovery/20260923T034009Z`.  The sidebar
adapter was still absent at that checkpoint.  Reboot and full restore exercises
remain open.

The interface-label follow-up was deployed from commit
`e06d6c7964acc5bdfb6000488dd7eea79d5ed615`.  All 54 Raspberry Pi tests passed,
the guarded upgrade preserved 98,634 measurements, and manual measurement
`98635` recorded `eth0`.  Dashboard and timer services remained active and
enabled, while Pi-hole DNS and blocking remained healthy.  Recovery evidence is
stored at
`/var/lib/pihole-speedtest-upgrade-recovery/20260923T040754Z`.

## Gate 5: optional Pi-hole adapter

- require a recognized Pi-hole version and file layout;
- record checksums and back up exact target files;
- install the adapter idempotently;
- add native Pi-hole `Speedtest` navigation with `Overview` and `Setup`;
- display the companion views inside authenticated Pi-hole pages;
- permit framing only from the explicitly configured Pi-hole origin;
- verify all existing Pi-hole pages and controls;
- remove the adapter and prove exact restoration;
- simulate an unknown Pi-hole layout and confirm refusal.

The disposable installed-tree rehearsal passed on September 22, 2026 local
time.  Installation, checksum validation, exact removal, live-sidebar
non-modification, FTL health, and blocking status all passed.  The subsequent
guarded live installation, CSP correction, LCARS navigation repair, embedded
Overview and Setup verification, and owner visual acceptance also passed.
Version `0.1.0.dev4` is the accepted live adapter baseline.  Pi-hole DNS, FTL,
blocking, dashboard health, companion collection, and recovery controls
remained operational.

## Gate 6: release acceptance

- Pi-hole DNS and admin health remain unaffected;
- the dashboard uses no CDN or remote browser dependency;
- failed tests do not create zero-value measurements;
- measurement units are correct;
- timestamps are UTC in storage and clearly rendered for the user;
- data survives restart, reboot, upgrade, and uninstall by default;
- backup and restore are exercised, not merely documented;
- Raspberry Pi 3 CPU, memory, disk, and temperature remain acceptable;
- installation and rollback instructions match the accepted build.

### Curl workflow acceptance

- the bootstrap and bundle are fetched from immutable commit URLs;
- the bootstrap is verified before it runs and the bundle is verified before
  any privileged command;
- unsupported architecture, Python, Pi-hole, Ookla CLI, layout, and preserved
  data states fail before installation mutation;
- partial installation and removal restore service state without deleting user
  data;
- default uninstall preserves history, settings, backups, manifests, logs, and
  recovery evidence;
- reinstall verifies and reuses the preserved database;
- the separately invoked purge refuses an active installation and requires the
  exact destructive confirmation;
- clean install, adapter install and removal, uninstall, reinstall, reboot, and
  disposable-data purge pass on Raspberry Pi 3 ARM64.

### Version 1.0.6 one-line workflow acceptance

Automated tests exercise the runner, the rendered bootstrap, and the release
publication validation against stubbed system commands and throwaway
repositories.  Before version `1.0.6` replaces version `1.0.5`, the following
must pass on Raspberry Pi 3 ARM64 against the published `v1.0.6-rc.8`
prerelease, using `PIHOLE_SPEEDTEST_RELEASE_TAG=v1.0.6-rc.8` with the exact
one-line runner from `main`.  Prerelease `v1.0.6-rc.1` was published and
accepted on the Raspberry Pi for upgrade, data preservation, services, sidebar,
and charts.  It exposed a collection scheduling defect, a 15-minute setting
recording about every 30 minutes, so it is superseded for acceptance and
remains published as immutable historical evidence.

The current candidate must show:

- the runner reports the selected tag and downloads the bootstrap and checksum
  from that prerelease only;
- the one-line runner verifies the release bootstrap checksum, refuses root,
  and runs `install-all` by default and `uninstall-all` for `uninstall`;
- `install-all` upgrades the installed version `1.0.5` by a data-preserving
  reinstall with measurement history and settings unchanged;
- dashboard health, exactly one enabled collection timer, Pi-hole FTL and web
  health, and the sidebar adapter manifest and pages are verified;
- the printed dashboard, Overview, and Setup addresses open correctly;
- when Pi-hole serves HTTPS, the runner detects its configured domain and
  certificate, the companion serves HTTPS on port 8765, and the Overview and
  Setup iframes load without mixed content;
- on an HTTPS-enabled Pi-hole, HTTP IP or alternate-origin Overview and Setup
  requests redirect to the configured canonical HTTPS origin before the iframe
  loads;
- on an HTTP-only Pi-hole, Overview and Setup remain on the configured HTTP
  origin without an HTTPS redirect;
- the HTTPS dashboard service receives `/etc/pihole/tls.pem` through its
  restricted systemd credential, while the companion account has no direct
  read access to the source certificate;
- a repeated `install-all` changes nothing;
- `uninstall-all` removes the sidebar before the companion, restores the
  original sidebar exactly, and preserves history, settings, and recovery
  evidence;
- a repeated `uninstall-all` changes nothing, and a following `install-all`
  reuses the preserved data;
- a sidebar failure leaves the companion, data, and Pi-hole web files intact
  and the outer runner prints a valid checksum-verified retry command without a
  transient bootstrap path;
- HTTPS adapter evidence is captured through the TLS health endpoint, and a
  standalone adapter retry reuses the installed HTTPS origins.

Release candidate `v1.0.6-rc.8` must additionally show at least three
consecutive scheduled collections about 15 minutes apart with no alternating
`"not due"` skips in the collector journal, complete one documented uninstall
and reinstall and one repeat installation, and keep genuine outages as empty
chart gaps rather than zero values.  As a visual check only, confirm at a
normal browser viewport that the Download and upload chart's time labels do
not overlap the Latency and jitter heading.  Zoom to approximately ten
measurements while a high ping outside the view would otherwise dominate the
scale: the Latency and jitter y-axis must fit only the visible measurements
with headroom.  The bars must widen as spacing grows, stay distinct when
close, and the companion text and canvas axis labels must use Pi-hole's
Antonio LCARS font in Chrome split view.  The font check must cover both the
Overview and Setup pages before and after a browser refresh.  Bars must retain
genuine time gaps.  Record owner visual acceptance separately from automated
test results.

For new scheduled measurements, confirm that the chart position is the exact
configured UTC schedule slot, such as `:00`, `:15`, `:30`, or `:45` for the
default interval.  Confirm that the API, CSV export, table, and chart tooltip
retain the actual start and completion timestamps.  For a manual measurement,
confirm that the chart uses its actual start time.  Existing measurements must
remain intact and continue to use their historical completion time because a
reliable earlier start time cannot be reconstructed.

Open Pi-hole through its HTTPS hostname and verify both sidebar pages.  Confirm
that the installed manifest records matching HTTPS `pihole_origin` and
`companion_url` values, that `https://<pihole-host>:8765/api/health` responds,
and that the browser reports no refused iframe, mixed-content, or certificate
error.  Repeat installation must preserve this configuration.  A deliberately
mixed HTTP/HTTPS pair or a certificate that does not cover the companion
hostname must fail before installation mutation.

Preserve the runner output, dashboard health responses, timer listings, adapter
manifests, and recovery evidence as acceptance evidence.  After acceptance,
change no source or asset.  The stable `v1.0.6` release must then be published
from the same commit with byte-identical bootstrap assets, and the ordinary
command without the override must be verified to resolve it before the curl
workflow issue is closed.

### Version 1.0.6-rc.7 acceptance result

The owner completed Raspberry Pi 3 ARM64 acceptance on September 25, 2026.
The public one-line runner verified bootstrap SHA-256
`fe0bd79aa80389654b2038dd55a45d7bd1bc0d984c8c1ef0db92b3f9ff9c3a6e`
and installed source commit `e95b176268a2b805ea94269aab5756e2f91030c2`.
HTTP entry redirected to the canonical HTTPS Pi-hole origin, while direct
HTTPS Overview and Setup pages loaded the TLS companion successfully.

Five consecutive scheduled collections, followed by three post-reinstall
collections and one post-reboot collection, used exact quarter-hour
`scheduled_at` values while retaining distinct actual `started_at` and
completion `recorded_at` values.  Repeat installation changed nothing.
Uninstall and repeat-uninstall restored the original Pi-hole web state and
preserved 98,803 measurements and the settings checksum.  Reinstall reused the
preserved data, and the final post-reboot count reached 98,807 with SQLite
integrity `ok`.

The destructive-confirmation guard refused an incorrect purge phrase in an
isolated private mount namespace.  The exact confirmation then deleted only
the disposable data.  The live data-directory inode and settings checksum were
unchanged, the live measurement count did not decrease, and dashboard and
timer services remained active.  Release candidate 7 passed this complete
functional sequence, but a later Chrome split-view comparison exposed
companion typography that did not match the Pi-hole LCARS theme.  It is
superseded for final acceptance and remains published as historical evidence.
Release candidate 8 must preserve every rc.7 result and pass the Antonio font
check.  Stable `v1.0.6` remains held.

## Stop conditions

Stop immediately if Pi-hole DNS health changes, the admin interface becomes
unavailable, an installer encounters an unknown file layout, a backup cannot be
verified, measurement parsing is ambiguous, or rollback cannot restore the
pre-test state.

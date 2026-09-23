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
- configuration and reset writes require an administrator token;
- manual HTTP collection requires an administrator token, runs asynchronously,
  and shares the scheduled collector lock;
- reset verifies a SQLite recovery copy before deleting active history;
- CSV export preserves chronological order and measurement units;
- chart zoom and pan affect only the time axis;
- line and bar modes preserve the same fixed vertical scale.

### Owner dashboard acceptance

The owner visually accepted the branded dashboard and Setup experience on
September 22, 2026, using the imported 98,627-measurement validation database.
The accepted interface is documented in
[`APPROVED-DASHBOARD-BASELINE.md`](APPROVED-DASHBOARD-BASELINE.md).  Later UI
changes must preserve its required behaviors or receive explicit owner
approval for a revised baseline.

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
restarts, correct security headers, SQLite integrity, stable Pi-hole health,
and the absence of both the collection timer and live sidebar adapter.  Timer,
reboot, collection, upgrade, and history-survival checks remain open.

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
non-modification, FTL health, and blocking status all passed.  Live adapter
installation remains separately approval-gated.

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

## Stop conditions

Stop immediately if Pi-hole DNS health changes, the admin interface becomes
unavailable, an installer encounters an unknown file layout, a backup cannot be
verified, measurement parsing is ambiguous, or rollback cannot restore the
pre-test state.

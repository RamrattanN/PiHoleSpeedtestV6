# Deployment status

The dashboard companion service, 15-minute automated collection, and optional
Pi-hole navigation adapter passed live verification on the Raspberry Pi.
Version `1.0.0` is the production release line.

The former installer copied files into Pi-hole web directories and added a cron
entry before the runner and web page had reliable automated tests.  That path is
retained only as historical source.  Guarded companion installation, upgrade,
and data-preserving removal workflows now exist.  Full backup and restore
acceptance remains open.

Do not run `./mod`, `scripts/mod.sh`, or `scripts/install_dashboard.sh` on a
live Pi-hole from this development branch.

## Development-only execution

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
pihole-speedtest serve --database ./data/speedtest.db --host 127.0.0.1 --port 8765
```

## Implemented service shape

- application: `/opt/pihole-speedtest`
- data: `/var/lib/pihole-speedtest/speedtest.db`
- configuration: `/var/lib/pihole-speedtest/settings.json`
- service environment: `/etc/default/pihole-speedtest-v6`
- reset recovery backups: `/var/lib/pihole-speedtest/backups`
- service account: dedicated unprivileged account
- dashboard: independent HTTP service on a configurable LAN address and port
- schedule: systemd timer
- integration: optional and reversible Pi-hole v6 adapter

Systemd units are maintained under `deploy/systemd/` for:

- an always-on dashboard at LAN port `8765`;
- a one-shot official Ookla collection service;
- a persistent scheduler that checks every 15 minutes;
- a user-selected capture frequency from 15 minutes through once a day, with a
  60-minute default;
- an unprivileged `pihole-speedtest` service account;
- process locking that refuses overlapping collections.

The dashboard and collection timer run without an interactive Terminal
session.  Production source commit
`494f45f23f8c14f8ccd6eff40c1e71a9c277be71` passed GitHub CI run 46.  General
backup, restore, and final reboot acceptance remain tracked release work.

The authoritative deployment gates are in
[`docs/QA-AND-ACCEPTANCE.md`](docs/QA-AND-ACCEPTANCE.md).

The optional Pi-hole navigation integration is documented separately in
[`docs/PIHOLE-V6-ADAPTER.md`](docs/PIHOLE-V6-ADAPTER.md).  It must not be
installed before the companion service and isolated adapter validation pass.

## Dashboard-only staged installation

`scripts/install_companion_dashboard.sh` installs only the unprivileged
companion dashboard.  It imports and reconciles the accepted legacy history,
verifies SQLite integrity and the expected measurement counts, enables the
dashboard service, and verifies its health.

The script deliberately does not install the collection service or timer and
does not modify the Pi-hole web tree.  A failed installation removes the new
service and application, preserves failure evidence, and leaves Pi-hole files
unchanged.  Use is approval-gated and requires all expected migration counts as
explicit arguments.  It also requires the exact approved Git commit and refuses
a source tree with tracked changes.

`scripts/remove_companion_dashboard.sh` is the matching recovery command for
this phase.  It refuses to run if a collection timer is present, stops the
dashboard, preserves the complete data directory and deployment evidence under
`/var/lib/pihole-speedtest-removal-recovery/`, and leaves the Pi-hole web tree
unchanged.

The staged installation from commit
`62fbcc88fc09b9f4d209a8fcec753a895665f7e0` passed on September 22, 2026 local
time.  The service started as `pihole-speedtest`, the health endpoint reported
98,627 measurements, SQLite integrity was `ok`, and all accepted migration
counts matched.  The collection timer remained absent, the root crontab
remained empty, and the Pi-hole sidebar checksum remained unchanged.

## Guarded collection upgrade

`scripts/upgrade_and_enable_collection.sh` upgrades the staged application from
an explicitly named installed commit to an explicitly named approved source
commit.  It creates and verifies a SQLite recovery backup, retains the complete
prior application, updates the dashboard for manual speed tests,
and installs the schedule-aware collection service and timer.

Before enabling the timer, the script invokes the manual collection
API and requires one valid measurement, a one-row count increase, and a clean
SQLite integrity check.  Failure restores the prior application, dashboard
unit, and settings while deliberately preserving any valid measurement that
completed before a later check failed.  The Pi-hole web tree is outside this
workflow.

## Keyless dashboard upgrade

`scripts/upgrade_remove_administrator_key.sh` upgrades an existing scheduled
installation to the owner-approved keyless dashboard.  It pauses the timer,
waits for any active collection to finish, verifies a SQLite recovery backup,
retains the prior application and deployment files, removes the obsolete token,
and proves the keyless manual-test API with one measurement before restoring
the timer.  It does not modify the Pi-hole web tree or install the adapter.

## Guarded companion upgrade

`scripts/upgrade_companion.sh` is the current guarded updater for an installed
keyless companion.  It requires the exact installed and source commits, pauses
the timer, waits for any active collection, creates and verifies an online
SQLite recovery copy, retains the prior application and deployment files,
installs the approved wheel, verifies dashboard health and required interface
markers, and restores the timer.  Failure invokes rollback.  It does not modify
the Pi-hole web tree.

The accepted live installation has been upgraded through version
`0.1.0.dev4`, commit `4bd209c0d41c70dd7235ace2b2640be27450c052`, with
measurement history, the active collection schedule, and the installed Pi-hole
adapter state preserved.  Each guarded upgrade retains timestamped recovery
evidence under `/var/lib/pihole-speedtest-upgrade-recovery/`.

## Checksum-verified curl installation and removal

Version `1.0.0` contains the release installer, data-preserving uninstaller,
separate purge command, deterministic bundle builder, and immutable-bootstrap
renderer.  The bootstrap verifies the complete bundle before invoking `sudo`;
it never pipes a mutable branch into a privileged shell.

Immutable production command syntax and the complete trust, preservation,
rollback, and acceptance contract are maintained in
[Checksum-verified curl workflow](docs/CURL-INSTALLATION.md).  Remaining
Raspberry Pi acceptance is tracked in
[issue #3](https://github.com/RamrattanN/PiHoleSpeedtestV6/issues/3).

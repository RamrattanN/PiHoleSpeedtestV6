# Roadmap

## Foundation

- [x] Recover the original product contract.
- [x] Select the hybrid companion architecture.
- [x] Define QA, acceptance, and stop conditions.
- [x] Add official Ookla parsing, SQLite history, API, and local dashboard.
- [x] Add automated tests and pull-request CI.
- [x] Add repeatable legacy CSV migration with rejected-row reporting.
- [x] Complete owner visual review of the dashboard foundation.
- [x] Establish the approved dashboard as the go-to interface baseline.

## Raspberry Pi development baseline

- [x] Complete read-only preflight on `192.168.2.14`.
- [x] Archive the active legacy installation and pause its five-minute cron job.
- [x] Validate the copied legacy CSV import into a temporary SQLite database.
- [x] Add systemd service and timer units.
- [x] Add concurrency locking.
- [ ] Add structured journal messages.
- [x] Add collection-frequency configuration for the trusted LAN dashboard.
- [ ] Add conservative retention.
- [ ] Build a safe installer, upgrader, uninstaller, backup, and restore flow.
- [x] Add a rollback-guarded dashboard-only staged installer.
- [x] Add a data-preserving dashboard-only removal command.
- [x] Pass the guarded dashboard-only staged installation on Raspberry Pi 3.
- [ ] Pass isolated Raspberry Pi 3 testing on a temporary port and database.

## Product capability

- [x] Add keyless manual test execution directly from Overview.
- [x] Add complete-history CSV export.
- [ ] Add date-range filtering.
- [ ] Add server selection with explicit validation.
- [ ] Add status, logs, storage, and next-run information.
- [ ] Add chart ranges for 24 hours, 7 days, 30 days, 90 days, and all history.
- [ ] Add an optional preferred-server selector while retaining automatic
  selection as the default.
- [x] Add a verified recovery backup before protected reset.
- [ ] Add general backup and restore controls.
- [ ] Add a user-triggered verified backup and safe backup download.
- [x] Add line and bar charts with fixed-scale time-axis zoom and pan.
- [x] Add optional recent-results table visibility.
- [ ] Add table sorting and complete accessible-state verification.

## Optional Pi-hole integration

- [x] Audit the official Pi-hole Web v6.6 interface and supported paths.
- [x] Design and implement a version-gated, reversible adapter.
- [x] Add the Speedtest Overview and Setup sidebar hierarchy.
- [ ] Add dashboard status and companion link.
- [x] Validate the adapter against a disposable copy of the installed Pi-hole
  v6.6 web tree.
- [x] Prove exact adapter rollback against the installed-tree copy.
- [ ] Prove Pi-hole update failure isolation on the live service boundary.

## Release

- [ ] Pass the complete acceptance plan on Raspberry Pi 3.
- [ ] Reconcile documentation with the accepted implementation.
- [ ] Tag the first supported v6 release.

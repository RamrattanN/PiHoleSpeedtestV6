# Roadmap

## Foundation

- [x] Define the Pi-hole v6 product contract.
- [x] Select the hybrid companion architecture.
- [x] Define QA, acceptance, and stop conditions.
- [x] Add official Ookla parsing, SQLite history, API, and local dashboard.
- [x] Add automated tests and pull-request CI.
- [x] Add repeatable legacy CSV migration with rejected-row reporting.
- [x] Complete owner visual review of the dashboard foundation.
- [x] Establish the approved dashboard as the go-to interface baseline.
- [x] Approve chart mouseover details, aligned navigation actions, and
  permanently expanded Setup sections on the live Raspberry Pi.

## Raspberry Pi development baseline

- [x] Complete read-only preflight on the owner's Raspberry Pi.
- [x] Archive the active legacy installation and pause its five-minute cron job.
- [x] Validate the copied legacy CSV import into a temporary SQLite database.
- [x] Add systemd service and timer units.
- [x] Add concurrency locking.
- [ ] Add structured journal messages.
- [x] Add collection-frequency configuration for the trusted LAN dashboard.
- [ ] Add conservative retention.
- [x] Build guarded staged installation and companion upgrade flows.
- [x] Build the data-preserving release uninstaller and separate explicit purge
  flow.
- [x] Complete checksum-verified curl install and uninstall entry points with
  GitHub-hosted instructions ([issue #3](https://github.com/RamrattanN/PiHoleSpeedtestV6/issues/3)).
- [x] Add deterministic release-bundle and immutable-bootstrap build tooling.
- [x] Publish immutable release assets and record both SHA-256 trust anchors.
- [ ] Pass uninstall and reinstall acceptance with history and settings
  preserved.
- [x] Add a rollback-guarded dashboard-only staged installer.
- [x] Add a data-preserving dashboard-only removal command.
- [x] Pass the guarded dashboard-only staged installation on Raspberry Pi 3.
- [x] Enable and verify the 15-minute systemd collection timer on Raspberry Pi
  3.
- [x] Pass a guarded live companion upgrade with history preserved.
- [x] Restore and verify Linux interface labels when Ookla omits the interface
  name.
- [ ] Pass restart and reboot acceptance with collection continuity.
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
- [x] Add mouseover measurement details to both charts.
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
- [x] Install and verify the adapter against the live Pi-hole Web v6.6 tree
  under the recovery-backed approval gate.
- [x] Complete owner acceptance of embedded branding, manual test controls,
  true timestamp gaps, and adaptive layered bars in version `0.1.0.dev4`.
- [x] Complete owner acceptance of production maintenance version `1.0.1`,
  which leaves substantial collection outages blank without inserting
  synthetic rows into measurement history.
- [x] Complete owner review of version `1.0.2` bar delimiters and the
  runtime-derived Setup version label.
- [ ] Complete owner acceptance of version `1.0.4`, which retains a consistent
  two-pixel gap between neighboring bar groups across mixed collection
  cadences and allows the current verified bootstrap to uninstall any supported
  installed version.
- [ ] Prove Pi-hole update failure isolation on the live service boundary.

## Release

- [ ] Pass the complete acceptance plan on Raspberry Pi 3.
- [x] Reconcile repository documentation and Wiki navigation with the accepted
  live implementation.
- [ ] Tag the first supported v6 release.

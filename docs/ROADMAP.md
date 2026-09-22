# Roadmap

## Foundation

- [x] Recover the original product contract.
- [x] Select the hybrid companion architecture.
- [x] Define QA, acceptance, and stop conditions.
- [x] Add official Ookla parsing, SQLite history, API, and local dashboard.
- [x] Add automated tests and pull-request CI.
- [x] Add repeatable legacy CSV migration with rejected-row reporting.
- [ ] Complete owner review of the foundation branch.

## Raspberry Pi development baseline

- [x] Complete read-only preflight on `192.168.2.14`.
- [x] Archive the active legacy installation and pause its five-minute cron job.
- [ ] Validate the copied legacy CSV import into a temporary SQLite database.
- [ ] Add systemd service and timer units.
- [ ] Add concurrency locking and structured journal messages.
- [ ] Add configuration and conservative retention.
- [ ] Build a safe installer, upgrader, uninstaller, backup, and restore flow.
- [ ] Pass isolated Raspberry Pi 3 testing on a temporary port and database.

## Product capability

- [ ] Add authenticated manual test execution.
- [ ] Add CSV export and date-range filtering.
- [ ] Add server selection with explicit validation.
- [ ] Add status, logs, storage, and next-run information.
- [ ] Add backup and restore controls.
- [ ] Add responsive charts, table sorting, and accessible states.

## Optional Pi-hole integration

- [ ] Audit the exact installed Pi-hole v6 interface and supported paths.
- [ ] Design a version-gated, reversible adapter.
- [ ] Add dashboard status and companion link.
- [ ] Prove update failure isolation and exact rollback.

## Release

- [ ] Pass the complete acceptance plan on Raspberry Pi 3.
- [ ] Reconcile documentation with the accepted implementation.
- [ ] Tag the first supported v6 release.

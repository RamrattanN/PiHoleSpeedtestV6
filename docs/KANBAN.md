# Delivery Kanban

This page summarizes the current delivery state.  GitHub issues hold the
detailed acceptance criteria for active engineering work.

## Done

- Recover the original project contract and select the independent companion
  architecture.
- Archive and pause the legacy five-minute cron collector.
- Reconcile and import 98,627 valid legacy measurements.
- Deploy the unprivileged companion dashboard on Raspberry Pi 3.
- Enable and verify the 15-minute systemd collection timer.
- Remove the administrator-key requirement by owner decision.
- Add manual testing, CSV export, fixed-scale chart zoom and pan, line and bar
  modes, chart mouseover details, and protected reset with verified backup.
- Establish and approve the Ramrattan Network Tools visual baseline.
- Validate Pi-hole Web v6.6 adapter installation and exact removal against a
  disposable copy of the installed web tree.
- Complete a guarded live companion upgrade with 98,632 measurements preserved.
- Add a tested Linux default-route fallback when the Ookla JSON omits its
  interface name.

## Ready next

| Work item | Tracking | Entry condition |
| --- | --- | --- |
| Deploy and verify interface-label fallback | Current feature branch | Guarded companion upgrade, then confirm a new Pi measurement records `eth0` |
| Live Pi-hole sidebar integration | [Issue #2](https://github.com/RamrattanN/PiHoleSpeedtestV6/issues/2) | Fresh version, checksum, health, and recovery preflight plus explicit owner approval |
| Supported curl install and uninstall | [Issue #3](https://github.com/RamrattanN/PiHoleSpeedtestV6/issues/3) | Agree release artifact, checksum, rollback, preservation, and purge contracts |

## Backlog

- Restart and reboot acceptance with collection continuity.
- Full backup and restore exercise.
- Pi-hole update failure-isolation exercise after sidebar integration.
- Structured journal messages and conservative retention.
- Dashboard service status, next-run, last-failure, storage, and log views.
- Chart date ranges, optional preferred server selection, table sorting, and
  complete accessible-state verification.
- First supported v6 release tag after all release gates pass.

## Approval-gated

- No live Pi-hole Web modification before the issue #2 preflight and explicit
  owner approval.
- No curl command may be documented as supported until immutable-source and
  checksum verification, rollback, uninstall preservation, and Raspberry Pi 3
  acceptance pass.
- No purge of measurement history, settings, backups, or recovery evidence
  without a separate explicit owner action.

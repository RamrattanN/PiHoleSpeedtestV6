# Delivery Kanban

This page summarizes the current delivery state.  GitHub issues hold the
detailed acceptance criteria for active engineering work.

## Done

- Select and document the independent companion architecture.
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
- Deploy and verify the Linux default-route fallback when the Ookla JSON omits
  its interface name.  Live measurement `98635` recorded `eth0`.
- Install, repair, and verify the live Pi-hole Web v6.6 sidebar integration,
  including exact CSP recovery and independently reversible adapter state.
- Rebaseline version `0.1.0.dev4` as the owner-approved live baseline with
  embedded branding, manual testing, true timestamp gaps, and adaptive layered
  bars.
- Promote version `1.0.0`, pass GitHub CI run 46, and publish an immutable
  production bundle plus checksum-pinned bootstrap.
- Upgrade the live Raspberry Pi companion to version `1.0.0` with 98,713
  measurements, SQLite integrity, services, timer, adapter, and Pi-hole health
  verified.
- Publish version `1.0.1` source, pass GitHub CI run 50, and publish its
  deterministic bundle plus checksum-pinned bootstrap.

## In progress

| Work item | Tracking | Entry condition |
| --- | --- | --- |
| Supported curl install and uninstall | [Issue #3](https://github.com/RamrattanN/PiHoleSpeedtestV6/issues/3) | Complete rollback, reboot, and disposable-data purge acceptance on Raspberry Pi 3 |
| Production chart-gap correction | Version `1.0.1` | Remove synthetic zero points, preserve blank outage spans, pass CI, and complete owner visual acceptance |

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

- No future Pi-hole Web modification without version, checksum, health,
  recovery, and exact-removal verification plus explicit owner approval.
- No future curl release may be documented without immutable-source and
  checksum verification, rollback, uninstall preservation, and Raspberry Pi 3
  acceptance evidence.
- No purge of measurement history, settings, backups, or recovery evidence
  without a separate explicit owner action.

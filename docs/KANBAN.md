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
- Correct mixed-cadence bar widths so every timestamp column retains a subtle
  delimiter, and publish the installed runtime version discreetly in Setup.
- Publish the immutable version `1.0.2` source, deterministic bundle, bundle
  checksum, and checksum-pinned bootstrap after GitHub CI run 54 passed.
- Complete owner review of version `1.0.2` and identify inconsistent visible
  gaps between mixed-cadence bar groups.
- Publish the immutable version `1.0.3` source after GitHub CI run 58 passed.
- Reject the version `1.0.3` release asset after live checksum verification
  correctly failed closed before privileged installation.
- Correct release packaging so generated bundles never contain prior release
  bundles or generated bootstraps, and verify the downloaded immutable bytes
  before documenting a release.
- Complete the version `1.0.2` data-preserving curl uninstall acceptance test
  with 98,716 measurements and the 15-minute setting preserved exactly.
- Identify and correct the bootstrap limitation that tied uninstall to the
  bootstrap release instead of the verified installed release.
- Publish version `1.0.4` source after GitHub CI run 63 passed, then publish
  and independently download-verify its deterministic bundle and
  checksum-pinned bootstrap.
- Install version `1.0.4` with 98,716 measurements preserved, verify the
  adapter, services, timer, SQLite integrity, and continued collection at
  measurement 98,717.
- Reject version `1.0.4` visual acceptance because its mixed-cadence bar chart
  does not match the Pi-hole dashboard presentation.
- Identify the post-install cleanup false failure caused by privileged package
  build artifacts in the bootstrap workspace.
- Publish version `1.0.5` source after GitHub CI run 68 passed, then build the
  release bundle twice and independently download-verify the immutable bundle
  and checksum-pinned bootstrap.
- Upgrade the live Raspberry Pi to version `1.0.5` with 98,719 measurements,
  SQLite integrity `ok`, one active 15-minute timer, and the installed sidebar
  adapter preserved.
- Complete owner visual acceptance and rebaseline version `1.0.5` as the
  production baseline.

## In progress

| Work item | Tracking | Entry condition |
| --- | --- | --- |
| Supported curl install and uninstall | [Issue #3](https://github.com/RamrattanN/PiHoleSpeedtestV6/issues/3) | Complete rollback, reboot, and disposable-data purge acceptance on Raspberry Pi 3 |

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

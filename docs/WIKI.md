# Project Wiki

This folder is the version-controlled documentation source for design,
deployment, testing, and delivery status.  The separate GitHub Wiki must be
published from these maintained pages so the repository's Wiki tab remains a
useful entry point rather than an independent source of truth.

## Start here

- [README](../README.md) - product purpose, current capability, and developer
  quick start.
- [Kanban](KANBAN.md) - current delivery state and next work.
- [Roadmap](ROADMAP.md) - capability and release backlog.
- [Deployment](../DEPLOY.md) - supported and approval-gated deployment paths.
- [Checksum-verified curl workflow](CURL-INSTALLATION.md) - immutable download,
  verification, preservation, rollback, and purge contract, plus the published
  version `1.0.6` one-line runner, prerelease acceptance, release sequence,
  guarded release publication, and full-product actions.
- [Removal and recovery](CURL-INSTALLATION.md#preservation-and-recovery) -
  data-preserving uninstall, preserved history and settings, recovery evidence,
  and the separate purge action.
- [Troubleshooting](CURL-INSTALLATION.md#fail-closed-checks) - the checks that
  stop installation and the recovery commands each failure prints.
- [Backup status](../DEPLOY.md) - reset recovery backups exist; general backup
  and restore controls remain open roadmap work.
- [License](../LICENSE) - MIT licence for Ramrattan Pi-hole Speedtest.
- [Third-Party Notices](../THIRD_PARTY_NOTICES.md) - licences applicable to
  incorporated components only.

## Design

- [Architecture](ARCHITECTURE.md) - companion, storage, scheduler, adapter, and
  failure boundaries.
- [Approved Dashboard Baseline](APPROVED-DASHBOARD-BASELINE.md) - required
  branding and interaction behavior.

## Raspberry Pi delivery

- [Verified Raspberry Pi Baseline](VERIFIED-PI-BASELINE.md) - platform,
  migration, deployment, upgrade, and recovery evidence.
- [QA and Acceptance](QA-AND-ACCEPTANCE.md) - gates, verification, and stop
  conditions.
- [Pi-hole v6 Adapter](PIHOLE-V6-ADAPTER.md) - optional sidebar integration and
  exact rollback contract.

## Release and tracked work

- [Stable v1.0.6 release](https://github.com/RamrattanN/PiHoleSpeedtestV6/releases/tag/v1.0.6)
- [Issue #3: Supported curl install and uninstall workflow](https://github.com/RamrattanN/PiHoleSpeedtestV6/issues/3) - acceptance complete.

## Current approved baseline

Historical: version `0.1.0.dev4` was the first owner-approved live Raspberry Pi
and Pi-hole Web v6.6 integration baseline, where the companion service,
collection timer, embedded dashboard, and independently reversible sidebar
adapter first completed live acceptance.

Version `1.0.5` was the preceding owner-approved production baseline.  It
uses a 24-hour default window, responsive hourly grid, uniform bar geometry,
blank outage spans, and a corrected post-install cleanup path.  Its source
passed GitHub CI run 68, and its immutable bundle and bootstrap were
independently downloaded and checksum-verified.  Live acceptance preserved
98,719 measurements, SQLite integrity, one active 15-minute timer, and the
installed sidebar adapter.
Its curl uninstall and reinstall acceptance preserved measurement history and
settings, and the owner accepted the restored dashboard and sidebar.

Production `v1.0.6` is published and accepted on the Raspberry Pi.  Prerelease
`v1.0.6-rc.1` was published and accepted on the Raspberry Pi for upgrade, data
preservation, services, sidebar, and charts.  It exposed a collection
scheduling defect, a 15-minute setting recording about every 30 minutes, so it
is superseded for acceptance and remains published as immutable historical
evidence.  `v1.0.6-rc.2` passed live runner, scheduling, data-preservation,
and reboot checks, but its fixed y-axis and narrow zoomed bars did not pass
owner visual acceptance.  `v1.0.6-rc.3` corrected those chart defects and
passed visual and runner acceptance, but its completion-time chart chronology
is superseded for acceptance.  `v1.0.6-rc.4` corrected chart chronology and
retained completion timestamps, but its HTTP-only companion could not be
embedded from a Pi-hole page opened over HTTPS.  It is superseded for
acceptance and remains published as historical evidence.  `v1.0.6-rc.5`
served the companion over HTTPS when Pi-hole used its native TLS certificate,
but its final adapter evidence capture sent plain HTTP to the TLS listener and
rolled the adapter back safely.  It is superseded for acceptance and remains
published as historical evidence.  `v1.0.6-rc.6` corrected adapter recovery and
passed native HTTPS embedding, but HTTP Pi-hole access displayed a rejected
iframe instead of upgrading to the canonical HTTPS page.  It is superseded for
acceptance and remains published as historical evidence.  `v1.0.6-rc.7` added
the adaptive HTTP-only behavior and canonical HTTPS redirect while retaining
the one-line `install-all` and `uninstall-all` actions.  It passed complete
Raspberry Pi acceptance,
including owner visual, install, repeat-install,
scheduled collection, timestamp, uninstall,
repeat-uninstall, reinstall, reboot, and isolated disposable-data purge
acceptance on the Raspberry Pi 3, but Chrome split view exposed companion
typography that did not match the Pi-hole LCARS theme.  It is superseded for
acceptance and remains published as historical evidence.  `v1.0.6-rc.8`
applied Pi-hole's Antonio font stack but its companion headings differed in
case and color from Pi-hole's dashboard.  rc.8 is superseded for acceptance
and remains published as historical evidence.  `v1.0.6-rc.9` corrected those
headings and passed the owner's Overview and Setup review, tagged install,
repeat install, uninstall, reinstall, and continued scheduled collection.
Stable `v1.0.6` shares rc.9's release commit
`673119bff0b4751fd3afa4fa9af922a09a27cc3d` and byte-identical assets.
The ordinary stable curl runner verified bootstrap SHA-256
`cf7db2d9c028ed5ea8a8df21e5f268afd0f72d22f6ff31d6735615902fcbc120`
and passed all seven installation checks on the Raspberry Pi.

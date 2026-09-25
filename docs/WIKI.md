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
  verification, preservation, rollback, and purge contract, plus the unpublished
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

## Active tracked work

- [Issue #3: Engineer supported curl install and uninstall workflow](https://github.com/RamrattanN/PiHoleSpeedtestV6/issues/3)

## Current approved baseline

Historical: version `0.1.0.dev4` was the first owner-approved live Raspberry Pi
and Pi-hole Web v6.6 integration baseline, where the companion service,
collection timer, embedded dashboard, and independently reversible sidebar
adapter first completed live acceptance.

Version `1.0.5` is the installed and owner-approved production baseline.  It
uses a 24-hour default window, responsive hourly grid, uniform bar geometry,
blank outage spans, and a corrected post-install cleanup path.  Its source
passed GitHub CI run 68, and its immutable bundle and bootstrap were
independently downloaded and checksum-verified.  Live acceptance preserved
98,719 measurements, SQLite integrity, one active 15-minute timer, and the
installed sidebar adapter.
Its curl uninstall and reinstall acceptance preserved measurement history and
settings, and the owner accepted the restored dashboard and sidebar.

Production `v1.0.6` is held and has not been published.  Prerelease
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
acceptance and remains published as historical evidence.  `v1.0.6-rc.5` is
the current acceptance candidate after publication.  It serves the companion
over HTTPS when Pi-hole uses its native TLS certificate and retains the
one-line `install-all` and `uninstall-all` actions.  Raspberry Pi acceptance of
rc.5 and the stable release remain open.

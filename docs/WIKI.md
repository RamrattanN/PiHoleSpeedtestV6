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
  verification, preservation, rollback, and purge contract.

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

Version `0.1.0.dev4` is the owner-approved live Raspberry Pi and Pi-hole Web
v6.6 integration baseline.  The companion service, collection timer, embedded
dashboard, and independently reversible sidebar adapter have completed live
acceptance.

Version `1.0.4` is the installed production maintenance line.  It removes synthetic zero
points, leaves substantial collection outages blank, and breaks line charts
across those outages while preserving the underlying measurement history
exactly.  It also preserves a consistent two-pixel gap between neighboring bar
groups across mixed collection cadences and shows the installed runtime version
discreetly in Setup.  Live owner acceptance of this maintenance revision remains
pending.  Its verified bootstrap can uninstall any supported installed version
by validating the source commit recorded in the installed manifest.

Version `1.0.5` is the active release-blocking visual-alignment candidate.  It
uses a 24-hour default window, responsive hourly grid, uniform bar geometry,
blank outage spans, and a corrected post-install cleanup path.  Its source
passed GitHub CI run 68, and its immutable bundle and bootstrap were
independently downloaded and checksum-verified.  Live owner acceptance remains
required before it replaces version `1.0.4`.

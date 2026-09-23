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

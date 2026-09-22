# Architecture

## Decision

Pi-hole Speedtest v6 will be an independent companion service with an optional,
reversible Pi-hole dashboard adapter.

The companion core must not replace Pi-hole Core, replace the Pi-hole web
repository, or depend on undocumented Pi-hole files for collection and history.

## Components

### Collector

- invokes the official Ookla CLI with JSON output;
- validates the process result and required fields;
- converts bandwidth from bytes per second to megabits per second;
- stores only successful measurements;
- prevents overlapping runs in the production service.

### Storage

- uses SQLite as the source of record;
- creates its schema idempotently;
- supports bounded history queries and later retention controls;
- lives outside both the application directory and Pi-hole directories.

### Companion API and dashboard

- uses a small standard-library HTTP service;
- exposes read-only health and result endpoints in the foundation;
- serves local HTML, CSS, and JavaScript;
- makes no CDN or third-party browser requests;
- remains available independently of Pi-hole's admin interface.

### Scheduler and service

The production implementation will use systemd service and timer units.  Cron
is not the target because systemd provides explicit state, logs, concurrency
control, missed-run behavior, and cleaner uninstall semantics.

### Optional Pi-hole adapter

The adapter may add a navigation entry or status card when a tested Pi-hole v6
version is recognized.  It is not part of the companion core and must have:

- explicit compatibility detection;
- an exact backup of every changed Pi-hole file;
- idempotent install and removal;
- automatic refusal on an unknown layout;
- restoration verification;
- no ownership of speed-test data or scheduling.

## Failure boundaries

- A failed speed test records no misleading zero result.
- A dashboard failure does not stop scheduled collection.
- A Pi-hole adapter failure does not stop the companion core.
- A Pi-hole update may disable the adapter, but must not delete history.
- Upgrade and uninstall preserve the database unless the owner explicitly
  requests data deletion.

## Initial network boundary

The foundation server is read-only.  Manual test execution over HTTP is deferred
until authentication and cross-site-request protections are designed.  Local
CLI collection remains available for development and systemd execution.

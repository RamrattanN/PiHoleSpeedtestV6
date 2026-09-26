# Experimental Docker Compose companion

This is an **untested Docker deployment** for evaluation on a Docker host.
The production v1.0.6 installer, Raspberry Pi systemd setup, and published
release do not use these files.  No container image has been published for
this setup.  Use a disposable Docker host and separate data for the first
acceptance run.  Do not mount the live `/var/lib/pihole-speedtest` directory.

The Compose stack runs the dashboard and one collector as separate containers
sharing a named volume.  It does not install a sidebar adapter or alter Pi-hole
files.  Both native and containerized Pi-hole can run independently alongside
it; use the dashboard URL directly.  Browser access from a different machine
requires binding to a trusted LAN address.  The initial setup binds only to
loopback and serves HTTP.  Put the dashboard behind your existing HTTPS proxy
if remote HTTPS access is required.

## Prerequisites

- Docker Engine with the Compose plugin on an AMD64 or ARM64 Linux host.
- The **official Ookla Speedtest CLI**, installed on that same host at a
  readable, executable absolute path.  It must match the container's CPU
  architecture and be runnable in a Debian-based container.  The CLI is not
  bundled or downloaded at image build time.  Review its license and terms.
- Port 8765 available.  Stop any native companion on that port before trying
  the Docker dashboard.  Leave the native service and its data untouched when
  testing on another Docker host.

From the repository root:

```bash
export SPEEDTEST_BINARY="$(command -v speedtest)"
test -n "$SPEEDTEST_BINARY" && test -x "$SPEEDTEST_BINARY"
docker compose -f docker/compose.yaml config --quiet
docker compose -f docker/compose.yaml up --build -d
docker compose -f docker/compose.yaml ps
curl -fsS http://127.0.0.1:8765/api/health
docker compose -f docker/compose.yaml exec pihole-speedtest-collector \
  /usr/local/bin/speedtest --version
```

The first scheduled collection starts at the next UTC quarter-hour boundary
(`:00`, `:15`, `:30`, `:45`).  The collector wakes at each boundary and calls
`collect --respect-schedule`.  The interval configured in Setup (15 minutes
through 24 hours) decides whether that slot needs a measurement.  A failed
collection is logged and retried at the next quarter-hour.  The manual
"Run speed test now" button and scheduler share a file lock.  There must be
only one collector for each data volume; do not scale it or run the native
systemd collector against the same database.

```bash
docker compose -f docker/compose.yaml logs --tail=100 pihole-speedtest-collector
docker compose -f docker/compose.yaml exec pihole-speedtest \
  pihole-speedtest collect --database /data/speedtest.db \
  --binary /usr/local/bin/speedtest --respect-schedule
docker compose -f docker/compose.yaml down
```

`down` leaves the named volume in place, including SQLite history and
`settings.json`.  **Do not use `down -v`** if you want to preserve that data.
After restarting the stack, confirm `/api/health` shows the previous count
and that a later scheduled measurement increases it.  SQLite integrity can
be checked with the Python `sqlite3` module inside the container.

For a trusted LAN, set `PIHOLE_SPEEDTEST_BIND_IP` to the Docker host's LAN
address before running Compose.  Restrict access to that trusted network;
the dashboard's setup and manual collection controls are not authenticated.
The separate Pi-hole sidebar integration, certificates, and reverse-proxy
configuration require their own design and acceptance work.  A Pi-hole
container's file system is never modified by this stack.

## Acceptance needed before calling Docker supported

On both AMD64 and ARM64: build the image, check the dashboard and official
binary, run a manual measurement, wait for scheduled measurements, change
the interval in Setup, restart both services, check settings and measurement
continuity and SQLite integrity, and verify the Pi-hole DNS service and web
UI remain healthy.  Test a clean install and a repeated `up --build` against
the same Docker volume.  Record any binary loader or permission failures.
The Compose definition and Python tests can be checked without Docker, but
neither establishes runtime or network compatibility.

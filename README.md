# Pi-hole Speedtest v6

Pi-hole Speedtest v6 is a resilient speed-test companion for Pi-hole v6.  It
keeps collection, history, and the full dashboard independent from Pi-hole so a
Pi-hole upgrade cannot erase data or disable scheduled tests.

## Current status

Version `1.0.4` is the production maintenance line.  Its dashboard and Pi-hole
sidebar integration are the visual, interaction, and deployment baseline for
subsequent Pi-hole Speedtest work.  It provides:

- an official Ookla CLI collector;
- validated result parsing;
- SQLite history;
- a repeatable importer for valid legacy CSV history;
- a local API and Ramrattan Network Tools dashboard;
- local web assets with no CDN dependency;
- line and adaptive layered-bar charts with fixed-scale time-axis zoom and pan;
- true timestamp spacing with substantial collection outages rendered as
  blank chart intervals without altering stored measurements;
- chart mouseover details for measurement time and values;
- optional table visibility and complete-history CSV export;
- dashboard controls for manual speed tests, collection-frequency changes,
  and reset;
- a verified SQLite recovery backup before every reset;
- unprivileged systemd service and schedule assets;
- a version-gated, recovery-backed Pi-hole Web v6.6 sidebar adapter;
- automated unit tests and pull-request CI.

The approved companion service, 15-minute collection timer, and reversible
Pi-hole Web v6.6 sidebar adapter are running on the verified Raspberry Pi 3
baseline.  Version `1.0.4` removes synthetic zero points, breaks line charts
across substantial collection outages, preserves a consistent two-pixel gap
between neighboring bar groups across mixed collection cadences, and shows the
installed version discreetly at the bottom of Setup.  Its checksum-verified
uninstaller discovers and validates the installed source commit, allowing the
current bootstrap to remove any supported installed version.
Guarded installation and upgrade paths exist.  Immutable download
commands and checksums are documented in
[Checksum-verified curl workflow](docs/CURL-INSTALLATION.md).  Remaining
Raspberry Pi acceptance is tracked in
[issue #3](https://github.com/RamrattanN/PiHoleSpeedtestV6/issues/3).

## Architecture

The product has two deliberately separate layers:

1. **Companion core:** collection, SQLite history, API, dashboard, service,
   scheduling, upgrades, and recovery.
2. **Optional Pi-hole adapter:** a small status card or navigation link.  If a
   Pi-hole update breaks the adapter, the companion core continues to work.

See [Architecture](docs/ARCHITECTURE.md),
[Approved Dashboard Baseline](docs/APPROVED-DASHBOARD-BASELINE.md),
[Pi-hole v6 Adapter](docs/PIHOLE-V6-ADAPTER.md),
[Checksum-verified curl workflow](docs/CURL-INSTALLATION.md),
[QA and Acceptance](docs/QA-AND-ACCEPTANCE.md), and
[Roadmap](docs/ROADMAP.md).  The repository documentation index is
[Wiki](docs/WIKI.md), and active work is summarized in
[Kanban](docs/KANBAN.md).

## Developer quick start

Python 3.11 or newer is recommended.  The runtime uses only the Python standard
library.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
```

Collect one measurement with the official Ookla CLI:

```bash
pihole-speedtest collect --database ./data/speedtest.db
```

Import a legacy CSV into a separate development database:

```bash
pihole-speedtest import-legacy-csv \
  ./speedtest.csv \
  --database ./data/imported-speedtest.db
```

The importer reports inserted, duplicate, timestamp-collision, and rejected
rows.  Distinct measurements that share a legacy timestamp are preserved and
reported rather than overwritten.  It returns exit code `2` when a row is
rejected or a timestamp collision is first imported so the migration requires
explicit review.  Running the same import again does not duplicate matching
measurements.

Start the companion dashboard:

```bash
pihole-speedtest serve \
  --database ./data/speedtest.db \
  --host 127.0.0.1 \
  --port 8765
```

Then open <http://127.0.0.1:8765/>.

## Raspberry Pi safety boundary

Development and automated tests run away from the live Pi-hole first.  The
approved companion is installed on the owner's Pi-hole host only through guarded,
recovery-backed gates.  The optional sidebar adapter is managed as a separate,
reversible deployment phase and has completed live owner acceptance.  The
verified device baseline is recorded in
[Verified Raspberry Pi Baseline](docs/VERIFIED-PI-BASELINE.md).

## License

MIT licensed.  See [LICENSE](LICENSE).

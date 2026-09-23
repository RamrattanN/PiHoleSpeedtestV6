# Pi-hole Speedtest v6

Pi-hole Speedtest v6 is a resilient speed-test companion for Pi-hole v6.  It
keeps collection, history, and the full dashboard independent from Pi-hole so a
Pi-hole upgrade cannot erase data or disable scheduled tests.

The project is a modernization of the MIT-licensed
[`arevindh/pihole-speedtest`](https://github.com/arevindh/pihole-speedtest).
The original product intent is preserved, while the implementation no longer
replaces Pi-hole Core or its web interface.

## Current status

This branch is an owner-approved development foundation, not a production
release.  Its dashboard is the visual and interaction baseline for subsequent
Pi-hole Speedtest work.  It provides:

- an official Ookla CLI collector;
- validated result parsing;
- SQLite history;
- a repeatable importer for valid legacy CSV history;
- a local API and Ramrattan Network Tools dashboard;
- local web assets with no CDN dependency;
- line and bar charts with fixed-scale time-axis zoom and pan;
- chart mouseover details for measurement time and values;
- optional table visibility and complete-history CSV export;
- dashboard controls for manual speed tests, collection-frequency changes,
  and reset;
- a verified SQLite recovery backup before every reset;
- unprivileged systemd service and schedule assets;
- automated unit tests and pull-request CI.

The approved companion service and 15-minute collection timer are running on
the verified Raspberry Pi 3 baseline.  Guarded installation and upgrade paths
exist, but a release-grade curl installer and data-preserving uninstaller are
still tracked in [issue #3](https://github.com/RamrattanN/PiHoleSpeedtestV6/issues/3).
A version-gated, reversible Pi-hole Web v6.6 adapter has passed disposable-copy
validation.  Its live installation remains a separately approved gate tracked
in [issue #2](https://github.com/RamrattanN/PiHoleSpeedtestV6/issues/2).

## Architecture

The product has two deliberately separate layers:

1. **Companion core:** collection, SQLite history, API, dashboard, service,
   scheduling, upgrades, and recovery.
2. **Optional Pi-hole adapter:** a small status card or navigation link.  If a
   Pi-hole update breaks the adapter, the companion core continues to work.

See [Architecture](docs/ARCHITECTURE.md),
[Approved Dashboard Baseline](docs/APPROVED-DASHBOARD-BASELINE.md),
[Pi-hole v6 Adapter](docs/PIHOLE-V6-ADAPTER.md),
[Origin and v6 Gap Analysis](docs/ORIGIN-AND-V6-GAP-ANALYSIS.md),
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
approved companion is installed on `192.168.2.14` only through guarded,
recovery-backed gates.  The optional sidebar adapter remains absent until its
separate live gate is approved and completed.  The verified device baseline is
recorded in
[Verified Raspberry Pi Baseline](docs/VERIFIED-PI-BASELINE.md).

## License and attribution

MIT licensed.  See [LICENSE](LICENSE).  The original project and its
contributors remain credited in the provenance documentation.

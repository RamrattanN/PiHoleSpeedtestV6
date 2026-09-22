# Pi-hole Speedtest v6

Pi-hole Speedtest v6 is a resilient speed-test companion for Pi-hole v6.  It
keeps collection, history, and the full dashboard independent from Pi-hole so a
Pi-hole upgrade cannot erase data or disable scheduled tests.

The project is a modernization of the MIT-licensed
[`arevindh/pihole-speedtest`](https://github.com/arevindh/pihole-speedtest).
The original product intent is preserved, while the implementation no longer
replaces Pi-hole Core or its web interface.

## Current status

This branch is an early development foundation, not a production release.  It
provides:

- an official Ookla CLI collector;
- validated result parsing;
- SQLite history;
- a repeatable importer for valid legacy CSV history;
- a read-only HTTP API and local dashboard;
- local web assets with no CDN dependency;
- automated unit tests and pull-request CI.

It does not yet install a service, schedule tests, modify the Pi-hole dashboard,
or provide an uninstall workflow.  Do not run the legacy installer on a live
Pi-hole.

## Architecture

The product has two deliberately separate layers:

1. **Companion core:** collection, SQLite history, API, dashboard, service,
   scheduling, upgrades, and recovery.
2. **Optional Pi-hole adapter:** a small status card or navigation link.  If a
   Pi-hole update breaks the adapter, the companion core continues to work.

See [Architecture](docs/ARCHITECTURE.md),
[Origin and v6 Gap Analysis](docs/ORIGIN-AND-V6-GAP-ANALYSIS.md),
[QA and Acceptance](docs/QA-AND-ACCEPTANCE.md), and
[Roadmap](docs/ROADMAP.md).

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

The importer reports inserted, duplicate, and rejected rows.  It returns exit
code `2` when any row is rejected so the migration requires explicit review.
Running the same import again does not duplicate matching measurements.

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
project will not be installed on `192.168.2.14` until the documented preflight,
backup, isolated collection, dashboard, rollback, and acceptance gates pass.
The verified device baseline is recorded in
[Verified Raspberry Pi Baseline](docs/VERIFIED-PI-BASELINE.md).

## License and attribution

MIT licensed.  See [LICENSE](LICENSE).  The original project and its
contributors remain credited in the provenance documentation.

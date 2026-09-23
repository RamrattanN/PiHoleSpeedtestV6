# Deployment status

Production deployment remains intentionally blocked until the systemd assets
pass isolated testing on the Raspberry Pi.

The former installer copied files into Pi-hole web directories and added a cron
entry before the runner and web page had reliable automated tests.  That path is
retained only as historical source while the safe installer, systemd units,
upgrade process, and rollback process are built.

Do not run `./mod`, `scripts/mod.sh`, or `scripts/install_dashboard.sh` on a
live Pi-hole from this development branch.

## Development-only execution

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
pihole-speedtest serve --database ./data/speedtest.db --host 127.0.0.1 --port 8765
```

## Implemented service shape

- application: `/opt/pihole-speedtest`
- data: `/var/lib/pihole-speedtest/speedtest.db`
- configuration: `/var/lib/pihole-speedtest/settings.json`
- service environment: `/etc/default/pihole-speedtest-v6`
- dashboard administrator token: `/var/lib/pihole-speedtest/admin.token`
- reset recovery backups: `/var/lib/pihole-speedtest/backups`
- service account: dedicated unprivileged account
- dashboard: independent HTTP service on a configurable LAN address and port
- schedule: systemd timer
- integration: optional and reversible Pi-hole v6 adapter

Development systemd units now exist under `deploy/systemd/` for:

- an always-on dashboard at LAN port `8765`;
- a one-shot official Ookla collection service;
- a persistent scheduler that checks every 15 minutes;
- a user-selected capture frequency from 15 minutes through once a day, with a
  60-minute default;
- an unprivileged `pihole-speedtest` service account;
- process locking that refuses overlapping collections.

Once installed and enabled by an administrator, the dashboard and collection
schedule run without an interactive Terminal session.  These units are not yet
approved for installation on the live Raspberry Pi.  The safe installer,
upgrade, verification, and rollback procedures must be completed and reviewed
first.

The authoritative deployment gates are in
[`docs/QA-AND-ACCEPTANCE.md`](docs/QA-AND-ACCEPTANCE.md).

The optional Pi-hole navigation integration is documented separately in
[`docs/PIHOLE-V6-ADAPTER.md`](docs/PIHOLE-V6-ADAPTER.md).  It must not be
installed before the companion service and isolated adapter validation pass.

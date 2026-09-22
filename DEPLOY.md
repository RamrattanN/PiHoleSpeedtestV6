# Deployment status

Production deployment is intentionally blocked during the companion-foundation
phase.

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

## Planned production shape

- application: `/opt/pihole-speedtest`
- data: `/var/lib/pihole-speedtest/speedtest.db`
- configuration: `/etc/pihole-speedtest/config.toml`
- service account: dedicated unprivileged account
- dashboard: independent HTTP service on a configurable LAN address and port
- schedule: systemd timer
- integration: optional and reversible Pi-hole v6 adapter

The authoritative deployment gates are in
[`docs/QA-AND-ACCEPTANCE.md`](docs/QA-AND-ACCEPTANCE.md).

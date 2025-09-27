# Pi hole Speedtest v6 Deploy

This package avoids network fetches and works with Pi hole v6 web paths.

## Contents
- `mod` and `test` wrappers that call local scripts
- `scripts/speedtest.sh` the runner
- `scripts/mod.sh` installer for web assets and schedule
- `web/` minimal page that reads JSON for a simple chart
- `docker/` assets for container builds

## Bare metal on your Pi hole
1. Copy the folder to your Pi hole box, for example to `/opt/pihole-speedtest`.
2. Install the runner and web assets.
   ```bash
   cd /opt/pihole-speedtest
   sudo ./mod --data-dir /etc/pihole/speedtest --cron "*/30 * * * *"
   ```
3. Ensure a CLI is installed.  Prefer Ookla:
   ```bash
   # Debian or Ubuntu
   sudo apt-get update
   # Then follow Ookla instructions to add their repo, or install librespeed-cli
   sudo apt-get install -y librespeed-cli
   ```
4. Run once to create files.
   ```bash
   sudo ./test -o /etc/pihole/speedtest
   ```
5. View the page at `http://<pihole>/speedtest/`.

## Docker
1. Place this folder next to your compose file.
2. Add the override from `docker/compose.override.yml` or bake the Dockerfile.
3. Rebuild and up.
   ```bash
   docker compose build --no-cache
   docker compose up -d
   ```
4. Exec into the container to install a CLI or mount it from host network namespace.
   ```bash
   docker exec -it pihole bash
   apt-get update && apt-get install -y librespeed-cli
   pihole-speedtest -o /etc/pihole/speedtest
   ```

## Scheduling
The installer writes a cron entry labeled `pihole-speedtest v6`.  Edit with `crontab -e`.

## Files
- CSV: `/etc/pihole/speedtest/speedtest.csv`
- JSON: `/etc/pihole/speedtest/speedtest.json`

# Pi-hole Speedtest v6

An independent Pi-hole Speedtest Mod designed for **Pi-hole v6**.  
This project removes all upstream dependencies, avoids network fetches, and provides:

- A local runner that writes results to **CSV and JSON**  
- A minimal web page served at `/speedtest/` with a chart and table  
- Support for both **bare metal installs** and **Docker deployments**

Maintained by **Nilesh Ramrattan**. Licensed under the MIT License.
A simple runner and web view for periodic internet speed tests that works with Pi hole v6.  No network fetches.  Local scripts only.

## What it does
- Runs a CLI speed test on a schedule.  Writes CSV and JSON.  
- Serves a minimal page at `/speedtest/` that reads `speedtest.json` and draws a chart.  
- Works on bare metal or in Docker.

## Install on the Pi hole device
```bash
sudo apt-get update
sudo apt-get install -y git librespeed-cli
sudo rm -rf /opt/pihole-speedtest
sudo git clone https://github.com/RamrattanN/PiHoleSpeedtestV6.git /opt/pihole-speedtest
cd /opt/pihole-speedtest
sudo chmod +x ./mod ./test ./scripts/mod.sh ./scripts/speedtest.sh
sudo ./mod --data-dir /etc/pihole/speedtest --cron "*/30 * * * *"
sudo ./test -o /etc/pihole/speedtest

Open http://<pihole-host>/speedtest/.

Docker (optional)

Use files in docker/, rebuild, then install a speedtest CLI in the container and run pihole-speedtest.

Files

CSV: /etc/pihole/speedtest/speedtest.csv

JSON: /etc/pihole/speedtest/speedtest.json

License

MIT License. Copyright (c) 2025 Nilesh Ramrattan.
"@ | Set-Content -Encoding UTF8 .\README.md
"""Run one scheduled collection at each quarter-hour boundary in Docker."""

from __future__ import annotations

import subprocess
import time


def seconds_until_next_slot(now: float) -> float:
    """Use wall-clock UTC boundaries so restarts do not shift the schedule."""
    return ((int(now) // 900) + 1) * 900 - now


def main() -> None:
    command = [
        "pihole-speedtest",
        "collect",
        "--database",
        "/data/speedtest.db",
        "--binary",
        "/usr/local/bin/speedtest",
        "--respect-schedule",
    ]
    while True:
        time.sleep(seconds_until_next_slot(time.time()))
        result = subprocess.run(command, check=False)
        if result.returncode:
            print(f"Scheduled collection exited with {result.returncode}", flush=True)


if __name__ == "__main__":
    main()

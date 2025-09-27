# Pi hole Speedtest v6 compatible package

This refactor removes network fetches, vendors the scripts, and installs a minimal page at `/speedtest/` that reads a JSON file produced by the runner.

Use `mod` to install and schedule.  Use `test` to run the speedtest once or loop with `--interval`.

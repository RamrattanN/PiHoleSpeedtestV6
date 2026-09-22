from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import List, Optional

from .collector import CollectionError, collect
from .server import serve
from .storage import Storage


def default_database() -> Path:
    configured = os.environ.get("PIHOLE_SPEEDTEST_DATABASE")
    if configured:
        return Path(configured).expanduser()
    return (
        Path.home()
        / ".local"
        / "share"
        / "pihole-speedtest"
        / "speedtest.db"
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="pihole-speedtest",
        description="Pi-hole v6 speed-test companion",
    )
    commands = root.add_subparsers(dest="command", required=True)

    collect_command = commands.add_parser(
        "collect", help="Run and store one official Ookla measurement"
    )
    collect_command.add_argument(
        "--database", type=Path, default=default_database()
    )
    collect_command.add_argument("--binary", default="speedtest")
    collect_command.add_argument("--timeout", type=int, default=180)

    serve_command = commands.add_parser(
        "serve", help="Serve the read-only companion dashboard"
    )
    serve_command.add_argument(
        "--database", type=Path, default=default_database()
    )
    serve_command.add_argument("--host", default="127.0.0.1")
    serve_command.add_argument("--port", type=int, default=8765)

    return root


def main(argv: Optional[List[str]] = None) -> int:
    arguments = parser().parse_args(argv)
    storage = Storage(arguments.database)

    if arguments.command == "collect":
        if arguments.timeout <= 0:
            parser().error("--timeout must be greater than zero")
        try:
            measurement = collect(arguments.binary, arguments.timeout)
        except CollectionError as exc:
            print(f"Collection failed: {exc}")
            return 1
        measurement_id = storage.insert(measurement)
        print(
            json.dumps(
                {"id": measurement_id, **measurement.to_dict()},
                ensure_ascii=False,
            )
        )
        return 0

    if not 1 <= arguments.port <= 65535:
        parser().error("--port must be between 1 and 65535")
    serve(storage, arguments.host, arguments.port)
    return 0

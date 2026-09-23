from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import List, Optional

from .adapter import AdapterError, install_adapter, remove_adapter
from .collector import CollectionError, collect
from .locking import CollectionLockedError, collection_lock
from .migration import LegacyImportError, import_legacy_csv
from .server import serve
from .settings import load_settings
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


def default_frame_ancestors() -> List[str]:
    return os.environ.get(
        "PIHOLE_SPEEDTEST_FRAME_ANCESTORS", ""
    ).split()


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
    collect_command.add_argument("--lock-file", type=Path)
    collect_command.add_argument("--settings-file", type=Path)
    collect_command.add_argument("--respect-schedule", action="store_true")

    import_command = commands.add_parser(
        "import-legacy-csv",
        help="Import valid history from the legacy CSV format",
    )
    import_command.add_argument("source", type=Path)
    import_command.add_argument(
        "--database", type=Path, default=default_database()
    )
    import_command.add_argument("--issue-limit", type=int, default=20)

    serve_command = commands.add_parser(
        "serve", help="Serve the read-only companion dashboard"
    )
    serve_command.add_argument(
        "--database", type=Path, default=default_database()
    )
    serve_command.add_argument("--host", default="127.0.0.1")
    serve_command.add_argument("--port", type=int, default=8765)
    serve_command.add_argument("--settings-file", type=Path)
    serve_command.add_argument("--admin-token-file", type=Path)
    serve_command.add_argument("--backup-directory", type=Path)
    serve_command.add_argument(
        "--frame-ancestor",
        action="append",
        default=default_frame_ancestors(),
        help="Trusted origin allowed to embed the dashboard",
    )
    serve_command.add_argument("--collection-binary")
    serve_command.add_argument("--collection-lock-file", type=Path)
    serve_command.add_argument("--collection-timeout", type=int, default=180)

    adapter_install = commands.add_parser(
        "adapter-install",
        help="Install the version-gated Pi-hole sidebar adapter",
    )
    adapter_install.add_argument("--web-root", type=Path, required=True)
    adapter_install.add_argument("--web-version", required=True)
    adapter_install.add_argument("--companion-url", required=True)
    adapter_install.add_argument("--backup-root", type=Path, required=True)

    adapter_remove = commands.add_parser(
        "adapter-remove",
        help="Remove an adapter using its verified recovery manifest",
    )
    adapter_remove.add_argument("--manifest", type=Path, required=True)

    return root


def main(argv: Optional[List[str]] = None) -> int:
    arguments = parser().parse_args(argv)

    if arguments.command == "adapter-install":
        try:
            manifest = install_adapter(
                arguments.web_root,
                arguments.web_version,
                arguments.companion_url,
                arguments.backup_root,
            )
        except AdapterError as exc:
            print(f"Adapter installation refused: {exc}")
            return 1
        print(json.dumps({"status": "installed", "manifest": str(manifest)}))
        return 0

    if arguments.command == "adapter-remove":
        try:
            remove_adapter(arguments.manifest)
        except AdapterError as exc:
            print(f"Adapter removal refused: {exc}")
            return 1
        print(json.dumps({"status": "removed"}))
        return 0

    storage = Storage(arguments.database)

    if arguments.command == "collect":
        if arguments.timeout <= 0:
            parser().error("--timeout must be greater than zero")
        lock_file = arguments.lock_file or Path(
            f"{arguments.database}.collect.lock"
        )
        if arguments.respect_schedule:
            settings_file = arguments.settings_file or arguments.database.with_name(
                "settings.json"
            )
            interval = load_settings(settings_file)["collection_interval_minutes"]
            if not storage.collection_is_due(interval):
                print(json.dumps({"status": "skipped", "reason": "not due"}))
                return 0
        try:
            with collection_lock(lock_file):
                measurement = collect(arguments.binary, arguments.timeout)
                measurement_id = storage.insert(measurement)
        except (CollectionError, CollectionLockedError) as exc:
            print(f"Collection failed: {exc}")
            return 1
        print(
            json.dumps(
                {"id": measurement_id, **measurement.to_dict()},
                ensure_ascii=False,
            )
        )
        return 0

    if arguments.command == "import-legacy-csv":
        if arguments.issue_limit < 0:
            parser().error("--issue-limit must not be negative")
        try:
            report = import_legacy_csv(
                arguments.source,
                storage,
                issue_limit=arguments.issue_limit,
            )
        except LegacyImportError as exc:
            print(f"Import failed: {exc}")
            return 1
        print(json.dumps(report.to_dict(), ensure_ascii=False))
        return 2 if report.rejected or report.timestamp_collisions else 0

    if not 1 <= arguments.port <= 65535:
        parser().error("--port must be between 1 and 65535")
    if arguments.collection_timeout <= 0:
        parser().error("--collection-timeout must be greater than zero")
    serve(
        storage,
        arguments.host,
        arguments.port,
        settings_file=arguments.settings_file,
        admin_token_file=arguments.admin_token_file,
        backup_directory=arguments.backup_directory,
        frame_ancestors=arguments.frame_ancestor,
        collection_binary=arguments.collection_binary,
        collection_lock_file=arguments.collection_lock_file,
        collection_timeout=arguments.collection_timeout,
    )
    return 0

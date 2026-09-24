import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from pihole_speedtest.cli import main
from pihole_speedtest.migration import (
    LegacyImportError,
    import_legacy_csv,
)
from pihole_speedtest.models import Measurement
from pihole_speedtest.storage import Storage


FIELDS = [
    "timestamp",
    "iso8601",
    "download_mbps",
    "upload_mbps",
    "latency_ms",
    "jitter_ms",
    "server",
    "interface",
]


def valid_row(**overrides):
    row = {
        "timestamp": "1790111401",
        "iso8601": "2026-09-22T21:10:01Z",
        "download_mbps": "324.40",
        "upload_mbps": "102.36",
        "latency_ms": "10.269",
        "jitter_ms": "10.327",
        "server": "Spectrum",
        "interface": "eth0",
    }
    row.update(overrides)
    return row


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.storage = Storage(self.root / "speedtest.db")

    def tearDown(self):
        self.temporary.cleanup()

    def write_csv(self, rows, fields=FIELDS):
        source = self.root / "legacy.csv"
        with source.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        return source

    def test_imports_valid_rows_and_reports_bad_and_duplicate_rows(self):
        source = self.write_csv(
            [
                valid_row(),
                valid_row(),
                valid_row(download_mbps=""),
            ]
        )

        report = import_legacy_csv(source, self.storage)

        self.assertEqual(report.rows, 3)
        self.assertEqual(report.inserted, 1)
        self.assertEqual(report.duplicates, 1)
        self.assertEqual(report.timestamp_collisions, 0)
        self.assertEqual(report.rejected, 1)
        self.assertEqual(report.issues[0].line, 4)
        self.assertIn("download_mbps", report.issues[0].reason)
        self.assertEqual(self.storage.count(), 1)

    def test_repeat_import_is_idempotent(self):
        source = self.write_csv([valid_row()])

        first = import_legacy_csv(source, self.storage)
        second = import_legacy_csv(source, self.storage)

        self.assertEqual(first.inserted, 1)
        self.assertEqual(second.inserted, 0)
        self.assertEqual(second.duplicates, 1)
        self.assertEqual(self.storage.count(), 1)

    def test_distinct_measurements_at_same_timestamp_are_preserved(self):
        self.storage.insert(
            Measurement(
                recorded_at="2026-09-22T21:10:01Z",
                download_mbps=1.0,
                upload_mbps=1.0,
                latency_ms=1.0,
                jitter_ms=1.0,
                server_name="Different",
                server_id="",
                interface_name="eth0",
            )
        )
        source = self.write_csv([valid_row()])

        report = import_legacy_csv(source, self.storage)

        self.assertEqual(report.inserted, 1)
        self.assertEqual(report.timestamp_collisions, 1)
        self.assertEqual(report.rejected, 0)
        self.assertEqual(self.storage.count(), 2)

        repeated = import_legacy_csv(source, self.storage)
        self.assertEqual(repeated.inserted, 0)
        self.assertEqual(repeated.duplicates, 1)
        self.assertEqual(repeated.timestamp_collisions, 0)
        self.assertEqual(self.storage.count(), 2)

    def test_small_epoch_difference_is_accepted(self):
        source = self.write_csv([valid_row(timestamp="1790111397")])

        report = import_legacy_csv(source, self.storage)

        self.assertEqual(report.inserted, 1)
        self.assertEqual(report.rejected, 0)

    def test_mismatched_epoch_and_iso_timestamp_is_rejected(self):
        source = self.write_csv([valid_row(timestamp="1")])

        report = import_legacy_csv(source, self.storage)

        self.assertEqual(report.rejected, 1)
        self.assertIn("do not match", report.issues[0].reason)

    def test_missing_columns_stop_before_import(self):
        source = self.write_csv([], fields=["iso8601"])

        with self.assertRaisesRegex(LegacyImportError, "missing columns"):
            import_legacy_csv(source, self.storage)

        self.assertEqual(self.storage.count(), 0)

    def test_cli_reports_partial_import_with_review_exit_code(self):
        source = self.write_csv(
            [valid_row(), valid_row(download_mbps="")]
        )
        output = io.StringIO()

        with redirect_stdout(output):
            status = main(
                [
                    "import-legacy-csv",
                    str(source),
                    "--database",
                    str(self.storage.path),
                ]
            )

        report = json.loads(output.getvalue())
        self.assertEqual(status, 2)
        self.assertEqual(report["inserted"], 1)
        self.assertEqual(report["timestamp_collisions"], 0)
        self.assertEqual(report["rejected"], 1)
        self.assertEqual(report["issues"][0]["line"], 3)

    def test_cli_reports_timestamp_collision_with_review_exit_code(self):
        self.storage.insert(
            Measurement(
                recorded_at="2026-09-22T21:10:01Z",
                download_mbps=1.0,
                upload_mbps=1.0,
                latency_ms=1.0,
                jitter_ms=1.0,
                server_name="Different",
                server_id="",
                interface_name="eth0",
            )
        )
        source = self.write_csv([valid_row()])
        output = io.StringIO()

        with redirect_stdout(output):
            status = main(
                [
                    "import-legacy-csv",
                    str(source),
                    "--database",
                    str(self.storage.path),
                ]
            )

        report = json.loads(output.getvalue())
        self.assertEqual(status, 2)
        self.assertEqual(report["inserted"], 1)
        self.assertEqual(report["timestamp_collisions"], 1)
        self.assertEqual(report["rejected"], 0)

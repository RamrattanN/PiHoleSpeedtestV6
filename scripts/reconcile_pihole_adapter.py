"""Internal helper; run only from the checksum-verified guarded installer."""

import fcntl
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pihole_speedtest.adapter import AdapterError
from pihole_speedtest.adapter_reconcile import inspect_restored, prepare, recover

LOCK = "/run/pihole-speedtest-adapter.lock"
INHERITED_LOCK = 9
ROOT_UID = 0


def acquire_lock():
    # The guarded installer passes its held lock as descriptor 9; reuse it there.
    lock = os.stat(LOCK, follow_symlinks=False) if os.path.lexists(LOCK) else None
    try:
        inherited = os.fstat(INHERITED_LOCK)
    except OSError:
        inherited = None
    if lock and inherited and (inherited.st_dev, inherited.st_ino) == (
        lock.st_dev,
        lock.st_ino,
    ):
        descriptor = INHERITED_LOCK
    else:
        descriptor = os.open(LOCK, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise AdapterError("another deployment operation is running") from exc


try:
    if len(sys.argv) != 2:
        raise ValueError("expected one operation: check, prepare or recover")
    operation = {"check": inspect_restored, "prepare": prepare, "recover": recover}[
        sys.argv[1]
    ]
    acquire_lock()
    print(
        operation(
            Path("/var/lib/pihole-speedtest"),
            Path("/var/lib/pihole-speedtest-adapter-recovery"),
            Path("/var/www/html/admin"),
            uid=ROOT_UID,
        )
    )
except (AdapterError, OSError, ValueError, KeyError, TypeError) as exc:
    raise SystemExit(f"STOP: Adapter reconciliation refused: {exc}") from exc

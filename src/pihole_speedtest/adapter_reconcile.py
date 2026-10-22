"""Fail-closed reconciliation of a recorded, fully restored production adapter.

This module changes deployment metadata only. The guarded shell installer owns
service/version checks, installation, rollback and completion of the journal.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
from datetime import datetime, timezone
from pathlib import Path

from .adapter import DONATE_ANCHOR, AdapterError, _page, _sha256, _sidebar_entry
from .adapter import _write_atomic as _atomic
from .pihole_headers import allow_companion_frame

APPROVED_SIDEBAR = "83943cbdf5258fe43e819108a5135e070d6742e273753ba398a8d28e1a008fdb"


def _write_atomic(path: Path, content: str) -> None:
    _atomic(path, content)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def trusted(path: Path, uid: int = 0, *, directory: bool = False) -> None:
    # Check lexical components before resolving; even dangling links are unsafe.
    if not path.is_absolute() or ".." in path.parts:
        raise AdapterError(f"unsafe path: {path}")
    for component in (path, *path.parents):
        if component.is_symlink():
            raise AdapterError(f"symlink is not permitted: {component}")
    info = path.stat()
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(info.st_mode) or info.st_uid != uid or info.st_mode & 0o022:
        raise AdapterError(f"untrusted type, owner or permissions: {path}")


def read_state(path: Path, uid: int) -> dict[str, str]:
    trusted(path, uid)
    values = {}
    for line in path.read_text().splitlines():
        if "=" not in line:
            raise AdapterError(f"malformed deployment manifest: {path}")
        key, value = line.split("=", 1)
        if key in values:
            raise AdapterError(f"duplicate deployment key: {key}")
        values[key] = value
    return values


def inspect_restored(
    data: Path,
    recovery: Path,
    web: Path,
    *,
    uid: int = 0,
    approved: str = APPROVED_SIDEBAR,
    _recovering: bool = False,
) -> Path:
    trusted(recovery, uid, directory=True)
    pending = recovery / "reconciliation.pending.json"
    if not _recovering and (pending.exists() or pending.is_symlink()):
        raise AdapterError(
            f"interrupted reconciliation; review {pending} and docs/ADAPTER-RECOVERY.md"
        )
    states = [
        read_state(data / name, uid)
        for name in ("install-manifest.txt", "collection-manifest.txt")
    ]
    active = states[0]
    for state in states:
        if state.get("pihole_adapter_installed") != "true":
            raise AdapterError(
                "deployment manifests must both record an installed adapter"
            )
        if state.get("pihole_adapter_manifest") != active.get(
            "pihole_adapter_manifest"
        ):
            raise AdapterError("deployment adapter references disagree")
    raw = active.get("pihole_adapter_manifest", "")
    path = Path(raw)
    if (
        path.name != "manifest.json"
        or path.parent.parent != recovery
        or not re.fullmatch(r"\d{8}T\d{12}Z", path.parent.name)
    ):
        raise AdapterError(
            "active deployment does not reference a trusted recovery manifest"
        )
    trusted(path.parent, uid, directory=True)
    trusted(path, uid)
    manifest = json.loads(path.read_text())
    sidebar = web / "scripts/lua/sidebar.lp"
    backup = path.with_name("sidebar.lp.before")
    pages = [web / "speedtest.lp", web / "speedtest-setup.lp"]
    if (
        manifest["schema"] != 1
        or manifest["web_version"] != "v6.6"
        or manifest["web_root"] != str(web)
        or manifest["sidebar"]["path"] != str(sidebar)
        or manifest["sidebar"]["backup"] != str(backup)
        or [entry["path"] for entry in manifest["created"]] != list(map(str, pages))
    ):
        raise AdapterError(
            "recovery schema, version or paths do not match the approved layout"
        )
    for digest in [
        manifest["sidebar"]["before_sha256"],
        manifest["sidebar"]["installed_sha256"],
        *[entry["sha256"] for entry in manifest["created"]],
    ]:
        if not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest):
            raise AdapterError("invalid recovery checksum")
    trusted(backup, uid)
    trusted(sidebar, uid)
    for parent in (web, web / "scripts", web / "scripts/lua"):
        trusted(parent, uid, directory=True)
    if manifest["sidebar"]["before_sha256"] != approved or _sha256(backup) != approved:
        raise AdapterError("sidebar recovery copy does not match the approved baseline")
    if _sha256(sidebar) != approved:
        raise AdapterError(
            "current sidebar is not the fully restored approved baseline"
        )
    if "PIHOLE-SPEEDTEST-V6" in sidebar.read_text():
        raise AdapterError("adapter markers remain in the sidebar")
    for page in pages:
        if page.exists() or page.is_symlink():
            raise AdapterError(
                f"adapter page is present; partial state is unsafe: {page}"
            )
    # Guarded installations always archive both deployment records and header arrays.
    for name in (
        "install-manifest.before.txt",
        "collection-manifest.before.txt",
        "pihole-web-headers.before.json",
        "pihole-web-headers.installed.json",
    ):
        trusted(path.with_name(name), uid)
    for name in ("pihole-web-headers.before.json", "pihole-web-headers.installed.json"):
        headers = json.loads(path.with_name(name).read_text())
        if not isinstance(headers, list) or not all(
            isinstance(h, str) for h in headers
        ):
            raise AdapterError("invalid header recovery evidence")
    before = json.loads(path.with_name("pihole-web-headers.before.json").read_text())
    installed = json.loads(
        path.with_name("pihole-web-headers.installed.json").read_text()
    )
    if allow_companion_frame(before, manifest["companion_url"]) != installed:
        raise AdapterError("historical header policies are inconsistent")
    original = backup.read_text()
    patched = original.replace(
        DONATE_ANCHOR, _sidebar_entry(manifest["companion_url"]) + DONATE_ANCHOR
    )
    companion, origin = manifest["companion_url"], manifest["pihole_origin"]
    expected = [
        patched,
        _page("Speedtest Overview", companion, origin, "overview"),
        _page("Speedtest Setup", companion, origin, "setup"),
    ]
    recorded = [
        manifest["sidebar"]["installed_sha256"],
        *[entry["sha256"] for entry in manifest["created"]],
    ]
    if [hashlib.sha256(text.encode()).hexdigest() for text in expected] != recorded:
        raise AdapterError("historical installed checksums are internally inconsistent")
    for name in ("install-manifest.before.txt", "collection-manifest.before.txt"):
        snapshot = read_state(path.with_name(name), uid)
        if (
            snapshot.get("pihole_adapter_installed") != "false"
            or "pihole_adapter_manifest" in snapshot
        ):
            raise AdapterError("historical deployment snapshot is inconsistent")
    return path


def prepare(data: Path, recovery: Path, web: Path, **checks) -> Path:
    old = inspect_restored(data, recovery, web, **checks)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    journal = recovery / f"reconciliation-{stamp}"
    journal.mkdir(mode=0o700)
    names = ("install-manifest.txt", "collection-manifest.txt")
    for name in names:
        shutil.copy2(data / name, journal / name)
        with (journal / name).open("rb") as snapshot:
            os.fsync(snapshot.fileno())
    evidence = {
        "schema": 1,
        "action": "reconcile-fully-restored-adapter",
        "historical_manifest": str(old),
        "historical_sha256": _sha256(old),
        "sidebar_sha256": _sha256(web / "scripts/lua/sidebar.lp"),
        "created_pages_absent": True,
        "started_at": stamp,
        "snapshots": {name: _sha256(journal / name) for name in names},
    }
    _write_atomic(
        journal / "reconciliation.json", json.dumps(evidence, indent=2) + "\n"
    )
    # Durable intent precedes either metadata write. A retry never bypasses it.
    _write_atomic(
        recovery / "reconciliation.pending.json",
        json.dumps({"journal": str(journal)}) + "\n",
    )
    for name in reversed(names):
        target = data / name
        lines = [
            line
            for line in target.read_text().splitlines()
            if not line.startswith(
                (
                    "pihole_adapter_installed=",
                    "pihole_adapter_manifest=",
                    "pihole_adapter_reconciliation=",
                )
            )
        ]
        lines.extend(
            [
                "pihole_adapter_installed=false",
                f"pihole_adapter_reconciliation={journal}",
            ]
        )
        _write_atomic(target, "\n".join(lines) + "\n")
    return journal


def recover(
    data: Path,
    recovery: Path,
    web: Path,
    *,
    uid: int = 0,
    approved: str = APPROVED_SIDEBAR,
) -> Path:
    """Restore metadata snapshots only when the web tree is still fully restored."""
    trusted(recovery, uid, directory=True)
    pending = recovery / "reconciliation.pending.json"
    trusted(pending, uid)
    journal = Path(json.loads(pending.read_text())["journal"])
    if journal.parent != recovery or not re.fullmatch(
        r"reconciliation-\d{8}T\d{12}Z", journal.name
    ):
        raise AdapterError("unsafe reconciliation journal path")
    trusted(journal, uid, directory=True)
    trusted(journal / "reconciliation.json", uid)
    evidence = json.loads((journal / "reconciliation.json").read_text())
    old = inspect_restored(
        journal, recovery, web, uid=uid, approved=approved, _recovering=True
    )
    if evidence["historical_manifest"] != str(old) or evidence[
        "historical_sha256"
    ] != _sha256(old):
        raise AdapterError("historical reconciliation evidence changed")
    names = ("install-manifest.txt", "collection-manifest.txt")
    for name in names:
        if _sha256(journal / name) != evidence["snapshots"][name]:
            raise AdapterError("reconciliation snapshot checksum mismatch")
        current = read_state(data / name, uid)
        original = read_state(journal / name, uid)
        # Only adapter metadata may differ. Never clobber a concurrent settings/deployment change.
        excluded = {
            "pihole_adapter_installed",
            "pihole_adapter_manifest",
            "pihole_adapter_reconciliation",
        }
        if {k: v for k, v in current.items() if k not in excluded} != {
            k: v for k, v in original.items() if k not in excluded
        }:
            raise AdapterError("deployment metadata changed outside reconciliation")
        if current.get("pihole_adapter_manifest") not in (None, str(old)):
            raise AdapterError(
                "new adapter manifest recorded; manual recovery review required"
            )
    for name in reversed(names):
        _write_atomic(data / name, (journal / name).read_text())
    _write_atomic(
        journal / "recovered.json",
        json.dumps({"recovered_at": datetime.now(timezone.utc).isoformat()}) + "\n",
    )
    pending.unlink()
    return journal

from __future__ import annotations

import hashlib
import html
import json
import os
import shutil
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SUPPORTED_WEB_VERSIONS = {"v6.6"}
BEGIN_MARKER = "<!-- BEGIN PIHOLE-SPEEDTEST-V6 -->"
END_MARKER = "<!-- END PIHOLE-SPEEDTEST-V6 -->"
DONATE_ANCHOR = '                <!-- Donate button -->'


class AdapterError(RuntimeError):
    """Raised when a safe adapter operation cannot be completed."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_atomic(path: Path, content: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as destination:
            destination.write(content)
            destination.flush()
            os.fsync(destination.fileno())
        temporary_path.chmod(mode)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _validated_url(value: str) -> str:
    parsed = urlparse(value)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise AdapterError(
            "companion URL must be an HTTP(S) origin without credentials, "
            "query, or fragment"
        )
    return value.rstrip("/")


def _sidebar_entry(companion_url: str) -> str:
    del companion_url
    return f"""{BEGIN_MARKER}
                <li class="menu-speedtest treeview<? if startsWith(scriptname, 'speedtest') then ?> active<? end ?>">
                    <a href="<?=webhome?>#">
                        <i class="fa fa-fw menu-icon fa-gauge-high"></i> <span>Speedtest</span>
                        <span class="pull-right-container"><i class="fa fa-angle-left pull-right"></i></span>
                    </a>
                    <ul class="treeview-menu">
                        <li<? if scriptname == 'speedtest' then ?> class="active"<? end ?>>
                            <a href="<?=webhome?>speedtest">
                                <i class="fa fa-fw menu-icon fa-chart-line"></i> <span>Overview</span>
                            </a>
                        </li>
                        <li<? if scriptname == 'speedtest/setup' then ?> class="active"<? end ?>>
                            <a href="<?=webhome?>speedtest-setup">
                                <i class="fa fa-fw menu-icon fa-sliders"></i> <span>Setup</span>
                            </a>
                        </li>
                    </ul>
                </li>
{END_MARKER}

"""


def _page(title: str, companion_url: str, view: str) -> str:
    safe_title = html.escape(title, quote=True)
    safe_source = html.escape(f"{companion_url}/?embed=1#{view}", quote=True)
    return f"""<?
mg.include('scripts/lua/header_authenticated.lp','r')
?>
<div class="page-header">
    <h1>{safe_title}</h1>
    <small>Ramrattan Network Tools companion service</small>
</div>
<div class="row">
    <div class="col-md-12">
        <div class="box">
            <div class="box-body" style="padding: 0; overflow: hidden;">
                <iframe
                    title="{safe_title}"
                    src="{safe_source}"
                    style="display: block; width: 100%; min-height: 1200px; border: 0;"
                    loading="eager"
                    referrerpolicy="no-referrer"
                ></iframe>
            </div>
        </div>
    </div>
</div>
<? mg.include('scripts/lua/footer.lp','r')?>
"""


def install_adapter(
    web_root: Path,
    web_version: str,
    companion_url: str,
    backup_root: Path,
) -> Path:
    if web_version not in SUPPORTED_WEB_VERSIONS:
        raise AdapterError(f"unsupported Pi-hole Web version: {web_version}")
    companion_url = _validated_url(companion_url)
    root = web_root.expanduser().resolve()
    sidebar = root / "scripts" / "lua" / "sidebar.lp"
    overview = root / "speedtest.lp"
    setup = root / "speedtest-setup.lp"
    if not sidebar.is_file():
        raise AdapterError(f"sidebar not found: {sidebar}")
    original = sidebar.read_text(encoding="utf-8")
    sidebar_mode = stat.S_IMODE(sidebar.stat().st_mode)
    if BEGIN_MARKER in original or END_MARKER in original:
        raise AdapterError("adapter markers already exist")
    if original.count(DONATE_ANCHOR) != 1 or 'class="sidebar-menu"' not in original:
        raise AdapterError("unrecognized Pi-hole v6.6 sidebar layout")
    for path in (overview, setup):
        if path.exists():
            raise AdapterError(f"adapter target already exists: {path}")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    recovery = backup_root.expanduser().resolve() / timestamp
    if recovery.exists():
        raise AdapterError(f"recovery directory already exists: {recovery}")
    recovery.mkdir(parents=True, mode=0o700)
    sidebar_backup = recovery / "sidebar.lp.before"
    shutil.copy2(sidebar, sidebar_backup)

    patched = original.replace(
        DONATE_ANCHOR,
        _sidebar_entry(companion_url) + DONATE_ANCHOR,
    )
    manifest_path = recovery / "manifest.json"
    try:
        _write_atomic(
            overview,
            _page("Speedtest Overview", companion_url, "overview"),
            0o644,
        )
        _write_atomic(
            setup,
            _page("Speedtest Setup", companion_url, "setup"),
            0o644,
        )
        _write_atomic(sidebar, patched, sidebar_mode)
        manifest: dict[str, Any] = {
            "schema": 1,
            "web_version": web_version,
            "web_root": str(root),
            "companion_url": companion_url,
            "sidebar": {
                "path": str(sidebar),
                "backup": str(sidebar_backup),
                "before_sha256": _sha256(sidebar_backup),
                "installed_sha256": _sha256(sidebar),
            },
            "created": [
                {"path": str(overview), "sha256": _sha256(overview)},
                {"path": str(setup), "sha256": _sha256(setup)},
            ],
        }
        _write_atomic(manifest_path, json.dumps(manifest, indent=2) + "\n")
    except Exception:
        shutil.copy2(sidebar_backup, sidebar)
        overview.unlink(missing_ok=True)
        setup.unlink(missing_ok=True)
        raise
    return manifest_path


def remove_adapter(manifest_path: Path) -> None:
    path = manifest_path.expanduser().resolve()
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdapterError(f"invalid recovery manifest: {path}") from exc
    if manifest.get("schema") != 1:
        raise AdapterError("unsupported recovery manifest schema")
    sidebar_info = manifest["sidebar"]
    sidebar = Path(sidebar_info["path"])
    backup = Path(sidebar_info["backup"])
    if not sidebar.is_file() or _sha256(sidebar) != sidebar_info["installed_sha256"]:
        raise AdapterError("installed sidebar changed after adapter installation")
    if not backup.is_file() or _sha256(backup) != sidebar_info["before_sha256"]:
        raise AdapterError("sidebar recovery copy is missing or invalid")
    for created in manifest["created"]:
        target = Path(created["path"])
        if not target.is_file() or _sha256(target) != created["sha256"]:
            raise AdapterError(f"installed adapter page changed: {target}")

    shutil.copy2(backup, sidebar)
    for created in manifest["created"]:
        Path(created["path"]).unlink()
    restored = dict(manifest)
    restored["removed_at"] = datetime.now(timezone.utc).isoformat()
    _write_atomic(path.with_name("removal.json"), json.dumps(restored, indent=2) + "\n")

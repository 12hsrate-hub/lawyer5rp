from __future__ import annotations

import os
import tempfile
from pathlib import Path


TEMP_DIR_ENV = "OGP_TMP_DIR"


def _candidate_temp_bases() -> list[Path]:
    candidates: list[Path] = []
    workspace_tmp = Path.cwd() / ".tmp"
    explicit = os.getenv(TEMP_DIR_ENV, "").strip()
    if explicit:
        candidates.append(Path(explicit))

    for env_name in ("TMP", "TEMP", "TMPDIR", "LOCALAPPDATA"):
        raw = os.getenv(env_name, "").strip()
        if not raw:
            continue
        path = Path(raw)
        if env_name == "LOCALAPPDATA":
            path = path / "Temp"
        candidates.append(path)

    candidates.append(workspace_tmp)
    candidates.append(Path(tempfile.gettempdir()))
    candidates.append(Path.home() / "AppData" / "Local" / "Temp")
    candidates.append(Path.cwd())

    unique: list[Path] = []
    seen: set[str] = set()
    for item in candidates:
        key = str(item).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _pick_writable_base() -> Path:
    for base in _candidate_temp_bases():
        try:
            base.mkdir(parents=True, exist_ok=True)
            probe = base / ".ogp_write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return base
        except OSError:
            continue
    raise OSError("No writable temp directory available for OGP.")


def get_temp_root(*, app_slug: str = "ogp_builder") -> Path:
    base = _pick_writable_base()
    workspace_root = Path.cwd().resolve()
    workspace_tmp = workspace_root / ".tmp"
    try:
        resolved_base = base.resolve()
    except OSError:
        resolved_base = base

    if resolved_base == workspace_root:
        root = workspace_tmp / app_slug
    elif resolved_base == workspace_tmp or resolved_base.name.lower() == app_slug.lower():
        root = resolved_base
    else:
        root = resolved_base / app_slug
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_named_temp_root(name: str, *, app_slug: str = "ogp_builder") -> Path:
    root = get_temp_root(app_slug=app_slug) / name
    root.mkdir(parents=True, exist_ok=True)
    return root


def configure_process_temp_dir(*, app_slug: str = "ogp_builder") -> Path:
    root = get_temp_root(app_slug=app_slug)
    resolved = str(root)
    os.environ["TMP"] = resolved
    os.environ["TEMP"] = resolved
    os.environ["TMPDIR"] = resolved
    tempfile.tempdir = resolved
    return root

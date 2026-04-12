from __future__ import annotations

"""
Legacy SQLite backup workflow.

Use scripts/backup_web_data.py for PostgreSQL-based production backups.
"""

import argparse
import json
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from shared.ogp_temp import get_named_temp_root


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = ROOT_DIR / "web" / "data"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "backups" / "web_data"
SQLITE_SUFFIXES = {".db", ".sqlite", ".sqlite3"}


def _collect_source_files(source_dir: Path) -> list[Path]:
    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory does not exist: {source_dir}")
    return sorted(path for path in source_dir.rglob("*") if path.is_file())


def _build_archive_path(output_dir: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    return output_dir / f"web_data_backup_{timestamp}.zip"


def _prune_old_archives(output_dir: Path, keep: int) -> list[Path]:
    archives = sorted(output_dir.glob("web_data_backup_*.zip"))
    to_delete = archives[:-keep] if keep > 0 else archives
    for path in to_delete:
        path.unlink(missing_ok=True)
    return to_delete


def _is_sqlite_path(path: Path) -> bool:
    return path.suffix.lower() in SQLITE_SUFFIXES


def _backup_sqlite_file(source_path: Path, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    source_conn = sqlite3.connect(str(source_path))
    try:
        target_conn = sqlite3.connect(str(target_path))
        try:
            source_conn.backup(target_conn)
        finally:
            target_conn.close()
    finally:
        source_conn.close()


def _copy_to_staging(source_dir: Path, files: list[Path], staging_dir: Path) -> tuple[list[str], list[dict[str, object]]]:
    archived_files: list[str] = []
    sqlite_snapshots: list[dict[str, object]] = []

    for source_path in files:
        relative_path = source_path.relative_to(source_dir)
        staged_path = staging_dir / relative_path
        staged_path.parent.mkdir(parents=True, exist_ok=True)

        if _is_sqlite_path(source_path):
            _backup_sqlite_file(source_path, staged_path)
            sqlite_snapshots.append(
                {
                    "path": str(relative_path),
                    "method": "sqlite_backup",
                    "size_bytes": staged_path.stat().st_size,
                }
            )
        else:
            shutil.copy2(source_path, staged_path)

        archived_files.append(str(relative_path))

    return archived_files, sqlite_snapshots


def create_backup(source_dir: Path, output_dir: Path, keep: int) -> dict[str, object]:
    files = _collect_source_files(source_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = _build_archive_path(output_dir)
    created_at = datetime.now(timezone.utc).isoformat()

    staging_root = get_named_temp_root("backup_staging") / f"ogp_backup_{uuid.uuid4().hex}"
    try:
        staging_dir = staging_root / "snapshot"
        archived_files, sqlite_snapshots = _copy_to_staging(source_dir, files, staging_dir)
        total_source_bytes = sum(path.stat().st_size for path in files)

        with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
            manifest = {
                "created_at_utc": created_at,
                "source_dir": str(source_dir),
                "file_count": len(files),
                "total_source_bytes": total_source_bytes,
                "sqlite_snapshot_count": len(sqlite_snapshots),
                "sqlite_snapshots": sqlite_snapshots,
                "files": archived_files,
            }
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            for staged_path in sorted(path for path in staging_dir.rglob("*") if path.is_file()):
                archive.write(staged_path, arcname=str(staged_path.relative_to(staging_dir)))
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)

    pruned = _prune_old_archives(output_dir, keep)
    archive_size = archive_path.stat().st_size if archive_path.exists() else 0
    return {
        "archive_path": str(archive_path),
        "file_count": len(files),
        "total_source_bytes": total_source_bytes,
        "archive_size_bytes": archive_size,
        "sqlite_snapshot_count": len(sqlite_snapshots),
        "pruned": [str(path) for path in pruned],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a timestamped backup of web/data with retention.")
    parser.add_argument("--source-dir", default=str(DEFAULT_SOURCE_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--keep", type=int, default=7, help="How many recent backup archives to keep.")
    args = parser.parse_args()

    result = create_backup(Path(args.source_dir), Path(args.output_dir), args.keep)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

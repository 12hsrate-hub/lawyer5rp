from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from shared.ogp_temp import get_named_temp_root


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = ROOT_DIR / "web" / "data"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "backups" / "web_data"


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


def _copy_to_staging(source_dir: Path, files: list[Path], staging_dir: Path) -> list[str]:
    archived_files: list[str] = []
    for source_path in files:
        relative_path = source_path.relative_to(source_dir)
        staged_path = staging_dir / relative_path
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, staged_path)
        archived_files.append(str(relative_path))
    return archived_files


def _dump_postgres_database(database_url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--no-privileges",
        f"--file={destination}",
        database_url,
    ]
    subprocess.run(command, check=True)


def create_backup(source_dir: Path, output_dir: Path, keep: int, database_url: str) -> dict[str, object]:
    files = _collect_source_files(source_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = _build_archive_path(output_dir)
    created_at = datetime.now(timezone.utc).isoformat()

    staging_root = get_named_temp_root("backup_staging") / f"ogp_backup_{uuid.uuid4().hex}"
    total_source_bytes = sum(path.stat().st_size for path in files)
    staged_dump_path = staging_root / "snapshot" / "postgres" / "database.dump"

    try:
        staging_dir = staging_root / "snapshot"
        archived_files = _copy_to_staging(source_dir, files, staging_dir)
        _dump_postgres_database(database_url, staged_dump_path)

        dump_relative_path = staged_dump_path.relative_to(staging_dir)
        with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
            manifest = {
                "created_at_utc": created_at,
                "source_dir": str(source_dir),
                "file_count": len(files),
                "total_source_bytes": total_source_bytes,
                "database_backup": {
                    "engine": "postgresql",
                    "method": "pg_dump_custom",
                    "artifact": dump_relative_path.as_posix(),
                    "database_url_masked": database_url.split("@")[-1] if "@" in database_url else "configured",
                },
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
        "postgres_dump": "postgres/database.dump",
        "pruned": [str(path) for path in pruned],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a timestamped backup of web/data + PostgreSQL dump with retention."
    )
    parser.add_argument("--source-dir", default=str(DEFAULT_SOURCE_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--keep", type=int, default=7, help="How many recent backup archives to keep.")
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("DATABASE_URL is required for PostgreSQL backups.")

    result = create_backup(Path(args.source_dir), Path(args.output_dir), args.keep, database_url)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

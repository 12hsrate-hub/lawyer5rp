from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


def _bootstrap_env() -> None:
    env_path = WEB_DIR / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


import os

_bootstrap_env()

from ogp_web.db import create_database_backend, load_database_config, run_migrations
from ogp_web.db.sqlite_to_postgres import PostgresMigrationTarget, migrate_sqlite_to_postgres
from ogp_web.env import load_web_env


DEFAULT_SOURCE_DIR = ROOT_DIR / "web" / "data"


def main() -> None:
    load_web_env()

    parser = argparse.ArgumentParser(description="Migrate OGP data from SQLite files to PostgreSQL.")
    parser.add_argument(
        "--source-dir",
        default=str(DEFAULT_SOURCE_DIR),
        help="Directory containing SQLite source files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Audit source data and show what would be inserted or updated without writing.",
    )
    parser.add_argument(
        "--skip-migrations",
        action="store_true",
        help="Do not run PostgreSQL schema migrations before importing data.",
    )
    args = parser.parse_args()

    config = load_database_config()
    if config.backend != "postgres":
        raise SystemExit("OGP_DB_BACKEND must be set to 'postgres' before running this migration.")

    if not args.skip_migrations:
        run_migrations(backend="postgres", dry_run=False)

    backend = create_database_backend()
    conn = backend.connect()
    try:
        report = migrate_sqlite_to_postgres(
            source_dir=Path(args.source_dir),
            target=PostgresMigrationTarget(conn),
            dry_run=args.dry_run,
        )
        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()
    except Exception:
        try:
            conn.rollback()
        finally:
            conn.close()
        raise
    else:
        conn.close()

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.db.migrations import list_migrations, run_migrations
from ogp_web.env import load_web_env


def main() -> None:
    load_web_env()

    parser = argparse.ArgumentParser(description="Run database migrations for OGP Web.")
    parser.add_argument("--backend", default=None, help="Target backend. Defaults to OGP_DB_BACKEND.")
    parser.add_argument("--dry-run", action="store_true", help="Show pending migrations without applying them.")
    args = parser.parse_args()

    if args.dry_run:
        pending = run_migrations(backend=args.backend, dry_run=True)
        if pending:
            print("Pending migrations:")
            for version in pending:
                print(f"- {version}")
        else:
            print("No pending migrations.")
        return

    available = list_migrations(args.backend)
    if not available:
        print("No migration files found.")
        return

    applied = run_migrations(backend=args.backend, dry_run=False)
    if applied:
        print("Applied migrations:")
        for version in applied:
            print(f"- {version}")
    else:
        print("Database is already up to date.")


if __name__ == "__main__":
    main()

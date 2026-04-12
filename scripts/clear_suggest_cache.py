from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from shared.ogp_ai_cache import _default_cache_dir


def resolve_cache_dir(raw_path: str) -> Path:
    candidate = Path(raw_path).expanduser().resolve() if raw_path else _default_cache_dir().resolve()
    return candidate


def clear_suggest_cache(cache_dir: Path, *, dry_run: bool = False) -> tuple[int, int]:
    removed_dirs = 0
    removed_files = 0
    if not cache_dir.exists():
        return (0, 0)

    operation_dir = cache_dir / "suggest_description"
    if operation_dir.exists():
        if dry_run:
            for path in operation_dir.rglob("*"):
                if path.is_file():
                    removed_files += 1
            removed_dirs += 1
        else:
            for path in operation_dir.rglob("*"):
                if path.is_file():
                    removed_files += 1
            shutil.rmtree(operation_dir, ignore_errors=True)
            removed_dirs += 1
    return (removed_dirs, removed_files)


def main() -> int:
    parser = argparse.ArgumentParser(description="Clear suggest_description cache entries.")
    parser.add_argument("--cache-dir", default="", help="Override cache directory (defaults to OGP ai cache dir).")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be removed without deleting.")
    args = parser.parse_args()

    cache_dir = resolve_cache_dir(args.cache_dir)
    removed_dirs, removed_files = clear_suggest_cache(cache_dir, dry_run=args.dry_run)
    mode = "dry-run" if args.dry_run else "execute"
    print(f"[{mode}] cache_dir={cache_dir}")
    print(f"removed_dirs={removed_dirs} removed_files={removed_files}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECK_SUFFIXES = {".py", ".js", ".html", ".css", ".json", ".md", ".txt", ".yml", ".yaml"}
SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}
SKIP_FILE_NAMES = set()


def iter_target_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.name in SKIP_FILE_NAMES:
            continue
        if path.suffix.lower() not in CHECK_SUFFIXES:
            continue
        files.append(path)
    return sorted(files)


def check_file(path: Path) -> str | None:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return "UTF-8 BOM is not allowed"
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return f"invalid UTF-8 at byte {exc.start}"
    return None


def main() -> int:
    failures: list[tuple[Path, str]] = []
    for path in iter_target_files():
        error = check_file(path)
        if error:
            failures.append((path.relative_to(ROOT), error))

    if failures:
        print("UTF-8 check failed:", file=sys.stderr)
        for path, error in failures:
            print(f"  {path}: {error}", file=sys.stderr)
        return 1

    print("UTF-8 check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import os
from pathlib import Path

from shared.ogp_temp import configure_process_temp_dir


ROOT_DIR = Path(__file__).resolve().parents[2]
WEB_DIR = ROOT_DIR / "web"
ENV_PATH = WEB_DIR / ".env"


def _parse_env_line(raw_line: str) -> tuple[str, str] | None:
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
        return None

    key, value = line.split("=", 1)
    key = key.strip()
    value = value.strip()

    if not key:
        return None

    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]

    return key, value


def load_web_env(env_path: str | Path | None = None) -> None:
    target_path = Path(env_path) if env_path is not None else ENV_PATH

    if not target_path.exists():
        configure_process_temp_dir()
        return

    for raw_line in target_path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_env_line(raw_line)
        if parsed is None:
            continue

        key, value = parsed
        os.environ.setdefault(key, value)

    configure_process_temp_dir()


def get_test_users() -> set[str]:
    raw = os.getenv("OGP_WEB_TEST_USERS", "").strip()
    if not raw:
        return set()
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def is_test_user(username: str) -> bool:
    return (username or "").strip().lower() in get_test_users()

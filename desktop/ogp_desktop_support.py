from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.ogp_models import Representative, Victim
from shared.ogp_temp import configure_process_temp_dir


APP_NAME = "OGP_Builder"
configure_process_temp_dir(app_slug=APP_NAME.lower())


def get_app_dir() -> Path:
    appdata = os.getenv("APPDATA")
    if appdata:
        path = Path(appdata) / APP_NAME
    else:
        path = Path.home() / f".{APP_NAME.lower()}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_runtime_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_DIR = get_app_dir()
RUNTIME_DIR = get_runtime_dir()
PROFILE_PATH = APP_DIR / "ogp_profile.json"
SETTINGS_PATH = APP_DIR / "ogp_local_settings.json"
LOG_PATH = APP_DIR / "ogp_builder.log"
LEGACY_SETTINGS_PATHS = [
    RUNTIME_DIR / "ogp_secrets.json",
    APP_DIR / "ogp_secrets.json",
]


def configure_logging() -> logging.Logger:
    logger = logging.getLogger(APP_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    logger.info("Логирование инициализировано")
    return logger


LOGGER = configure_logging()


def log_exception(message: str) -> None:
    LOGGER.exception(message)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f"{path.stem}_", suffix=path.suffix, dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        tmp_path.replace(path)
    except Exception:
        log_exception(f"Не удалось атомарно записать файл: {path}")
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            LOGGER.warning("Не удалось удалить временный файл: %s", tmp_path)
        raise


def mask_secret(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return "не задан"
    if len(raw) <= 10:
        return "*" * len(raw)
    return f"{raw[:6]}...{raw[-4:]}"


def safe_json_load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        log_exception(f"Поврежден JSON-файл: {path}")
        return {}
    except OSError:
        log_exception(f"Не удалось прочитать JSON-файл: {path}")
        return {}
    if not isinstance(data, dict):
        LOGGER.warning("JSON-файл не является объектом: %s", path)
        return {}
    return data


def sanitize_dataclass_payload(data: dict[str, Any], model_cls: type) -> dict[str, str]:
    allowed = {field.name for field in fields(model_cls)}
    return {key: str(data.get(key, "") or "").strip() for key in allowed}


class SettingsStore:
    DEFAULTS = {
        "OPENAI_API_KEY": "",
        "OPENAI_PROXY_URL": "",
    }

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict[str, str]:
        data = self.DEFAULTS.copy()
        if self.path.exists():
            loaded = safe_json_load(self.path)
            for key in self.DEFAULTS:
                data[key] = str(loaded.get(key, data[key]) or "").strip()
            return data

        migrated = self._migrate_legacy()
        if migrated:
            data.update(migrated)
            self.save(data)
        return data

    def save(self, data: dict[str, Any]) -> None:
        payload = self.DEFAULTS.copy()
        for key in self.DEFAULTS:
            payload[key] = str(data.get(key, payload[key]) or "").strip()
        atomic_write_text(self.path, json.dumps(payload, ensure_ascii=False, indent=2))

    def ensure_exists(self) -> None:
        if not self.path.exists():
            self.save(self.DEFAULTS)

    def _migrate_legacy(self) -> dict[str, str]:
        migrated: dict[str, str] = {}
        for legacy_path in LEGACY_SETTINGS_PATHS:
            if not legacy_path.exists():
                continue
            legacy = safe_json_load(legacy_path)
            for key in self.DEFAULTS:
                value = str(legacy.get(key, "") or "").strip()
                if value and not migrated.get(key):
                    migrated[key] = value
            if migrated:
                LOGGER.info("Мигрированы старые настройки из %s", legacy_path)
                break
        return migrated


class ProfileStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> Representative:
        if not self.path.exists():
            profile = Representative()
            self.save(profile)
            return profile
        payload = sanitize_dataclass_payload(safe_json_load(self.path), Representative)
        return Representative(**payload)

    def save(self, profile: Representative) -> None:
        atomic_write_text(self.path, json.dumps(asdict(profile), ensure_ascii=False, indent=2))


SETTINGS_STORE = SettingsStore(SETTINGS_PATH)
PROFILE_STORE = ProfileStore(PROFILE_PATH)


def write_settings_template() -> None:
    SETTINGS_STORE.ensure_exists()


def load_profile() -> Representative:
    return PROFILE_STORE.load()


def save_profile(rep: Representative) -> None:
    PROFILE_STORE.save(rep)


def load_settings() -> dict[str, str]:
    return SETTINGS_STORE.load()


def save_settings(data: dict[str, Any]) -> None:
    SETTINGS_STORE.save(data)


def is_valid_http_url(url: str) -> bool:
    raw = (url or "").strip()
    if not raw:
        return False
    parsed = urlparse(raw)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

from __future__ import annotations

import json
import os
from pathlib import Path

from ogp_web.db.factory import create_database_backend
from ogp_web.services.auth_service import AuthError

from .blackberry import BLACKBERRY_SERVER_CONFIG
from .types import ServerConfig


DEFAULT_SERVER_CODE = BLACKBERRY_SERVER_CONFIG.code

_BASE_SERVER_CONFIGS: dict[str, ServerConfig] = {
    BLACKBERRY_SERVER_CONFIG.code: BLACKBERRY_SERVER_CONFIG,
}


class ServerUnavailableError(AuthError):
    pass


def _normalized_code(value: str) -> str:
    return str(value or "").strip().lower()


def _load_codes_from_config_repo() -> set[str]:
    path = Path(str(os.getenv("OGP_SERVER_CONFIG_REPO", "")).strip())
    if not str(path):
        return set(_BASE_SERVER_CONFIGS.keys())
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set(_BASE_SERVER_CONFIGS.keys())
    if not isinstance(payload, dict):
        return set(_BASE_SERVER_CONFIGS.keys())
    raw_servers = payload.get("servers")
    if not isinstance(raw_servers, list):
        return set(_BASE_SERVER_CONFIGS.keys())
    codes = {
        _normalized_code(item.get("code", ""))
        for item in raw_servers
        if isinstance(item, dict)
    }
    return {code for code in codes if code}


def _load_server_rows_from_db() -> list[dict[str, object]]:
    try:
        backend = create_database_backend()
        conn = backend.connect()
    except Exception:
        return []
    try:
        rows = conn.execute("SELECT code, title, is_active FROM servers").fetchall()
        return [dict(row) for row in rows]
    except Exception:
        return []
    finally:
        conn.close()


def _load_runtime_server_configs() -> dict[str, ServerConfig]:
    allowed_codes = _load_codes_from_config_repo()
    rows = _load_server_rows_from_db()
    if not rows:
        return {
            code: config
            for code, config in _BASE_SERVER_CONFIGS.items()
            if code in allowed_codes
        }

    resolved: dict[str, ServerConfig] = {}
    for row in rows:
        code = _normalized_code(str(row.get("code") or ""))
        if not code or code not in allowed_codes:
            continue
        base = _BASE_SERVER_CONFIGS.get(code)
        if base is None:
            continue
        if not bool(row.get("is_active", True)):
            continue
        resolved[code] = ServerConfig(
            **{
                **base.__dict__,
                "name": str(row.get("title") or base.name),
            }
        )

    if resolved:
        return resolved
    return {
        code: config
        for code, config in _BASE_SERVER_CONFIGS.items()
        if code in allowed_codes
    }


def get_server_config(server_code: str) -> ServerConfig:
    normalized = _normalized_code(server_code) or DEFAULT_SERVER_CODE
    runtime_configs = _load_runtime_server_configs()
    try:
        return runtime_configs[normalized]
    except KeyError as exc:
        raise ServerUnavailableError(
            f"Сервер {normalized!r} недоступен или деактивирован. Выберите другой сервер в профиле."
        ) from exc


def list_server_configs() -> tuple[ServerConfig, ...]:
    return tuple(_load_runtime_server_configs().values())

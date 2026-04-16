from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ogp_web.db.factory import create_database_backend
from ogp_web.services.auth_service import AuthError

from .blackberry import BLACKBERRY_SERVER_CONFIG, BLACKBERRY_BOOTSTRAP_SERVER_PACK, build_server_config_from_pack
from .types import ServerConfig


DEFAULT_SERVER_CODE = BLACKBERRY_SERVER_CONFIG.code

_BASE_SERVER_CONFIGS: dict[str, ServerConfig] = {
    BLACKBERRY_SERVER_CONFIG.code: BLACKBERRY_SERVER_CONFIG,
}

_BOOTSTRAP_SERVER_PACKS: dict[str, dict[str, Any]] = {
    str(BLACKBERRY_BOOTSTRAP_SERVER_PACK.get("server_code") or DEFAULT_SERVER_CODE): dict(BLACKBERRY_BOOTSTRAP_SERVER_PACK),
}

_RESOLUTION_MODE_LABELS = {
    "published_pack": "published pack",
    "bootstrap_pack": "bootstrap pack",
    "neutral_fallback": "neutral fallback",
}


class ServerUnavailableError(AuthError):
    pass


def _normalized_code(value: str) -> str:
    return str(value or "").strip().lower()


def resolve_default_server_code(
    *,
    explicit_server_code: str = "",
    user_server_code: str = "",
    app_server_code: str = "",
    fallback_server_code: str = DEFAULT_SERVER_CODE,
) -> str:
    for candidate in (explicit_server_code, user_server_code, app_server_code, fallback_server_code, DEFAULT_SERVER_CODE):
        normalized = _normalized_code(candidate)
        if normalized:
            return normalized
    return DEFAULT_SERVER_CODE


def _load_codes_from_config_repo() -> set[str] | None:
    path = Path(str(os.getenv("OGP_SERVER_CONFIG_REPO", "")).strip())
    if not str(path):
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    raw_servers = payload.get("servers")
    if not isinstance(raw_servers, list):
        return None
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


def _load_effective_pack_from_db(*, server_code: str, at_timestamp: datetime | None) -> dict[str, Any] | None:
    normalized_code = _normalized_code(server_code)
    if not normalized_code:
        return None
    try:
        backend = create_database_backend()
        conn = backend.connect()
    except Exception:
        return None
    try:
        params: list[Any] = [normalized_code]
        timestamp_filter = ""
        if at_timestamp is not None:
            normalized_ts = at_timestamp if at_timestamp.tzinfo else at_timestamp.replace(tzinfo=timezone.utc)
            timestamp_filter = "AND published_at <= %s"
            params.append(normalized_ts)
        row = conn.execute(
            f"""
            SELECT id, server_code, version, status, metadata_json, created_at, published_at
            FROM server_packs
            WHERE server_code = %s AND status = 'published' {timestamp_filter}
            ORDER BY published_at DESC NULLS LAST, version DESC, id DESC
            LIMIT 1
            """,
            tuple(params),
        ).fetchone()
    except Exception:
        return None
    finally:
        conn.close()
    if row is None:
        return None
    return {
        "id": int(row.get("id") or 0),
        "server_code": str(row.get("server_code") or normalized_code),
        "version": int(row.get("version") or 0),
        "status": str(row.get("status") or "draft"),
        "metadata": dict(row.get("metadata_json") or {}),
        "created_at": row.get("created_at"),
        "published_at": row.get("published_at"),
    }


def _build_fallback_server_config(*, code: str, title: str) -> ServerConfig:
    display_name = str(title or code).strip() or code
    return ServerConfig(
        code=code,
        name=display_name,
        app_title=display_name,
    )


def effective_server_pack(server_code: str, at_timestamp: datetime | None = None) -> dict[str, Any]:
    normalized = resolve_default_server_code(explicit_server_code=server_code)
    db_pack = _load_effective_pack_from_db(server_code=normalized, at_timestamp=at_timestamp)
    if db_pack is not None:
        return db_pack
    bootstrap_pack = _BOOTSTRAP_SERVER_PACKS.get(normalized)
    if bootstrap_pack is not None:
        return dict(bootstrap_pack)
    return {
        "server_code": normalized,
        "version": 0,
        "status": "draft",
        "metadata": {},
    }


def build_runtime_resolution_snapshot(
    *,
    server_code: str,
    title: str = "",
    at_timestamp: datetime | None = None,
) -> dict[str, Any]:
    normalized = resolve_default_server_code(explicit_server_code=server_code)
    pack = effective_server_pack(normalized, at_timestamp=at_timestamp)
    pack_metadata = dict(pack.get("metadata") or {}) if isinstance(pack, dict) else {}
    if pack.get("id") is not None:
        resolution_mode = "published_pack"
    elif pack_metadata:
        resolution_mode = "bootstrap_pack"
    else:
        resolution_mode = "neutral_fallback"
    base_config = _BASE_SERVER_CONFIGS.get(normalized)
    resolved_title = str(title or (base_config.name if base_config else normalized) or normalized)
    runtime_config = _build_server_config_from_pack_or_base(
        code=normalized,
        title=resolved_title,
        base_config=base_config,
    )
    has_identity_capabilities = bool(
        runtime_config
        and (
            tuple(getattr(runtime_config, "organizations", ()) or ())
            or tuple(getattr(runtime_config, "procedure_types", ()) or ())
            or frozenset(getattr(runtime_config, "enabled_pages", frozenset()) or frozenset())
        )
    )
    return {
        "server_code": normalized,
        "pack": dict(pack or {}),
        "pack_metadata": pack_metadata,
        "resolution_mode": resolution_mode,
        "resolution_label": _RESOLUTION_MODE_LABELS.get(resolution_mode, resolution_mode.replace("_", " ")),
        "uses_transitional_fallback": resolution_mode != "published_pack",
        "requires_explicit_runtime_pack": resolution_mode == "neutral_fallback",
        "has_published_pack": pack.get("id") is not None,
        "has_bootstrap_pack": normalized in _BOOTSTRAP_SERVER_PACKS,
        "has_runtime_metadata": bool(pack_metadata),
        "has_identity_capabilities": has_identity_capabilities,
        "runtime_config": runtime_config,
    }


def resolve_document_builder_config(server_code: str) -> dict[str, Any]:
    pack = effective_server_pack(server_code)
    metadata = pack.get("metadata") if isinstance(pack, dict) else None
    if not isinstance(metadata, dict):
        return {}
    document_builder = metadata.get("document_builder")
    return dict(document_builder) if isinstance(document_builder, dict) else {}


def _build_server_config_from_pack_or_base(*, code: str, title: str, base_config: ServerConfig | None) -> ServerConfig:
    pack = effective_server_pack(code)
    metadata = pack.get("metadata") if isinstance(pack, dict) else None
    if isinstance(metadata, dict) and metadata:
        return build_server_config_from_pack(
            metadata=metadata,
            code=code,
            name=str(title or (base_config.name if base_config else code) or code),
        )
    if base_config is not None:
        return ServerConfig(
            **{
                **base_config.__dict__,
                "code": code,
                "name": str(title or base_config.name),
            }
        )
    return _build_fallback_server_config(code=code, title=title)


def _load_runtime_server_configs() -> dict[str, ServerConfig]:
    allowed_codes = _load_codes_from_config_repo()
    rows = _load_server_rows_from_db()

    resolved: dict[str, ServerConfig] = {}
    for row in rows:
        code = _normalized_code(str(row.get("code") or ""))
        if not code:
            continue
        if allowed_codes is not None and code not in allowed_codes:
            continue
        if not bool(row.get("is_active", True)):
            continue
        base = _BASE_SERVER_CONFIGS.get(code)
        resolved[code] = _build_server_config_from_pack_or_base(
            code=code,
            title=str(row.get("title") or code),
            base_config=base,
        )

    for code, config in _BASE_SERVER_CONFIGS.items():
        if allowed_codes is not None and code not in allowed_codes:
            continue
        resolved.setdefault(
            code,
            _build_server_config_from_pack_or_base(code=code, title=config.name, base_config=config),
        )
    return resolved


def get_server_config(server_code: str) -> ServerConfig:
    normalized = resolve_default_server_code(explicit_server_code=server_code)
    runtime_configs = _load_runtime_server_configs()
    try:
        return runtime_configs[normalized]
    except KeyError as exc:
        raise ServerUnavailableError(
            f"Сервер {normalized!r} недоступен или деактивирован. Выберите другой сервер в профиле."
        ) from exc


def list_server_configs() -> tuple[ServerConfig, ...]:
    return tuple(_load_runtime_server_configs().values())

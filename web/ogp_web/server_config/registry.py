from __future__ import annotations

from ogp_web.services.auth_service import AuthError

from .blackberry import BLACKBERRY_SERVER_CONFIG
from .types import ServerConfig


DEFAULT_SERVER_CODE = BLACKBERRY_SERVER_CONFIG.code

_SERVER_CONFIGS: dict[str, ServerConfig] = {
    BLACKBERRY_SERVER_CONFIG.code: BLACKBERRY_SERVER_CONFIG,
}


def get_server_config(server_code: str) -> ServerConfig:
    normalized = str(server_code or "").strip().lower() or DEFAULT_SERVER_CODE
    try:
        return _SERVER_CONFIGS[normalized]
    except KeyError as exc:
        raise AuthError(f"Unknown server code: {normalized!r}") from exc


def list_server_configs() -> tuple[ServerConfig, ...]:
    return tuple(_SERVER_CONFIGS.values())

from __future__ import annotations

from ogp_web.server_config import DEFAULT_SERVER_CODE, PermissionSet, ServerConfig, build_permission_set, get_server_config
from ogp_web.services.law_sources_validation import normalize_source_urls
from ogp_web.storage.user_store import UserStore


def resolve_server_config(*, server_code: str = "", fallback_server_code: str = DEFAULT_SERVER_CODE) -> ServerConfig:
    normalized_server_code = str(server_code or "").strip().lower()
    effective_server_code = normalized_server_code or str(fallback_server_code or DEFAULT_SERVER_CODE).strip().lower()
    return get_server_config(effective_server_code)


def resolve_server_law_bundle_path(*, server_code: str = "", fallback_server_code: str = DEFAULT_SERVER_CODE) -> str:
    server_config = resolve_server_config(server_code=server_code, fallback_server_code=fallback_server_code)
    return str(getattr(server_config, "law_qa_bundle_path", "") or "").strip()


def resolve_server_law_sources(*, server_code: str = "", fallback_server_code: str = DEFAULT_SERVER_CODE) -> tuple[str, ...]:
    server_config = resolve_server_config(server_code=server_code, fallback_server_code=fallback_server_code)
    return normalize_source_urls(getattr(server_config, "law_qa_sources", ()))


def resolve_user_server_context(
    user_store: UserStore,
    username: str,
    *,
    server_code: str = "",
) -> tuple[ServerConfig, PermissionSet]:
    fallback_server_code = user_store.get_server_code(username)
    server_config = resolve_server_config(server_code=server_code, fallback_server_code=fallback_server_code)
    permissions = build_permission_set(user_store, username, server_config)
    return server_config, permissions

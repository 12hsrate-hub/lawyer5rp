from __future__ import annotations

from ogp_web.server_config import PermissionSet, ServerConfig, build_permission_set, get_server_config
from ogp_web.storage.user_store import UserStore


def resolve_user_server_context(
    user_store: UserStore,
    username: str,
    *,
    server_code: str = "",
) -> tuple[ServerConfig, PermissionSet]:
    normalized_server_code = str(server_code or "").strip().lower()
    effective_server_code = normalized_server_code or user_store.get_server_code(username)
    server_config = get_server_config(effective_server_code)
    permissions = build_permission_set(user_store, username, server_config)
    return server_config, permissions

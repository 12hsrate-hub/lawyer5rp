from __future__ import annotations

from dataclasses import dataclass

from ogp_web.server_config import PermissionSet, ServerConfig, build_runtime_resolution_snapshot
from ogp_web.services.server_context_service import resolve_user_server_context
from ogp_web.storage.user_store import UserStore


@dataclass(frozen=True)
class SelectedServerContext:
    selected_server_code: str
    server_config: ServerConfig
    permissions: PermissionSet
    runtime_resolution_snapshot: dict[str, object]


def resolve_selected_server_context(
    user_store: UserStore,
    username: str,
    *,
    explicit_server_code: str = "",
) -> SelectedServerContext:
    server_config, permissions = resolve_user_server_context(
        user_store,
        username,
        server_code=explicit_server_code,
    )
    runtime_resolution_snapshot = build_runtime_resolution_snapshot(
        server_code=server_config.code,
        title=server_config.name,
    )
    return SelectedServerContext(
        selected_server_code=server_config.code,
        server_config=server_config,
        permissions=permissions,
        runtime_resolution_snapshot=runtime_resolution_snapshot,
    )

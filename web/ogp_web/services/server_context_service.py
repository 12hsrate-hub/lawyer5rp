from __future__ import annotations

from dataclasses import dataclass

from ogp_web.server_config import DEFAULT_SERVER_CODE, PermissionSet, ServerConfig, build_permission_set, get_server_config
from ogp_web.services.law_sources_validation import normalize_source_urls
from ogp_web.storage.user_store import UserStore


@dataclass(frozen=True)
class ServerLawContextSettings:
    source_urls: tuple[str, ...]
    bundle_path: str
    bundle_max_age_hours: int


@dataclass(frozen=True)
class ServerAiContextSettings:
    shadow_law_qa_profile: str
    shadow_suggest_profile: str
    suggest_prompt_mode: str
    suggest_low_confidence_policy: str


def resolve_server_config(*, server_code: str = "", fallback_server_code: str = DEFAULT_SERVER_CODE) -> ServerConfig:
    normalized_server_code = str(server_code or "").strip().lower()
    effective_server_code = normalized_server_code or str(fallback_server_code or DEFAULT_SERVER_CODE).strip().lower()
    return get_server_config(effective_server_code)


def extract_server_law_context_settings(server_config: object) -> ServerLawContextSettings:
    return ServerLawContextSettings(
        source_urls=normalize_source_urls(getattr(server_config, "law_qa_sources", ())),
        bundle_path=str(getattr(server_config, "law_qa_bundle_path", "") or "").strip(),
        bundle_max_age_hours=int(getattr(server_config, "law_qa_bundle_max_age_hours", 168) or 168),
    )


def extract_server_ai_context_settings(server_config: object) -> ServerAiContextSettings:
    return ServerAiContextSettings(
        shadow_law_qa_profile=str(getattr(server_config, "shadow_law_qa_profile", "") or "").strip(),
        shadow_suggest_profile=str(getattr(server_config, "shadow_suggest_profile", "") or "").strip(),
        suggest_prompt_mode=str(getattr(server_config, "suggest_prompt_mode", "legacy") or "legacy").strip().lower(),
        suggest_low_confidence_policy=str(
            getattr(server_config, "suggest_low_confidence_policy", "controlled_fallback") or "controlled_fallback"
        )
        .strip()
        .lower(),
    )


def resolve_server_law_bundle_path(*, server_code: str = "", fallback_server_code: str = DEFAULT_SERVER_CODE) -> str:
    server_config = resolve_server_config(server_code=server_code, fallback_server_code=fallback_server_code)
    return extract_server_law_context_settings(server_config).bundle_path


def resolve_server_law_sources(*, server_code: str = "", fallback_server_code: str = DEFAULT_SERVER_CODE) -> tuple[str, ...]:
    server_config = resolve_server_config(server_code=server_code, fallback_server_code=fallback_server_code)
    return extract_server_law_context_settings(server_config).source_urls


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

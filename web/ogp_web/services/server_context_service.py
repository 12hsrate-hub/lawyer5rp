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


@dataclass(frozen=True)
class ServerIdentitySettings:
    code: str
    name: str


@dataclass(frozen=True)
class ServerComplaintSettings:
    organizations: tuple[str, ...]
    complaint_basis_codes: tuple[str, ...]
    complaint_test_preset: dict[str, object]
    exam_sheet_url: str


def resolve_server_config(*, server_code: str = "", fallback_server_code: str = DEFAULT_SERVER_CODE) -> ServerConfig:
    normalized_server_code = str(server_code or "").strip().lower()
    effective_server_code = normalized_server_code or str(fallback_server_code or DEFAULT_SERVER_CODE).strip().lower()
    return get_server_config(effective_server_code)


def build_allowed_nav_items(items: object, permissions: PermissionSet) -> list[dict[str, str]]:
    return [
        {
            "key": str(getattr(item, "key", "") or "").strip(),
            "label": str(getattr(item, "label", "") or "").strip(),
            "href": str(getattr(item, "href", "") or "").strip(),
        }
        for item in (items or ())
        if permissions.allows(str(getattr(item, "permission", "") or "").strip())
    ]


def extract_server_shell_context(server_config: ServerConfig, permissions: PermissionSet | None = None) -> dict[str, object]:
    shell_context: dict[str, object] = {
        "server_code": server_config.code,
        "server_name": server_config.name,
        "app_title": server_config.app_title,
    }
    if permissions is None:
        return shell_context
    shell_context.update(
        {
            "page_nav_items": build_allowed_nav_items(server_config.page_nav_items, permissions),
            "complaint_nav_items": build_allowed_nav_items(server_config.complaint_nav_items, permissions),
            "complaint_bases": server_config.complaint_bases,
            "evidence_fields": server_config.evidence_fields,
            "complaint_forum_url": server_config.complaint_forum_url,
        }
    )
    return shell_context


def extract_server_identity_settings(
    server_config: object,
    *,
    fallback_server_code: str = DEFAULT_SERVER_CODE,
) -> ServerIdentitySettings:
    normalized_fallback = str(fallback_server_code or DEFAULT_SERVER_CODE).strip().lower() or DEFAULT_SERVER_CODE
    code = str(getattr(server_config, "code", normalized_fallback) or normalized_fallback).strip().lower() or normalized_fallback
    name = str(getattr(server_config, "name", code) or code).strip() or code
    return ServerIdentitySettings(code=code, name=name)


def extract_server_complaint_settings(server_config: object) -> ServerComplaintSettings:
    complaint_bases = tuple(getattr(server_config, "complaint_bases", ()) or ())
    complaint_basis_codes = tuple(
        str(getattr(item, "code", "") or "").strip()
        for item in complaint_bases
        if str(getattr(item, "code", "") or "").strip()
    )
    organizations = tuple(
        str(item or "").strip()
        for item in (getattr(server_config, "organizations", ()) or ())
        if str(item or "").strip()
    )
    complaint_test_preset = dict(getattr(server_config, "complaint_test_preset", {}) or {})
    exam_sheet_url = str(getattr(server_config, "exam_sheet_url", "") or "").strip()
    return ServerComplaintSettings(
        organizations=organizations,
        complaint_basis_codes=complaint_basis_codes,
        complaint_test_preset=complaint_test_preset,
        exam_sheet_url=exam_sheet_url,
    )


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


def extract_server_feature_flags(server_config: object) -> tuple[str, ...]:
    feature_flags = getattr(server_config, "feature_flags", ()) or ()
    normalized = [
        str(item or "").strip()
        for item in feature_flags
        if str(item or "").strip()
    ]
    return tuple(sorted(dict.fromkeys(normalized)))


def server_has_feature(server_config: object, feature_name: str) -> bool:
    checker = getattr(server_config, "has_feature", None)
    if callable(checker):
        try:
            return bool(checker(feature_name))
        except Exception:
            return False
    return str(feature_name or "").strip() in set(extract_server_feature_flags(server_config))


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


def resolve_user_server_permissions(
    user_store: UserStore,
    username: str,
    *,
    server_code: str = "",
) -> PermissionSet:
    _, permissions = resolve_user_server_context(user_store, username, server_code=server_code)
    return permissions

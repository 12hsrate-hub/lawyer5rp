from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from ogp_web.dependencies import get_admin_metrics_store, get_user_store, requires_permission
from ogp_web.schemas import (
    DocumentBuilderBundleResponse,
    DocumentBuilderSwitchDiff,
    DocumentBuilderSwitchPreviewPayload,
    DocumentBuilderSwitchPreviewResponse,
    ProfileResponse,
    RepresentativePayload,
    SelectedServerPayload,
    SelectedServerResponse,
)
from ogp_web.server_config import get_server_config
from ogp_web.services.auth_service import AuthUser, require_user
from ogp_web.services.profile_service import get_profile_payload, save_profile_payload
from ogp_web.storage.admin_metrics_store import AdminMetricsStore
from ogp_web.storage.user_store import UserStore


router = APIRouter(tags=["profile"])


_ALWAYS_REQUIRED_FIELDS = (
    "appeal_no",
    "org",
    "subject_names",
    "event_dt",
    "victim_name",
    "victim_passport",
    "victim_phone",
    "victim_discord",
    "victim_scan",
)
_OPTIONAL_DRAFT_LIST_FIELDS = ("video_fix_urls", "provided_video_urls")


def _required_fields(server_code: str) -> list[str]:
    config = get_server_config(server_code)
    required = list(_ALWAYS_REQUIRED_FIELDS)
    for item in config.evidence_fields:
        if item.required and item.field_name not in required:
            required.append(item.field_name)
    return required


def _bundle_for_server(server_code: str) -> DocumentBuilderBundleResponse:
    config = get_server_config(server_code)
    return DocumentBuilderBundleResponse(
        server_id=config.code,
        server_name=config.name,
        organizations=list(config.organizations),
        complaint_bases=[{"code": item.code, "label": item.label} for item in config.complaint_bases],
        required_fields=_required_fields(config.code),
        evidence_fields=[
            {"field_name": item.field_name, "label": item.label, "required": bool(item.required)}
            for item in config.evidence_fields
        ],
    )


def _as_string(value: object) -> str:
    return str(value or "").strip()


def _ensure_switchable_server(store: UserStore, username: str, target_server_id: str) -> str:
    normalized_target = str(target_server_id or "").strip().lower()
    if not normalized_target:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=["Укажите целевой сервер."])
    if normalized_target not in set(store.list_accessible_server_codes(username)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=["Недостаточно прав для переключения на выбранный сервер."],
        )
    return normalized_target


def _normalize_switch_draft(source: dict[str, Any], *, target_server_id: str) -> tuple[dict[str, Any], DocumentBuilderSwitchDiff]:
    target_config = get_server_config(target_server_id)
    allowed_orgs = set(target_config.organizations)
    allowed_bases = {item.code for item in target_config.complaint_bases}
    normalized = dict(source or {})
    keeps: list[str] = []
    clears: list[str] = []
    invalid_values: list[dict[str, str]] = []

    org = _as_string(normalized.get("org"))
    if org and allowed_orgs and org not in allowed_orgs:
        invalid_values.append(
            {"field": "org", "value": org, "reason": f"Организация не поддерживается на сервере {target_config.name}."}
        )
        normalized["org"] = ""
        clears.append("org")
    elif org:
        keeps.append("org")

    basis = _as_string(normalized.get("complaint_basis"))
    if basis and allowed_bases and basis not in allowed_bases:
        invalid_values.append(
            {"field": "complaint_basis", "value": basis, "reason": f"Основание не поддерживается на сервере {target_config.name}."}
        )
        normalized["complaint_basis"] = ""
        clears.append("complaint_basis")
    elif basis:
        keeps.append("complaint_basis")

    for field_name in _OPTIONAL_DRAFT_LIST_FIELDS:
        value = normalized.get(field_name)
        if isinstance(value, list):
            filtered = [str(item or "").strip() for item in value if str(item or "").strip()]
            normalized[field_name] = filtered
            if filtered:
                keeps.append(field_name)

    for field_name, value in normalized.items():
        if field_name in {"org", "complaint_basis", *set(_OPTIONAL_DRAFT_LIST_FIELDS)}:
            continue
        if isinstance(value, list):
            if any(str(item or "").strip() for item in value):
                keeps.append(field_name)
            continue
        if _as_string(value):
            keeps.append(field_name)

    required = _required_fields(target_server_id)
    missing_required = [field for field in required if not _as_string(normalized.get(field))]
    diff = DocumentBuilderSwitchDiff(
        keeps=sorted(set(keeps)),
        clears=sorted(set(clears)),
        new_required_fields=missing_required,
        invalid_values=invalid_values,
    )
    return normalized, diff


@router.get("/api/profile", response_model=ProfileResponse)
async def profile_get(
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
) -> ProfileResponse:
    return ProfileResponse(
        representative=get_profile_payload(store, user.username, server_code=user.server_code),
        server_code=user.server_code,
        message="Профиль загружен.",
    )


@router.put("/api/profile", response_model=ProfileResponse)
async def profile_save(
    payload: RepresentativePayload,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
) -> ProfileResponse:
    return ProfileResponse(
        representative=save_profile_payload(store, user.username, payload, server_code=user.server_code),
        server_code=user.server_code,
        message="Профиль представителя сохранён.",
    )


@router.patch("/api/profile/selected-server", response_model=SelectedServerResponse)
async def profile_selected_server(
    payload: SelectedServerPayload,
    user: AuthUser = Depends(require_user),
    store: UserStore = Depends(get_user_store),
) -> SelectedServerResponse:
    try:
        selected = store.set_selected_server_code(
            user.username,
            _ensure_switchable_server(store, user.username, payload.server_code),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    return SelectedServerResponse(
        server_code=selected,
        message="Сервер выбран. Обновите страницу для применения контекста.",
    )


@router.post("/api/document-builder/preview-switch", response_model=DocumentBuilderSwitchPreviewResponse)
async def document_builder_preview_switch(
    payload: DocumentBuilderSwitchPreviewPayload,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
) -> DocumentBuilderSwitchPreviewResponse:
    target_server_id = _ensure_switchable_server(store, user.username, payload.server_id)
    normalized_draft, diff = _normalize_switch_draft(payload.draft, target_server_id=target_server_id)
    return DocumentBuilderSwitchPreviewResponse(
        server_id=target_server_id,
        draft=normalized_draft,
        diff=diff,
        bundle=_bundle_for_server(target_server_id),
        message="Предпросмотр переключения сервера готов.",
    )


@router.post("/api/document-builder/confirm-switch", response_model=DocumentBuilderSwitchPreviewResponse)
async def document_builder_confirm_switch(
    payload: DocumentBuilderSwitchPreviewPayload,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
) -> DocumentBuilderSwitchPreviewResponse:
    target_server_id = _ensure_switchable_server(store, user.username, payload.server_id)
    old_server_id = user.server_code
    normalized_draft, diff = _normalize_switch_draft(payload.draft, target_server_id=target_server_id)
    store.set_selected_server_code(user.username, target_server_id)
    saved = store.save_complaint_draft(user.username, normalized_draft, server_code=target_server_id)
    metrics_store.log_event(
        event_type="document_builder_server_switch_confirmed",
        username=user.username,
        server_code=target_server_id,
        path="/api/document-builder/confirm-switch",
        method="POST",
        status_code=200,
        meta={
            "old_server_id": old_server_id,
            "new_server_id": target_server_id,
            "keeps_count": len(diff.keeps),
            "clears_count": len(diff.clears),
            "new_required_count": len(diff.new_required_fields),
            "invalid_count": len(diff.invalid_values),
        },
    )
    return DocumentBuilderSwitchPreviewResponse(
        server_id=target_server_id,
        draft=dict(saved.get("draft") or {}),
        diff=diff,
        bundle=_bundle_for_server(target_server_id),
        message="Сервер переключён. Черновик пересчитан и сохранён.",
    )

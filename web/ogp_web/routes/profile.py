from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ogp_web.dependencies import get_user_store, requires_permission
from ogp_web.server_config import ServerUnavailableError
from ogp_web.schemas import DraftSwitchAction, ProfileResponse, RepresentativePayload, SelectedServerPayload, SelectedServerResponse
from ogp_web.services.auth_service import AuthUser, require_user
from ogp_web.services.complaint_draft_schema import classify_switch_actions, normalize_complaint_draft
from ogp_web.services.profile_service import get_profile_payload, save_profile_payload
from ogp_web.services.server_context_service import resolve_user_server_config
from ogp_web.storage.user_store import UserStore


router = APIRouter(tags=["profile"])

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
        selected = store.set_selected_server_code(user.username, payload.server_code)
    except (ValueError, ServerUnavailableError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc

    target_config = resolve_user_server_config(store, user.username, server_code=selected)
    current_draft = store.get_complaint_draft(user.username, server_code=selected).get("draft", {})
    normalized = normalize_complaint_draft(current_draft, config=target_config)
    switch_items = classify_switch_actions(normalized.draft, target_config=target_config)
    return SelectedServerResponse(
        server_code=selected,
        message="Сервер выбран. Обновите страницу для применения контекста.",
        switch_actions=[DraftSwitchAction(semantic_key=item.semantic_key, action=item.action, detail=item.detail) for item in switch_items],
    )

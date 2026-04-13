from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ogp_web.dependencies import get_user_store
from ogp_web.schemas import ProfileResponse, RepresentativePayload, SelectedServerPayload, SelectedServerResponse
from ogp_web.services.auth_service import AuthUser, require_user
from ogp_web.services.profile_service import get_profile_payload, save_profile_payload
from ogp_web.storage.user_store import UserStore


router = APIRouter(tags=["profile"])

@router.get("/api/profile", response_model=ProfileResponse)
async def profile_get(
    user: AuthUser = Depends(require_user),
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
    user: AuthUser = Depends(require_user),
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
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    return SelectedServerResponse(
        server_code=selected,
        message="Сервер выбран. Обновите страницу для применения контекста.",
    )

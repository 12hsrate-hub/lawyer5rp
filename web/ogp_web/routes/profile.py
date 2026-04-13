from __future__ import annotations

from fastapi import APIRouter, Depends

from ogp_web.dependencies import get_user_store, requires_permission
from ogp_web.schemas import ProfileResponse, RepresentativePayload
from ogp_web.services.auth_service import AuthUser
from ogp_web.services.profile_service import get_profile_payload, save_profile_payload
from ogp_web.storage.user_store import UserStore


router = APIRouter(tags=["profile"])

@router.get("/api/profile", response_model=ProfileResponse)
async def profile_get(
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
) -> ProfileResponse:
    return ProfileResponse(
        representative=get_profile_payload(store, user.username),
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
        representative=save_profile_payload(store, user.username, payload),
        server_code=user.server_code,
        message="Профиль представителя сохранён.",
    )

from __future__ import annotations

from functools import partial

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from ogp_web.dependencies import get_user_store
from ogp_web.schemas import ProfileResponse, RepresentativePayload
from ogp_web.services.auth_service import AuthUser, require_user
from ogp_web.services.profile_service import get_profile_payload, save_profile_payload
from ogp_web.storage.user_store import UserStore


router = APIRouter(tags=["profile"])


async def _run_sync_io(func, /, *args, **kwargs):
    return await run_in_threadpool(partial(func, *args, **kwargs))


@router.get("/api/profile", response_model=ProfileResponse)
async def profile_get(
    user: AuthUser = Depends(require_user),
    store: UserStore = Depends(get_user_store),
) -> ProfileResponse:
    return ProfileResponse(
        representative=await _run_sync_io(get_profile_payload, store, user.username),
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
        representative=await _run_sync_io(save_profile_payload, store, user.username, payload),
        server_code=user.server_code,
        message="Профиль представителя сохранён.",
    )

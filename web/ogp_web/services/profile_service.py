from __future__ import annotations

from fastapi import HTTPException, status

from ogp_web.schemas import RepresentativePayload
from ogp_web.services.auth_service import AuthError
from ogp_web.storage.user_store import UserStore


def get_profile_payload(store: UserStore, username: str) -> RepresentativePayload:
    try:
        profile = store.get_representative_profile(username)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    return RepresentativePayload(**profile)


def save_profile_payload(store: UserStore, username: str, payload: RepresentativePayload) -> RepresentativePayload:
    try:
        profile = store.save_representative_profile(username, payload.model_dump())
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    return RepresentativePayload(**profile)

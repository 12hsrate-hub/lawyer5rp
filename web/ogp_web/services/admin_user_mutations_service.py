from __future__ import annotations

from typing import Any, Callable

from ogp_web.services.auth_service import AuthError
from ogp_web.storage.user_store import UserStore


def verify_admin_user_email_payload(*, user_store: UserStore, username: str) -> dict[str, Any]:
    return {"ok": True, "user": user_store.admin_mark_email_verified(username)}


def block_admin_user_payload(*, user_store: UserStore, username: str, reason: str) -> dict[str, Any]:
    return {"ok": True, "user": user_store.admin_set_access_blocked(username, reason)}


def unblock_admin_user_payload(*, user_store: UserStore, username: str) -> dict[str, Any]:
    return {"ok": True, "user": user_store.admin_clear_access_blocked(username)}


def grant_tester_payload(*, user_store: UserStore, username: str) -> dict[str, Any]:
    return {"ok": True, "user": user_store.admin_set_tester_status(username, True)}


def revoke_tester_payload(*, user_store: UserStore, username: str) -> dict[str, Any]:
    return {"ok": True, "user": user_store.admin_set_tester_status(username, False)}


def grant_gka_payload(*, user_store: UserStore, username: str) -> dict[str, Any]:
    return {"ok": True, "user": user_store.admin_set_gka_status(username, True)}


def revoke_gka_payload(*, user_store: UserStore, username: str) -> dict[str, Any]:
    return {"ok": True, "user": user_store.admin_set_gka_status(username, False)}


def update_admin_user_email_payload(*, user_store: UserStore, username: str, email: str) -> dict[str, Any]:
    return {"ok": True, "user": user_store.admin_update_email(username, email)}


def reset_admin_user_password_payload(*, user_store: UserStore, username: str, password: str) -> dict[str, Any]:
    return {"ok": True, "user": user_store.admin_reset_password(username, password)}


def deactivate_admin_user_payload(*, user_store: UserStore, username: str, reason: str) -> dict[str, Any]:
    return {"ok": True, "user": user_store.admin_deactivate_user(username, reason)}


def reactivate_admin_user_payload(*, user_store: UserStore, username: str) -> dict[str, Any]:
    return {"ok": True, "user": user_store.admin_reactivate_user(username)}


def set_admin_user_daily_quota_payload(*, user_store: UserStore, username: str, daily_limit: int) -> dict[str, Any]:
    return {"ok": True, "user": user_store.admin_set_daily_quota(username, daily_limit)}


def run_admin_user_mutation(mutation: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return mutation()
    except AuthError as exc:
        raise ValueError(str(exc)) from exc

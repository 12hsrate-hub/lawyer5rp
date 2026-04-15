from __future__ import annotations

from typing import Any, Callable

from fastapi import HTTPException, status

from ogp_web.services.auth_service import AuthError
from ogp_web.services.auth_service import AuthUser
from ogp_web.storage.admin_metrics_store import AdminMetricsStore
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


def execute_bulk_user_mutation_action(
    *,
    payload: Any,
    user: AuthUser,
    metrics_store: AdminMetricsStore,
    user_store: UserStore,
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    action = str(payload.action or "").strip().lower()
    if action == "set_daily_quota" and payload.daily_limit is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=["Для set_daily_quota обязательно поле daily_limit."])
    usernames = [str(item or "").strip().lower() for item in payload.usernames if str(item or "").strip()]
    if not usernames:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=["Не переданы пользователи для массовой операции."])

    results: list[dict[str, Any]] = []
    success_count = 0
    total = len(usernames)
    for index, username in enumerate(usernames, start=1):
        try:
            mutation_result, event_type, path, meta = _execute_single_bulk_mutation(
                action=action,
                username=username,
                payload=payload,
                user_store=user_store,
            )
            metrics_store.log_event(
                event_type=event_type,
                username=user.username,
                server_code=user.server_code,
                path=path,
                method="POST",
                status_code=200,
                meta=meta,
            )
            success_count += 1
            results.append({"username": username, "ok": True, "user": mutation_result.get("user")})
        except Exception as exc:  # noqa: BLE001
            results.append({"username": username, "ok": False, "error": str(exc)})
        if progress_callback:
            progress_callback(index, total)

    return {
        "action": action,
        "total": total,
        "success_count": success_count,
        "failed_count": total - success_count,
        "results": results,
    }


def _execute_single_bulk_mutation(
    *,
    action: str,
    username: str,
    payload: Any,
    user_store: UserStore,
) -> tuple[dict[str, Any], str, str, dict[str, Any]]:
    if action == "verify_email":
        result = verify_admin_user_email_payload(user_store=user_store, username=username)
        return result, "admin_verify_email", f"/api/admin/users/{username}/verify-email", {"target_username": username, "bulk": True}
    if action == "block":
        result = block_admin_user_payload(user_store=user_store, username=username, reason=payload.reason)
        return result, "admin_block_user", f"/api/admin/users/{username}/block", {"target_username": username, "reason": payload.reason, "bulk": True}
    if action == "unblock":
        result = unblock_admin_user_payload(user_store=user_store, username=username)
        return result, "admin_unblock_user", f"/api/admin/users/{username}/unblock", {"target_username": username, "bulk": True}
    if action == "grant_tester":
        result = grant_tester_payload(user_store=user_store, username=username)
        return result, "admin_grant_tester", f"/api/admin/users/{username}/grant-tester", {"target_username": username, "bulk": True}
    if action == "revoke_tester":
        result = revoke_tester_payload(user_store=user_store, username=username)
        return result, "admin_revoke_tester", f"/api/admin/users/{username}/revoke-tester", {"target_username": username, "bulk": True}
    if action == "grant_gka":
        result = grant_gka_payload(user_store=user_store, username=username)
        return result, "admin_grant_gka", f"/api/admin/users/{username}/grant-gka", {"target_username": username, "bulk": True}
    if action == "revoke_gka":
        result = revoke_gka_payload(user_store=user_store, username=username)
        return result, "admin_revoke_gka", f"/api/admin/users/{username}/revoke-gka", {"target_username": username, "bulk": True}
    if action == "deactivate":
        result = deactivate_admin_user_payload(user_store=user_store, username=username, reason=payload.reason)
        return result, "admin_deactivate_user", f"/api/admin/users/{username}/deactivate", {"target_username": username, "reason": payload.reason, "bulk": True}
    if action == "reactivate":
        result = reactivate_admin_user_payload(user_store=user_store, username=username)
        return result, "admin_reactivate_user", f"/api/admin/users/{username}/reactivate", {"target_username": username, "bulk": True}
    if action == "set_daily_quota":
        safe_limit = int(payload.daily_limit or 0)
        result = set_admin_user_daily_quota_payload(user_store=user_store, username=username, daily_limit=safe_limit)
        return result, "admin_set_daily_quota", f"/api/admin/users/{username}/daily-quota", {"target_username": username, "daily_limit": safe_limit, "bulk": True}
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[f"Неизвестное bulk-действие: {action}."])

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from ogp_web.storage.admin_metrics_store import AdminMetricsStore
from ogp_web.storage.user_store import UserStore


def build_admin_users_payload(
    *,
    metrics_store: AdminMetricsStore,
    user_store: UserStore,
    search: str = "",
    blocked_only: bool = False,
    tester_only: bool = False,
    gka_only: bool = False,
    unverified_only: bool = False,
    user_sort: str = "complaints",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    overview = metrics_store.get_overview(
        users=user_store.list_users(),
        search=search,
        blocked_only=blocked_only,
        tester_only=tester_only,
        gka_only=gka_only,
        unverified_only=unverified_only,
        user_sort=user_sort,
    )
    users = overview.get("users", [])
    total = len(users)
    paged = users[offset : offset + limit]
    return {
        "items": paged,
        "total": total,
        "limit": limit,
        "offset": offset,
        "filters": {
            "search": search,
            "blocked_only": blocked_only,
            "tester_only": tester_only,
            "gka_only": gka_only,
            "unverified_only": unverified_only,
            "user_sort": user_sort,
        },
    }


def build_admin_user_details_payload(
    *,
    metrics_store: AdminMetricsStore,
    user_store: UserStore,
    username: str,
) -> dict[str, Any]:
    normalized = str(username or "").strip().lower()
    overview = metrics_store.get_overview(users=user_store.list_users(), search=normalized)
    users = overview.get("users", [])
    target = next((item for item in users if str(item.get("username", "")).strip().lower() == normalized), None)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Пользователь не найден."])

    recent_actions = [
        event
        for event in overview.get("recent_events", [])
        if str(event.get("username", "")).strip().lower() == normalized
        or str((event.get("meta") or {}).get("target_username", "")).strip().lower() == normalized
    ][:20]

    permission_codes = user_store.get_permission_codes(normalized, server_code=target.get("server_code"))
    effective_permissions = {
        "manage_servers": "manage_servers" in permission_codes,
        "manage_laws": "manage_laws" in permission_codes,
        "view_analytics": "view_analytics" in permission_codes,
        "exam_import": "exam_import" in permission_codes,
        "court_claims": "court_claims" in permission_codes,
        "complaint_presets": "complaint_presets" in permission_codes,
    }

    recent_events = [event for event in overview.get("recent_events", []) if str(event.get("username", "")).strip().lower() == normalized][:20]
    failed_events = [event for event in recent_events if int(event.get("status_code") or 0) >= 400]
    activity_snapshot = {
        "api_requests": int(target.get("api_requests") or 0),
        "failed_api_requests": int(target.get("failed_api_requests") or 0),
        "complaints": int(target.get("complaints") or 0),
        "rehabs": int(target.get("rehabs") or 0),
        "ai_suggestions": int(target.get("ai_suggestions") or 0),
        "ai_ocr_requests": int(target.get("ai_ocr_requests") or 0),
        "resource_units": int(target.get("resource_units") or 0),
        "risk_score": int(target.get("risk_score") or 0),
        "risk_flags": list(target.get("risk_flags") or []),
        "recent_events_count": len(recent_events),
        "recent_errors_count": len(failed_events),
    }

    return {
        "user": target,
        "effective_permissions": effective_permissions,
        "recent_admin_actions": recent_actions,
        "recent_events": recent_events,
        "activity_snapshot": activity_snapshot,
    }


def build_admin_role_history_payload(
    *,
    metrics_store: AdminMetricsStore,
    user_store: UserStore,
    limit: int,
) -> dict[str, Any]:
    overview = metrics_store.get_overview(users=user_store.list_users())
    role_events = {
        "admin_grant_tester",
        "admin_revoke_tester",
        "admin_grant_gka",
        "admin_revoke_gka",
    }
    items = [event for event in overview.get("recent_events", []) if str(event.get("event_type", "")) in role_events]
    return {
        "items": items[:limit],
        "total": len(items),
    }


def build_admin_users_csv_content(
    *,
    metrics_store: AdminMetricsStore,
    user_store: UserStore,
    search: str = "",
    blocked_only: bool = False,
    tester_only: bool = False,
    gka_only: bool = False,
    unverified_only: bool = False,
    users_limit: int = 0,
    user_sort: str = "complaints",
) -> str:
    return metrics_store.export_users_csv(
        users=user_store.list_users(limit=normalize_optional_positive_int(users_limit)),
        search=search,
        blocked_only=blocked_only,
        tester_only=tester_only,
        gka_only=gka_only,
        unverified_only=unverified_only,
        user_sort=user_sort,
    )


def normalize_optional_positive_int(value: Any) -> int | None:
    try:
        normalized = int(value)
        if normalized <= 0:
            return None
        return normalized
    except (TypeError, ValueError):
        return None

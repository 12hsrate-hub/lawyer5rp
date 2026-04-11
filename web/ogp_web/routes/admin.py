from __future__ import annotations

import json
import threading
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any
from time import monotonic
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, Response
from datetime import datetime, timezone

from ogp_web.dependencies import get_admin_metrics_store, get_exam_answers_store, get_user_store
from ogp_web.server_config import build_permission_set, get_server_config
from ogp_web.schemas import (
    AdminBlockPayload,
    AdminBulkActionPayload,
    AdminDeactivatePayload,
    AdminEmailUpdatePayload,
    AdminPasswordResetPayload,
    AdminQuotaPayload,
)
from ogp_web.services.auth_service import AuthError, AuthUser, require_admin_user
from ogp_web.storage.admin_metrics_store import AdminMetricsStore
from ogp_web.storage.exam_answers_store import ExamAnswersStore
from ogp_web.storage.user_store import UserStore
from ogp_web.web import page_context, templates


router = APIRouter(tags=["admin"])
_PERFORMANCE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_PERFORMANCE_CACHE_TTL_SECONDS = 10
_PERFORMANCE_CACHE_LOCK = threading.Lock()
_ADMIN_TASKS: dict[str, dict[str, Any]] = {}
_ADMIN_TASKS_LOCK = threading.Lock()
_ADMIN_TASKS_PATH = Path(__file__).resolve().parents[3] / "web" / "data" / "admin_tasks.json"


def _cache_key(*, window_minutes: int, top_endpoints: int) -> str:
    return f"{window_minutes}:{top_endpoints}"


def _load_cached_performance_payload(cache_key: str) -> dict[str, Any] | None:
    with _PERFORMANCE_CACHE_LOCK:
        now = monotonic()
        cached = _PERFORMANCE_CACHE.get(cache_key)
        if not cached:
            return None
        cached_at, payload = cached
        if now - cached_at > _PERFORMANCE_CACHE_TTL_SECONDS:
            _PERFORMANCE_CACHE.pop(cache_key, None)
            return None
        payload["cached"] = True
        return deepcopy(payload)


def _store_performance_payload(cache_key: str, payload: dict[str, Any]) -> None:
    with _PERFORMANCE_CACHE_LOCK:
        _PERFORMANCE_CACHE[cache_key] = (monotonic(), deepcopy(payload))


def _save_admin_tasks_to_disk() -> None:
    try:
        _ADMIN_TASKS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _ADMIN_TASKS_PATH.write_text(
            json.dumps(_ADMIN_TASKS, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def _load_admin_tasks_from_disk() -> None:
    try:
        raw = _ADMIN_TASKS_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return
    except Exception:
        return
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return
    if isinstance(parsed, dict):
        _ADMIN_TASKS.clear()
        for key, value in parsed.items():
            if isinstance(value, dict):
                _ADMIN_TASKS[str(key)] = value


def _put_admin_task(task: dict[str, Any]) -> None:
    with _ADMIN_TASKS_LOCK:
        _ADMIN_TASKS[str(task["task_id"])] = deepcopy(task)
        _save_admin_tasks_to_disk()


def _patch_admin_task(task_id: str, **changes: Any) -> None:
    with _ADMIN_TASKS_LOCK:
        current = _ADMIN_TASKS.get(task_id)
        if not current:
            return
        current.update(changes)
        _ADMIN_TASKS[task_id] = current
        _save_admin_tasks_to_disk()


def _load_admin_task(task_id: str) -> dict[str, Any] | None:
    with _ADMIN_TASKS_LOCK:
        if task_id not in _ADMIN_TASKS:
            _load_admin_tasks_from_disk()
        item = _ADMIN_TASKS.get(task_id)
        return deepcopy(item) if item else None


_load_admin_tasks_from_disk()


def _apply_bulk_action(
    *,
    payload: AdminBulkActionPayload,
    user: AuthUser,
    metrics_store: AdminMetricsStore,
    user_store: UserStore,
    task_id: str | None = None,
) -> dict[str, Any]:
    action = str(payload.action or "").strip().lower()
    if action == "set_daily_quota" and payload.daily_limit is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=["Для set_daily_quota обязательно поле daily_limit."])
    usernames = [str(item or "").strip().lower() for item in payload.usernames if str(item or "").strip()]
    if not usernames:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=["Не переданы пользователи для массовой операции."])

    results: list[dict[str, Any]] = []
    success_count = 0
    for index, username in enumerate(usernames, start=1):
        try:
            if action == "verify_email":
                user_store.admin_mark_email_verified(username)
                event_type = "admin_verify_email"
                meta: dict[str, Any] = {"target_username": username, "bulk": True}
                path = f"/api/admin/users/{username}/verify-email"
            elif action == "block":
                user_store.admin_set_access_blocked(username, payload.reason)
                event_type = "admin_block_user"
                meta = {"target_username": username, "reason": payload.reason, "bulk": True}
                path = f"/api/admin/users/{username}/block"
            elif action == "unblock":
                user_store.admin_clear_access_blocked(username)
                event_type = "admin_unblock_user"
                meta = {"target_username": username, "bulk": True}
                path = f"/api/admin/users/{username}/unblock"
            elif action == "grant_tester":
                user_store.admin_set_tester_status(username, True)
                event_type = "admin_grant_tester"
                meta = {"target_username": username, "bulk": True}
                path = f"/api/admin/users/{username}/grant-tester"
            elif action == "revoke_tester":
                user_store.admin_set_tester_status(username, False)
                event_type = "admin_revoke_tester"
                meta = {"target_username": username, "bulk": True}
                path = f"/api/admin/users/{username}/revoke-tester"
            elif action == "grant_gka":
                user_store.admin_set_gka_status(username, True)
                event_type = "admin_grant_gka"
                meta = {"target_username": username, "bulk": True}
                path = f"/api/admin/users/{username}/grant-gka"
            elif action == "revoke_gka":
                user_store.admin_set_gka_status(username, False)
                event_type = "admin_revoke_gka"
                meta = {"target_username": username, "bulk": True}
                path = f"/api/admin/users/{username}/revoke-gka"
            elif action == "deactivate":
                user_store.admin_deactivate_user(username, payload.reason)
                event_type = "admin_deactivate_user"
                meta = {"target_username": username, "reason": payload.reason, "bulk": True}
                path = f"/api/admin/users/{username}/deactivate"
            elif action == "reactivate":
                user_store.admin_reactivate_user(username)
                event_type = "admin_reactivate_user"
                meta = {"target_username": username, "bulk": True}
                path = f"/api/admin/users/{username}/reactivate"
            elif action == "set_daily_quota":
                safe_limit = int(payload.daily_limit or 0)
                user_store.admin_set_daily_quota(username, safe_limit)
                event_type = "admin_set_daily_quota"
                meta = {"target_username": username, "daily_limit": safe_limit, "bulk": True}
                path = f"/api/admin/users/{username}/daily-quota"
            else:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[f"Неизвестное bulk-действие: {action}."])
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
            results.append({"username": username, "ok": True})
        except Exception as exc:  # noqa: BLE001
            results.append({"username": username, "ok": False, "error": str(exc)})
        if task_id:
            _patch_admin_task(task_id, progress={"done": index, "total": len(usernames)})

    return {
        "action": action,
        "total": len(usernames),
        "success_count": success_count,
        "failed_count": len(usernames) - success_count,
        "results": results,
    }


def _admin_template_payload(request: Request, user: AuthUser, *, admin_focus: str) -> dict[str, Any]:
    user_store = request.app.state.user_store
    server_config = get_server_config(user_store.get_server_code(user.username))
    permissions = build_permission_set(user_store, user.username, server_config)
    return page_context(
        username=user.username,
        nav_active="admin",
        is_admin=permissions.is_admin,
        show_test_pages=permissions.can_access_exam_import,
        show_tester_pages=permissions.can_access_court_claims,
        page_nav_items=[
            {"key": item.key, "label": item.label, "href": item.href}
            for item in server_config.page_nav_items
            if permissions.allows(item.permission)
        ],
        server_code=server_config.code,
        server_name=server_config.name,
        app_title=server_config.app_title,
        admin_focus=admin_focus,
    )


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, user: AuthUser = Depends(require_admin_user)):
    return templates.TemplateResponse(
        request,
        "admin.html",
        _admin_template_payload(request, user, admin_focus="dashboard"),
    )


@router.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard_page(request: Request, user: AuthUser = Depends(require_admin_user)):
    return templates.TemplateResponse(
        request,
        "admin.html",
        _admin_template_payload(request, user, admin_focus="dashboard"),
    )


@router.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(request: Request, user: AuthUser = Depends(require_admin_user)):
    return templates.TemplateResponse(
        request,
        "admin.html",
        _admin_template_payload(request, user, admin_focus="users"),
    )


@router.get("/api/admin/dashboard")
async def admin_dashboard_data(
    user: AuthUser = Depends(require_admin_user),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    exam_store: ExamAnswersStore = Depends(get_exam_answers_store),
    user_store: UserStore = Depends(get_user_store),
):
    _ = user
    users = user_store.list_users()
    overview = metrics_store.get_overview(users=users)
    performance = metrics_store.get_performance_overview(window_minutes=30, top_endpoints=5)
    exam_import = metrics_store.get_exam_import_summary(pending_scores=exam_store.count_entries_needing_scores())
    totals = overview.get("totals", {})
    users_with_metrics = overview.get("users", [])
    blocked_count = sum(1 for row in users_with_metrics if row.get("access_blocked"))
    unverified_count = sum(1 for row in users_with_metrics if not row.get("email_verified"))

    kpis = [
        {
            "id": "users_total",
            "label": "Всего аккаунтов",
            "value": int(totals.get("users_total") or 0),
            "period": "за все время",
            "status": "neutral",
        },
        {
            "id": "events_last_24h",
            "label": "Активность за сутки",
            "value": int(totals.get("events_last_24h") or 0),
            "period": "24 часа",
            "status": "neutral",
        },
        {
            "id": "complaints_total",
            "label": "Подготовлено жалоб",
            "value": int(totals.get("complaints_total") or 0),
            "period": "за все время",
            "status": "success-soft",
        },
        {
            "id": "rehabs_total",
            "label": "Подготовлено реабилитаций",
            "value": int(totals.get("rehabs_total") or 0),
            "period": "за все время",
            "status": "success-soft",
        },
        {
            "id": "pending_scores",
            "label": "Ожидают проверки экзамена",
            "value": int(exam_import.get("pending_scores") or 0),
            "period": "текущее состояние",
            "status": "warn",
        },
        {
            "id": "error_rate",
            "label": "Доля ошибок API",
            "value": f"{round(float(performance.get('error_rate') or 0) * 100, 2)}%",
            "period": "30 минут",
            "status": "danger" if float(performance.get("error_rate") or 0) >= 0.05 else "neutral",
        },
        {
            "id": "blocked_accounts",
            "label": "Заблокированные аккаунты",
            "value": blocked_count,
            "period": "текущее состояние",
            "status": "danger" if blocked_count else "neutral",
        },
        {
            "id": "unverified_accounts",
            "label": "Неподтвержденные email",
            "value": unverified_count,
            "period": "текущее состояние",
            "status": "warn" if unverified_count else "neutral",
        },
    ]

    alerts: list[dict[str, Any]] = []
    if float(performance.get("error_rate") or 0) >= 0.05:
        alerts.append(
            {
                "severity": "danger",
                "title": "Высокая доля ошибок API",
                "description": "Проверьте журнал событий и проблемные endpoint'ы.",
                "action_url": "/admin#admin-section-events",
            }
        )
    if int(exam_import.get("pending_scores") or 0) > 0:
        alerts.append(
            {
                "severity": "warn",
                "title": "Есть очередь проверки экзаменов",
                "description": "Запустите проверку импортированных строк.",
                "action_url": "/exam-import-test",
            }
        )
    if blocked_count:
        alerts.append(
            {
                "severity": "warn",
                "title": "Есть заблокированные аккаунты",
                "description": "Проверьте причины блокировки и актуальность ограничений.",
                "action_url": "/admin#admin-section-users",
            }
        )

    quick_links = [
        {"label": "Пользователи", "url": "/admin#admin-section-users"},
        {"label": "Импорт экзаменов", "url": "/admin#admin-section-import"},
        {"label": "События и ошибки", "url": "/admin#admin-section-events"},
        {"label": "Профиль", "url": "/profile"},
    ]

    return {
        "kpis": kpis,
        "alerts": alerts,
        "quick_links": quick_links,
        "recent_events": overview.get("recent_events", [])[:10],
        "top_endpoints": performance.get("endpoint_overview", []),
        "generated_at": performance.get("generated_at"),
    }


@router.get("/api/admin/users")
async def admin_users_data(
    user: AuthUser = Depends(require_admin_user),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
    search: str = "",
    blocked_only: bool = False,
    tester_only: bool = False,
    gka_only: bool = False,
    unverified_only: bool = False,
    user_sort: str = "complaints",
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    _ = user
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


@router.get("/api/admin/users/{username}")
async def admin_user_details(
    username: str,
    user: AuthUser = Depends(require_admin_user),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    _ = user
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

    effective_permissions = {
        "can_access_admin": bool(target.get("is_admin")),
        "can_access_exam_import": bool(target.get("is_admin") or target.get("is_tester")),
        "can_access_test_pages": bool(target.get("is_tester")),
        "is_gka": bool(target.get("is_gka")),
        "is_tester": bool(target.get("is_tester")),
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


@router.get("/api/admin/role-history")
async def admin_role_history(
    user: AuthUser = Depends(require_admin_user),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
    limit: int = Query(default=100, ge=1, le=1000),
):
    _ = user
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


@router.get("/api/admin/overview")
async def admin_overview(
    user: AuthUser = Depends(require_admin_user),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    exam_store: ExamAnswersStore = Depends(get_exam_answers_store),
    user_store: UserStore = Depends(get_user_store),
    search: str = "",
    blocked_only: bool = False,
    tester_only: bool = False,
    gka_only: bool = False,
    unverified_only: bool = False,
    event_search: str = "",
    event_type: str = "",
    failed_events_only: bool = False,
    users_limit: int = 0,
    user_sort: str = "complaints",
):
    _ = user
    safe_user_limit = None
    try:
        safe_user_limit = int(users_limit)
        if safe_user_limit <= 0:
            safe_user_limit = None
    except (TypeError, ValueError):
        safe_user_limit = None
    payload = metrics_store.get_overview(
        users=user_store.list_users(limit=safe_user_limit),
        search=search,
        blocked_only=blocked_only,
        tester_only=tester_only,
        gka_only=gka_only,
        unverified_only=unverified_only,
        event_search=event_search,
        event_type=event_type,
        failed_events_only=failed_events_only,
        user_sort=user_sort,
    )
    payload["exam_import"] = metrics_store.get_exam_import_summary(
        pending_scores=exam_store.count_entries_needing_scores()
    )
    return payload


@router.get("/api/admin/performance")
async def admin_performance(
    user: AuthUser = Depends(require_admin_user),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    window_minutes: int = 15,
    top_endpoints: int = 10,
):
    _ = user
    safe_window = max(1, min(int(window_minutes or 1), 60 * 24))
    safe_endpoints = max(1, min(int(top_endpoints or 10), 50))
    cache_key = _cache_key(window_minutes=safe_window, top_endpoints=safe_endpoints)
    cached_payload = _load_cached_performance_payload(cache_key)
    if cached_payload is not None:
        return cached_payload

    payload = metrics_store.get_performance_overview(
        window_minutes=safe_window,
        top_endpoints=safe_endpoints,
    )
    payload["window_minutes"] = safe_window
    payload["top_endpoints_limit"] = safe_endpoints
    payload["snapshot_at"] = datetime.now(timezone.utc).isoformat()
    payload["cached"] = False
    _store_performance_payload(cache_key, payload)
    return payload


@router.get("/api/admin/users.csv")
async def admin_users_csv(
    user: AuthUser = Depends(require_admin_user),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
    search: str = "",
    blocked_only: bool = False,
    tester_only: bool = False,
    gka_only: bool = False,
    unverified_only: bool = False,
    users_limit: int = 0,
    user_sort: str = "complaints",
) -> Response:
    _ = user
    safe_user_limit = None
    try:
        safe_user_limit = int(users_limit)
        if safe_user_limit <= 0:
            safe_user_limit = None
    except (TypeError, ValueError):
        safe_user_limit = None
    content = metrics_store.export_users_csv(
        users=user_store.list_users(limit=safe_user_limit),
        search=search,
        blocked_only=blocked_only,
        tester_only=tester_only,
        gka_only=gka_only,
        unverified_only=unverified_only,
        user_sort=user_sort,
    )
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="admin-users.csv"'},
    )


@router.get("/api/admin/events.csv")
async def admin_events_csv(
    user: AuthUser = Depends(require_admin_user),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    event_search: str = "",
    event_type: str = "",
    failed_events_only: bool = False,
) -> Response:
    _ = user
    content = metrics_store.export_events_csv(
        event_search=event_search,
        event_type=event_type,
        failed_events_only=failed_events_only,
    )
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="admin-events.csv"'},
    )


@router.post("/api/admin/users/{username}/verify-email")
async def admin_verify_email(
    username: str,
    user: AuthUser = Depends(require_admin_user),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = user_store.admin_mark_email_verified(username)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_verify_email",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/verify-email",
        method="POST",
        status_code=200,
        meta={"target_username": username},
    )
    return {"ok": True, "user": result}


@router.post("/api/admin/users/{username}/block")
async def admin_block_user(
    username: str,
    payload: AdminBlockPayload,
    user: AuthUser = Depends(require_admin_user),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = user_store.admin_set_access_blocked(username, payload.reason)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_block_user",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/block",
        method="POST",
        status_code=200,
        meta={"target_username": username, "reason": payload.reason},
    )
    return {"ok": True, "user": result}


@router.post("/api/admin/users/{username}/unblock")
async def admin_unblock_user(
    username: str,
    user: AuthUser = Depends(require_admin_user),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = user_store.admin_clear_access_blocked(username)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_unblock_user",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/unblock",
        method="POST",
        status_code=200,
        meta={"target_username": username},
    )
    return {"ok": True, "user": result}


@router.post("/api/admin/users/{username}/grant-tester")
async def admin_grant_tester(
    username: str,
    user: AuthUser = Depends(require_admin_user),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = user_store.admin_set_tester_status(username, True)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_grant_tester",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/grant-tester",
        method="POST",
        status_code=200,
        meta={"target_username": username},
    )
    return {"ok": True, "user": result}


@router.post("/api/admin/users/{username}/revoke-tester")
async def admin_revoke_tester(
    username: str,
    user: AuthUser = Depends(require_admin_user),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = user_store.admin_set_tester_status(username, False)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_revoke_tester",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/revoke-tester",
        method="POST",
        status_code=200,
        meta={"target_username": username},
    )
    return {"ok": True, "user": result}


@router.post("/api/admin/users/{username}/grant-gka")
async def admin_grant_gka(
    username: str,
    user: AuthUser = Depends(require_admin_user),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = user_store.admin_set_gka_status(username, True)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_grant_gka",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/grant-gka",
        method="POST",
        status_code=200,
        meta={"target_username": username},
    )
    return {"ok": True, "user": result}


@router.post("/api/admin/users/{username}/revoke-gka")
async def admin_revoke_gka(
    username: str,
    user: AuthUser = Depends(require_admin_user),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = user_store.admin_set_gka_status(username, False)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_revoke_gka",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/revoke-gka",
        method="POST",
        status_code=200,
        meta={"target_username": username},
    )
    return {"ok": True, "user": result}


@router.post("/api/admin/users/{username}/email")
async def admin_update_email(
    username: str,
    payload: AdminEmailUpdatePayload,
    user: AuthUser = Depends(require_admin_user),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = user_store.admin_update_email(username, payload.email)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_update_email",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/email",
        method="POST",
        status_code=200,
        meta={"target_username": username, "email": payload.email},
    )
    return {"ok": True, "user": result}


@router.post("/api/admin/users/{username}/reset-password")
async def admin_reset_password(
    username: str,
    payload: AdminPasswordResetPayload,
    user: AuthUser = Depends(require_admin_user),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = user_store.admin_reset_password(username, payload.password)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_reset_password",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/reset-password",
        method="POST",
        status_code=200,
        meta={"target_username": username},
    )
    return {"ok": True, "user": result}


@router.post("/api/admin/users/{username}/deactivate")
async def admin_deactivate_user(
    username: str,
    payload: AdminDeactivatePayload,
    user: AuthUser = Depends(require_admin_user),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = user_store.admin_deactivate_user(username, payload.reason)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_deactivate_user",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/deactivate",
        method="POST",
        status_code=200,
        meta={"target_username": username, "reason": payload.reason},
    )
    return {"ok": True, "user": result}


@router.post("/api/admin/users/{username}/reactivate")
async def admin_reactivate_user(
    username: str,
    user: AuthUser = Depends(require_admin_user),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = user_store.admin_reactivate_user(username)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_reactivate_user",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/reactivate",
        method="POST",
        status_code=200,
        meta={"target_username": username},
    )
    return {"ok": True, "user": result}


@router.post("/api/admin/users/{username}/daily-quota")
async def admin_set_daily_quota(
    username: str,
    payload: AdminQuotaPayload,
    user: AuthUser = Depends(require_admin_user),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    try:
        result = user_store.admin_set_daily_quota(username, payload.daily_limit)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    metrics_store.log_event(
        event_type="admin_set_daily_quota",
        username=user.username,
        server_code=user.server_code,
        path=f"/api/admin/users/{username}/daily-quota",
        method="POST",
        status_code=200,
        meta={"target_username": username, "daily_limit": payload.daily_limit},
    )
    return {"ok": True, "user": result}


@router.post("/api/admin/users/bulk-actions")
async def admin_bulk_actions(
    payload: AdminBulkActionPayload,
    user: AuthUser = Depends(require_admin_user),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
    user_store: UserStore = Depends(get_user_store),
):
    if payload.run_async:
        task_id = f"admin-bulk-{uuid.uuid4().hex}"
        created_at = datetime.now(timezone.utc).isoformat()
        _put_admin_task(
            {
                "task_id": task_id,
                "status": "queued",
                "created_at": created_at,
                "started_at": "",
                "finished_at": "",
                "progress": {"done": 0, "total": len(payload.usernames)},
                "result": None,
                "error": "",
            }
        )

        def _runner() -> None:
            _patch_admin_task(task_id, status="running", started_at=datetime.now(timezone.utc).isoformat())
            try:
                result = _apply_bulk_action(
                    payload=payload,
                    user=user,
                    metrics_store=metrics_store,
                    user_store=user_store,
                    task_id=task_id,
                )
                _patch_admin_task(
                    task_id,
                    status="finished",
                    finished_at=datetime.now(timezone.utc).isoformat(),
                    result=result,
                )
            except Exception as exc:  # noqa: BLE001
                _patch_admin_task(
                    task_id,
                    status="failed",
                    finished_at=datetime.now(timezone.utc).isoformat(),
                    error=str(exc),
                )

        threading.Thread(target=_runner, daemon=True).start()
        return {"ok": True, "task_id": task_id, "status": "queued"}

    result = _apply_bulk_action(payload=payload, user=user, metrics_store=metrics_store, user_store=user_store)
    return {"ok": True, "status": "finished", "result": result}


@router.get("/api/admin/tasks/{task_id}")
async def admin_task_status(task_id: str, _: AuthUser = Depends(require_admin_user)):
    task = _load_admin_task(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Задача не найдена."])
    return task

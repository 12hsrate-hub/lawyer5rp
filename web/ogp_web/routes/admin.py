from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, Response

from ogp_web.dependencies import get_admin_metrics_store, get_exam_answers_store, get_user_store
from ogp_web.server_config import build_permission_set, get_server_config
from ogp_web.schemas import AdminBlockPayload, AdminEmailUpdatePayload, AdminPasswordResetPayload
from ogp_web.services.auth_service import AuthError, AuthUser, require_admin_user
from ogp_web.storage.admin_metrics_store import AdminMetricsStore
from ogp_web.storage.exam_answers_store import ExamAnswersStore
from ogp_web.storage.user_store import UserStore
from ogp_web.web import page_context, templates


router = APIRouter(tags=["admin"])


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, user: AuthUser = Depends(require_admin_user)):
    user_store = request.app.state.user_store
    server_config = get_server_config(user_store.get_server_code(user.username))
    permissions = build_permission_set(user_store, user.username, server_config)
    return templates.TemplateResponse(
        request,
        "admin.html",
        page_context(
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
        ),
    )


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
    user_sort: str = "complaints",
):
    _ = user
    payload = metrics_store.get_overview(
        users=user_store.list_users(),
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
    user_sort: str = "complaints",
) -> Response:
    _ = user
    content = metrics_store.export_users_csv(
        users=user_store.list_users(),
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

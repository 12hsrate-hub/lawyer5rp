from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from ogp_web.db.factory import get_database_backend
from ogp_web.dependencies import get_exam_answers_store, get_user_store, requires_permission
from ogp_web.env import is_test_user
from ogp_web.server_config import PermissionSet, ServerConfig, build_permission_set, get_server_config, list_server_configs
from ogp_web.services.ai_service import get_default_law_qa_model
from ogp_web.services.auth_service import AuthError, AuthUser, get_current_user
from ogp_web.services.content_workflow_service import ContentWorkflowService
from ogp_web.services.law_admin_service import LawAdminService
from ogp_web.storage.exam_answers_store import ExamAnswersStore
from ogp_web.storage.content_workflow_repository import ContentWorkflowRepository
from ogp_web.storage.user_store import UserStore
from ogp_web.web import page_context, templates


router = APIRouter()


def _page_nav_items(server_config: ServerConfig, permissions: PermissionSet) -> list[dict[str, str]]:
    return [
        {"key": item.key, "label": item.label, "href": item.href}
        for item in server_config.page_nav_items
        if permissions.allows(item.permission)
    ]


def _complaint_nav_items(server_config: ServerConfig, permissions: PermissionSet) -> list[dict[str, str]]:
    return [
        {"key": item.key, "label": item.label, "href": item.href}
        for item in server_config.complaint_nav_items
        if permissions.allows(item.permission)
    ]


def _server_context(store: UserStore, username: str) -> tuple[ServerConfig, PermissionSet]:
    server_config = get_server_config(store.get_server_code(username))
    permissions = build_permission_set(store, username, server_config)
    return server_config, permissions


def _build_page_context(
    *,
    user: AuthUser,
    server_config: ServerConfig,
    permissions: PermissionSet,
    nav_active: str,
    **extra: object,
) -> dict[str, object]:
    return page_context(
        username=user.username,
        nav_active=nav_active,
        is_admin=permissions.is_admin,
        show_test_pages=permissions.can_access_exam_import,
        show_tester_pages=permissions.can_access_court_claims,
        page_nav_items=_page_nav_items(server_config, permissions),
        complaint_nav_items=_complaint_nav_items(server_config, permissions),
        complaint_bases=server_config.complaint_bases,
        evidence_fields=server_config.evidence_fields,
        complaint_forum_url=server_config.complaint_forum_url,
        server_code=server_config.code,
        server_name=server_config.name,
        app_title=server_config.app_title,
        **extra,
    )


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user = get_current_user(request)
    target = "/complaint" if user else "/login"
    return RedirectResponse(url=target, status_code=status.HTTP_302_FOUND)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/complaint", status_code=status.HTTP_302_FOUND)
    default_server = getattr(request.app.state, "server_config", None)
    server_config = get_server_config(getattr(default_server, "code", "blackberry"))
    return templates.TemplateResponse(
        request,
        "login.html",
        page_context(
            server_code=server_config.code,
            server_name=server_config.name,
            app_title=server_config.app_title,
        ),
    )


@router.get("/verify-email", response_class=HTMLResponse)
async def verify_email_page(
    request: Request,
    token: str = "",
    store: UserStore = Depends(get_user_store),
):
    success = False
    message = "Ссылка для подтверждения email недействительна."
    username = ""
    if token:
        try:
            user = store.confirm_email(token)
            success = True
            username = user.username
            message = "Email подтвержден. Теперь можно войти в аккаунт."
        except AuthError as exc:
            message = str(exc)
    server_code = (
        store.get_server_code(username)
        if username
        else getattr(request.app.state.server_config, "code", "blackberry")
    )
    server_config = get_server_config(server_code)
    return templates.TemplateResponse(
        request,
        "verify_email.html",
        page_context(
            verification_success=success,
            verification_message=message,
            username=username,
            server_code=server_config.code,
            server_name=server_config.name,
            app_title=server_config.app_title,
        ),
    )


@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request, token: str = ""):
    server_config = get_server_config(getattr(request.app.state.server_config, "code", "blackberry"))
    return templates.TemplateResponse(
        request,
        "reset_password.html",
        page_context(
            reset_token=token,
            server_code=server_config.code,
            server_name=server_config.name,
            app_title=server_config.app_title,
        ),
    )


@router.get("/complaint", response_class=HTMLResponse)
async def complaint_page(
    request: Request,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
):
    server_config, permissions = _server_context(store, user.username)
    return templates.TemplateResponse(
        request,
        "complaint.html",
        _build_page_context(
            user=user,
            server_config=server_config,
            permissions=permissions,
            nav_active="complaint",
            complaint_mode="default",
            preset_payload_json="",
        ),
    )


@router.get("/complaint-test", response_class=HTMLResponse)
async def complaint_test_page(
    request: Request,
    user: AuthUser = Depends(requires_permission("court_claims")),
    store: UserStore = Depends(get_user_store),
):
    server_config, permissions = _server_context(store, user.username)
    return templates.TemplateResponse(
        request,
        "complaint.html",
        _build_page_context(
            user=user,
            server_config=server_config,
            permissions=permissions,
            nav_active="complaint_test",
            complaint_mode="test",
            preset_payload_json=(
                json.dumps(server_config.complaint_test_preset, ensure_ascii=False)
                if is_test_user(user.username)
                else ""
            ),
        ),
    )


@router.get("/exam-import-test", response_class=HTMLResponse)
async def exam_import_page(
    request: Request,
    user: AuthUser = Depends(requires_permission("exam_import")),
    user_store: UserStore = Depends(get_user_store),
    store: ExamAnswersStore = Depends(get_exam_answers_store),
):
    server_config, permissions = _server_context(user_store, user.username)
    return templates.TemplateResponse(
        request,
        "exam_import.html",
        _build_page_context(
            user=user,
            server_config=server_config,
            permissions=permissions,
            nav_active="exam_import",
            exam_sheet_url=server_config.exam_sheet_url,
            exam_entries=store.list_entries(),
            exam_total_rows=store.count(),
        ),
    )


@router.get("/court-claim-test", response_class=HTMLResponse)
async def court_claim_test_page(
    request: Request,
    user: AuthUser = Depends(requires_permission("court_claims")),
    store: UserStore = Depends(get_user_store),
):
    server_config, permissions = _server_context(store, user.username)
    return templates.TemplateResponse(
        request,
        "court_claim_test.html",
        _build_page_context(
            user=user,
            server_config=server_config,
            permissions=permissions,
            nav_active="court_claim_test",
        ),
    )


@router.get("/law-qa-test", response_class=HTMLResponse)
async def law_qa_test_page(
    request: Request,
    user: AuthUser = Depends(requires_permission("court_claims")),
    store: UserStore = Depends(get_user_store),
):
    server_config, permissions = _server_context(store, user.username)
    law_sources = list(server_config.law_qa_sources)
    try:
        law_admin_service = LawAdminService(
            ContentWorkflowService(ContentWorkflowRepository(get_database_backend()), legacy_store=None)
        )
        law_sources_snapshot = law_admin_service.get_effective_sources(server_code=server_config.code)
        law_sources = list(law_sources_snapshot.source_urls)
    except Exception:
        # Allow law QA page rendering in tests/local runtimes without PostgreSQL.
        law_sources = list(server_config.law_qa_sources)
    return templates.TemplateResponse(
        request,
        "law_qa_test.html",
        _build_page_context(
            user=user,
            server_config=server_config,
            permissions=permissions,
            nav_active="law_qa_test",
            law_qa_servers=[
                {"code": item.code, "name": item.name}
                for item in list_server_configs()
                if item.law_qa_sources or item.law_qa_bundle_path
            ],
            law_qa_sources=law_sources,
            law_qa_default_model=get_default_law_qa_model(),
        ),
    )


@router.get("/rehab", response_class=HTMLResponse)
async def rehab_page(
    request: Request,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
):
    server_config, permissions = _server_context(store, user.username)
    return templates.TemplateResponse(
        request,
        "rehab.html",
        _build_page_context(
            user=user,
            server_config=server_config,
            permissions=permissions,
            nav_active="rehab",
        ),
    )


@router.get("/rehab-test", response_class=HTMLResponse)
async def rehab_test_redirect(user: AuthUser = Depends(requires_permission())):
    _ = user
    return RedirectResponse(url="/rehab", status_code=status.HTTP_302_FOUND)


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
):
    server_config, permissions = _server_context(store, user.username)
    return templates.TemplateResponse(
        request,
        "profile.html",
        _build_page_context(
            user=user,
            server_config=server_config,
            permissions=permissions,
            nav_active="profile",
        ),
    )

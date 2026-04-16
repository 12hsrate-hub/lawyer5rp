from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from ogp_web.dependencies import get_exam_answers_store, get_user_store, requires_permission
from ogp_web.env import is_test_user
from ogp_web.server_config import PermissionSet, ServerConfig, resolve_default_server_code
from ogp_web.services.auth_service import AuthError, AuthUser, get_current_user
from ogp_web.services.pages_runtime_service import (
    build_exam_import_page_data,
    build_law_qa_test_page_data,
)
from ogp_web.services.server_context_service import (
    extract_server_complaint_settings,
    extract_server_shell_context,
    resolve_server_config,
    resolve_user_server_context,
)
from ogp_web.storage.exam_answers_store import ExamAnswersStore
from ogp_web.storage.user_store import UserStore
from ogp_web.web import page_context, templates


router = APIRouter()


def _server_context(store: UserStore, username: str) -> tuple[ServerConfig, PermissionSet]:
    return resolve_user_server_context(store, username)


def _request_server_config(request: Request) -> ServerConfig:
    default_server = getattr(request.app.state, "server_config", None)
    return resolve_server_config(
        server_code=resolve_default_server_code(app_server_code=getattr(default_server, "code", "")),
    )


def _page_server_config(request: Request, store: UserStore, *, username: str = "") -> ServerConfig:
    if username:
        return resolve_server_config(server_code=store.get_server_code(username))
    return _request_server_config(request)


def _build_page_context(
    *,
    user: AuthUser,
    server_config: ServerConfig,
    permissions: PermissionSet,
    nav_active: str,
    **extra: object,
) -> dict[str, object]:
    shell_context = extract_server_shell_context(server_config, permissions)
    return page_context(
        username=user.username,
        nav_active=nav_active,
        is_admin=permissions.is_admin,
        show_test_pages=permissions.can_access_exam_import,
        show_tester_pages=permissions.can_access_court_claims,
        **shell_context,
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
    server_config = _request_server_config(request)
    return templates.TemplateResponse(
        request,
        "login.html",
        page_context(
            **extract_server_shell_context(server_config),
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
    server_config = _page_server_config(request, store, username=username)
    return templates.TemplateResponse(
        request,
        "verify_email.html",
        page_context(
            verification_success=success,
            verification_message=message,
            username=username,
            **extract_server_shell_context(server_config),
        ),
    )


@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request, token: str = ""):
    server_config = _request_server_config(request)
    return templates.TemplateResponse(
        request,
        "reset_password.html",
        page_context(
            reset_token=token,
            **extract_server_shell_context(server_config),
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
    complaint_settings = extract_server_complaint_settings(server_config)
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
                json.dumps(complaint_settings.complaint_test_preset, ensure_ascii=False)
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
            **build_exam_import_page_data(server_config=server_config, exam_store=store),
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
    return templates.TemplateResponse(
        request,
        "law_qa_test.html",
        _build_page_context(
            user=user,
            server_config=server_config,
            permissions=permissions,
            nav_active="law_qa_test",
            **build_law_qa_test_page_data(server_config=server_config),
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

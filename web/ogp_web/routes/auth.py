from __future__ import annotations

from functools import partial

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool

from ogp_web.dependencies import get_user_store
from ogp_web.rate_limit import RateLimitExceeded, auth_rate_limit
from ogp_web.schemas import AuthPayload, AuthResponse, EmailPayload, PasswordChangePayload, PasswordResetPayload
from ogp_web.services.auth_service import AuthError, clear_auth_cookie, require_user, set_auth_cookie
from ogp_web.services.email_service import build_public_base_url, send_password_reset_email, send_verification_email
from ogp_web.storage.user_store import UserStore


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


router = APIRouter(prefix="/api/auth", tags=["auth"])


async def _run_sync_io(func, /, *args, **kwargs):
    return await run_in_threadpool(partial(func, *args, **kwargs))


@router.get("/me", response_model=AuthResponse)
async def auth_me(user=Depends(require_user)) -> AuthResponse:
    return AuthResponse(username=user.username, server_code=user.server_code, message="Сессия активна.")


@router.post("/register", response_model=AuthResponse)
async def auth_register(
    request: Request,
    payload: AuthPayload,
    store: UserStore = Depends(get_user_store),
) -> AuthResponse:
    try:
        auth_rate_limit(_client_ip(request), "register", getattr(request.app.state, "rate_limiter", None))
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=[str(exc)]) from exc
    try:
        user, verification_token = await _run_sync_io(store.register, payload.username, payload.email, payload.password)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc

    base_url = build_public_base_url(str(request.base_url))
    verification_url = f"{base_url}/verify-email?token={verification_token}"
    delivery = await _run_sync_io(
        send_verification_email,
        recipient=user.email,
        username=user.username,
        verification_url=verification_url,
    )

    message = "Регистрация почти завершена. Подтвердите email по ссылке из письма."
    preview_url = None
    if not delivery.sent:
        message = "Регистрация создана. SMTP не настроен, поэтому ссылка подтверждения показана в ответе."
        preview_url = verification_url

    return AuthResponse(
        username=user.username,
        server_code=user.server_code,
        message=message,
        requires_email_verification=True,
        verification_url=preview_url,
    )


@router.post("/login", response_model=AuthResponse)
async def auth_login(
    request: Request,
    payload: AuthPayload,
    response: Response,
    store: UserStore = Depends(get_user_store),
) -> AuthResponse:
    try:
        auth_rate_limit(_client_ip(request), "login", getattr(request.app.state, "rate_limiter", None))
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=[str(exc)]) from exc
    try:
        user = await _run_sync_io(store.authenticate, payload.username, payload.password)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    set_auth_cookie(response, user.username)
    return AuthResponse(username=user.username, server_code=user.server_code, message="Вход выполнен успешно.")


@router.post("/resend-verification", response_model=AuthResponse)
async def auth_resend_verification(
    request: Request,
    payload: EmailPayload,
    store: UserStore = Depends(get_user_store),
) -> AuthResponse:
    try:
        user, verification_token = await _run_sync_io(store.issue_email_verification_token, payload.email)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc

    base_url = build_public_base_url(str(request.base_url))
    verification_url = f"{base_url}/verify-email?token={verification_token}"
    delivery = await _run_sync_io(
        send_verification_email,
        recipient=user.email,
        username=user.username,
        verification_url=verification_url,
    )

    message = "Письмо с подтверждением отправлено повторно."
    preview_url = None
    if not delivery.sent:
        message = "SMTP не настроен, поэтому ссылка подтверждения показана в ответе."
        preview_url = verification_url

    return AuthResponse(
        username=user.username,
        server_code=user.server_code,
        message=message,
        requires_email_verification=True,
        verification_url=preview_url,
    )


@router.post("/logout")
async def auth_logout(response: Response) -> dict[str, bool]:
    clear_auth_cookie(response)
    return {"ok": True}


@router.post("/forgot-password", response_model=AuthResponse)
async def auth_forgot_password(
    request: Request,
    payload: EmailPayload,
    store: UserStore = Depends(get_user_store),
) -> AuthResponse:
    try:
        auth_rate_limit(_client_ip(request), "forgot-password", getattr(request.app.state, "rate_limiter", None))
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=[str(exc)]) from exc
    try:
        user, reset_token = await _run_sync_io(store.issue_password_reset_token, payload.email)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc

    base_url = build_public_base_url(str(request.base_url))
    reset_url = f"{base_url}/reset-password?token={reset_token}"
    delivery = await _run_sync_io(
        send_password_reset_email,
        recipient=user.email,
        username=user.username,
        reset_url=reset_url,
    )

    message = "Инструкция по смене пароля отправлена на email."
    preview_url = None
    if not delivery.sent:
        message = "SMTP не настроен, поэтому ссылка для сброса показана в ответе."
        preview_url = reset_url

    return AuthResponse(
        username=user.username,
        server_code=user.server_code,
        message=message,
        verification_url=preview_url,
    )


@router.post("/reset-password", response_model=AuthResponse)
async def auth_reset_password(
    payload: PasswordResetPayload,
    response: Response,
    store: UserStore = Depends(get_user_store),
) -> AuthResponse:
    try:
        user = await _run_sync_io(store.reset_password, payload.token, payload.password)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    set_auth_cookie(response, user.username)
    return AuthResponse(username=user.username, server_code=user.server_code, message="Пароль обновлён. Вы вошли в систему.")


@router.post("/change-password", response_model=AuthResponse)
async def auth_change_password(
    payload: PasswordChangePayload,
    response: Response,
    user=Depends(require_user),
    store: UserStore = Depends(get_user_store),
) -> AuthResponse:
    try:
        updated_user = await _run_sync_io(store.change_password, user.username, payload.current_password, payload.new_password)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=[str(exc)]) from exc
    set_auth_cookie(response, updated_user.username)
    return AuthResponse(username=updated_user.username, server_code=updated_user.server_code, message="Пароль обновлён.")

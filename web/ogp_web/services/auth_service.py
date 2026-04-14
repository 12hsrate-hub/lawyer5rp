from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException, Request, Response, status


SESSION_COOKIE_NAME = "ogp_web_session"
SESSION_TTL_DAYS = 14
PASSWORD_SALT_BYTES = 16
PBKDF2_ITERATIONS = 200_000
EMAIL_TOKEN_BYTES = 32
EMAIL_RE = re.compile(r"^[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}$", re.IGNORECASE)
WEB_DIR = Path(__file__).resolve().parents[2]
SESSION_SECRET_FILE = WEB_DIR / "data" / "secrets" / "web_session_secret.txt"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _load_secret_key() -> bytes:
    raw = os.getenv("OGP_WEB_SECRET", "").strip()
    if raw:
        return raw.encode("utf-8")

    try:
        persisted = SESSION_SECRET_FILE.read_text(encoding="utf-8").strip()
        if persisted:
            return persisted.encode("utf-8")
    except FileNotFoundError:
        pass
    except OSError:
        return b""

    generated = secrets.token_urlsafe(48)
    try:
        SESSION_SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
        SESSION_SECRET_FILE.write_text(generated, encoding="utf-8")
        return generated.encode("utf-8")
    except OSError:
        return b""


SECRET_KEY = _load_secret_key()


@dataclass
class AuthUser:
    username: str
    email: str = ""
    server_code: str = ""


class AuthError(ValueError):
    pass


def _normalize_username(username: str) -> str:
    value = (username or "").strip().lower()
    if len(value) < 3:
        raise AuthError("Логин должен быть не короче 3 символов.")
    if len(value) > 50:
        raise AuthError("Логин слишком длинный.")
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789._-")
    if any(ch not in allowed for ch in value):
        raise AuthError("Логин может содержать только латиницу, цифры, '.', '_' и '-'.")
    return value


def _normalize_email(email: str) -> str:
    value = (email or "").strip().lower()
    if not value:
        raise AuthError("Укажите email.")
    if len(value) > 254:
        raise AuthError("Email слишком длинный.")
    if not EMAIL_RE.fullmatch(value):
        raise AuthError("Укажите корректный email.")
    return value


def _validate_password(password: str) -> str:
    value = password or ""
    if len(value) < 10:
        raise AuthError("Пароль должен быть не короче 10 символов.")
    if len(value) > 256:
        raise AuthError("Пароль слишком длинный.")
    if value.strip() != value:
        raise AuthError("Пароль не должен начинаться или заканчиваться пробелом.")
    checks = [
        (re.search(r"[a-z]", value), "Добавьте хотя бы одну строчную латинскую букву."),
        (re.search(r"[A-Z]", value), "Добавьте хотя бы одну заглавную латинскую букву."),
        (re.search(r"\d", value), "Добавьте хотя бы одну цифру."),
        (re.search(r"[^A-Za-z0-9]", value), "Добавьте хотя бы один специальный символ."),
    ]
    for passed, message in checks:
        if not passed:
            raise AuthError(message)
    return value


def _hash_password(password: str, salt: bytes) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return base64.b64encode(digest).decode("ascii")


def _encode_salt(salt: bytes) -> str:
    return base64.b64encode(salt).decode("ascii")


def _decode_salt(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"))


def _hash_email_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_email_verification_token() -> str:
    return secrets.token_urlsafe(EMAIL_TOKEN_BYTES)


def _build_user_record(password: str, email: str, verification_token: str) -> dict[str, object]:
    from ogp_web.storage.user_store import REPRESENTATIVE_PROFILE_DEFAULTS

    salt = secrets.token_bytes(PASSWORD_SALT_BYTES)
    return {
        "email": email,
        "salt": _encode_salt(salt),
        "password_hash": _hash_password(password, salt),
        "created_at": _utc_now().isoformat(),
        "email_verification_token_hash": _hash_email_token(verification_token),
        "email_verification_sent_at": _utc_now().isoformat(),
        "representative_profile": REPRESENTATIVE_PROFILE_DEFAULTS.copy(),
    }


def verify_password(password: str, salt_value: str, expected_hash: str) -> bool:
    try:
        salt = _decode_salt(salt_value)
    except (binascii.Error, ValueError):
        return False
    actual_hash = _hash_password(password, salt)
    return hmac.compare_digest(actual_hash, expected_hash)


def _get_secret_key() -> bytes:
    global SECRET_KEY
    if not SECRET_KEY:
        SECRET_KEY = _load_secret_key()
    if not SECRET_KEY:
        raise RuntimeError("OGP_WEB_SECRET не задан в переменных окружения.")
    return SECRET_KEY


def _get_secret_key() -> bytes:
    global SECRET_KEY
    if not SECRET_KEY:
        SECRET_KEY = _load_secret_key()
    if not SECRET_KEY:
        # Final fallback keeps the app bootable even if the data dir is not writable.
        SECRET_KEY = secrets.token_urlsafe(48).encode("utf-8")
    return SECRET_KEY


def _make_signature(payload: str) -> str:
    return hmac.new(_get_secret_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def create_session_token(username: str) -> str:
    expires_at = (_utc_now() + timedelta(days=SESSION_TTL_DAYS)).isoformat()
    payload = f"{username}|{expires_at}"
    signature = _make_signature(payload)
    raw = f"{payload}|{signature}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def parse_session_token(token: str) -> AuthUser | None:
    raw = (token or "").strip()
    if not raw:
        return None
    try:
        decoded = base64.urlsafe_b64decode(raw.encode("ascii")).decode("utf-8")
        username, expires_at, signature = decoded.split("|", 2)
    except Exception:
        return None

    try:
        expected = _make_signature(f"{username}|{expires_at}")
    except RuntimeError:
        return None
    if not hmac.compare_digest(signature, expected):
        return None

    try:
        expires_dt = datetime.fromisoformat(expires_at)
    except ValueError:
        return None

    if expires_dt.tzinfo is None:
        expires_dt = expires_dt.replace(tzinfo=timezone.utc)
    if expires_dt <= _utc_now():
        return None

    return AuthUser(username=username)


def set_auth_cookie(response: Response, username: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=create_session_token(username),
        httponly=True,
        samesite="lax",
        secure=True,
        max_age=14 * 24 * 60 * 60,
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")


def get_current_user(request: Request) -> AuthUser | None:
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    return parse_session_token(token)


def require_user(request: Request) -> AuthUser:
    user = get_current_user(request)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=["Требуется вход в систему."])
    store = getattr(request.app.state, "user_store", None)
    if store is not None:
        try:
            user = store.get_auth_user(user.username)
            if store.is_access_blocked(user.username):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=["Доступ к аккаунту заблокирован администратором."],
                )
        except AuthError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=[str(exc)],
            ) from exc
        except HTTPException:
            raise
        except Exception:
            pass
    return user


def is_admin_user(username: str) -> bool:
    normalized = (username or "").strip().lower()
    configured_many = os.getenv("OGP_WEB_ADMIN_USERNAMES", "").strip()
    if configured_many:
        allowed = {
            item.strip().lower()
            for item in configured_many.split(",")
            if item.strip()
        }
        if allowed:
            return normalized in allowed
    configured = os.getenv("OGP_WEB_ADMIN_USERNAME", "").strip().lower()
    if configured:
        return normalized == configured
    return normalized == "12345"


def require_admin_user(request: Request) -> AuthUser:
    user = require_user(request)
    if not is_admin_user(user.username):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=["Доступ разрешён только администратору."])
    return user

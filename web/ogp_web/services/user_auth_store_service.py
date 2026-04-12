from __future__ import annotations

import json
from contextlib import closing
from typing import TYPE_CHECKING

from ogp_web.db.errors import IntegrityConflictError
from ogp_web.services.auth_service import (
    AuthError,
    AuthUser,
    _build_user_record,
    _hash_email_token,
    _normalize_email,
    _normalize_username,
    _validate_password,
    create_email_verification_token,
    verify_password,
)
from ogp_web.server_config.registry import DEFAULT_SERVER_CODE

if TYPE_CHECKING:
    from ogp_web.storage.user_store import UserStore


def register_user(store: UserStore, username: str, email: str, password: str) -> tuple[AuthUser, str]:
    normalized = _normalize_username(username)
    normalized_email = _normalize_email(email)
    valid_password = _validate_password(password)
    verification_token = create_email_verification_token()
    record = _build_user_record(valid_password, normalized_email, verification_token)
    try:
        with closing(store._connect()) as conn:
            conn.execute(
                """
                INSERT INTO users (
                    username,
                    email,
                    salt,
                    password_hash,
                    created_at,
                    email_verified_at,
                    email_verification_token_hash,
                    email_verification_sent_at,
                    password_reset_token_hash,
                    password_reset_sent_at,
                    access_blocked_at,
                    access_blocked_reason,
                    server_code,
                    is_tester,
                    representative_profile
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized,
                    record["email"],
                    record["salt"],
                    record["password_hash"],
                    record["created_at"],
                    None,
                    record["email_verification_token_hash"],
                    record["email_verification_sent_at"],
                    None,
                    None,
                    None,
                    None,
                    DEFAULT_SERVER_CODE,
                    0,
                    json.dumps(record["representative_profile"], ensure_ascii=False),
                ),
            )
            conn.commit()
    except IntegrityConflictError as exc:
        message = "Пользователь с таким логином уже существует."
        lowered = str(exc).lower()
        if "users.email" in lowered or "idx_users_email_unique" in lowered:
            message = "Пользователь с таким email уже существует."
        raise AuthError(message) from exc
    return AuthUser(username=normalized, email=normalized_email, server_code=DEFAULT_SERVER_CODE), verification_token


def authenticate_user(store: UserStore, username: str, password: str) -> AuthUser:
    normalized = (username or "").strip().lower()
    if "@" in normalized:
        query = "SELECT username, email, server_code, salt, password_hash, email_verified_at, access_blocked_at FROM users WHERE email = ?"
        params = (_normalize_email(normalized),)
    else:
        query = "SELECT username, email, server_code, salt, password_hash, email_verified_at, access_blocked_at FROM users WHERE username = ?"
        params = (_normalize_username(normalized),)

    valid_password = _validate_password(password)
    row = store._fetchone(query, params)
    if row is None:
        raise AuthError("Неверный логин/email или пароль.")
    if not verify_password(valid_password, str(row["salt"]), str(row["password_hash"])):
        raise AuthError("Неверный логин/email или пароль.")
    if str(row["access_blocked_at"] or "").strip():
        raise AuthError("Доступ к аккаунту заблокирован администратором.")
    if not str(row["email_verified_at"] or "").strip():
        raise AuthError("Сначала подтвердите email по ссылке из письма.")
    return store._auth_user_from_row(row)


def confirm_email(store: UserStore, token: str) -> AuthUser:
    raw_token = (token or "").strip()
    if not raw_token:
        raise AuthError("Ссылка подтверждения неполная.")
    token_hash = _hash_email_token(raw_token)
    with closing(store._connect()) as conn:
        row = conn.execute(
            """
            SELECT username, email, server_code
            FROM users
            WHERE email_verification_token_hash = ?
            """,
            (token_hash,),
        ).fetchone()
        if row is None:
            raise AuthError("Ссылка подтверждения недействительна или уже использована.")
        conn.execute(
            """
            UPDATE users
            SET email_verified_at = CURRENT_TIMESTAMP,
                email_verification_token_hash = NULL
            WHERE username = ?
            """,
            (str(row["username"]),),
        )
        conn.commit()
    return store._auth_user_from_row(row)


def issue_email_verification_token(store: UserStore, email: str) -> tuple[AuthUser, str]:
    normalized_email = _normalize_email(email)
    verification_token = create_email_verification_token()
    with closing(store._connect()) as conn:
        row = conn.execute(
            """
            SELECT username, email, server_code, email_verified_at
            FROM users
            WHERE email = ?
            """,
            (normalized_email,),
        ).fetchone()
        if row is None:
            raise AuthError("Пользователь с таким email не найден.")
        if str(row["email_verified_at"] or "").strip():
            raise AuthError("Этот email уже подтвержден.")
        conn.execute(
            """
            UPDATE users
            SET email_verification_token_hash = ?,
                email_verification_sent_at = CURRENT_TIMESTAMP
            WHERE email = ?
            """,
            (_hash_email_token(verification_token), normalized_email),
        )
        conn.commit()
    return store._auth_user_from_row(row), verification_token


def issue_password_reset_token(store: UserStore, email: str) -> tuple[AuthUser, str]:
    normalized_email = _normalize_email(email)
    reset_token = create_email_verification_token()
    with closing(store._connect()) as conn:
        row = conn.execute(
            """
            SELECT username, email, server_code, email_verified_at
            FROM users
            WHERE email = ?
            """,
            (normalized_email,),
        ).fetchone()
        if row is None:
            raise AuthError("Пользователь с таким email не найден.")
        if not str(row["email_verified_at"] or "").strip():
            raise AuthError("Сначала подтвердите email, а затем сбрасывайте пароль.")
        conn.execute(
            """
            UPDATE users
            SET password_reset_token_hash = ?,
                password_reset_sent_at = CURRENT_TIMESTAMP
            WHERE email = ?
            """,
            (_hash_email_token(reset_token), normalized_email),
        )
        conn.commit()
    return store._auth_user_from_row(row), reset_token


def reset_password(store: UserStore, token: str, new_password: str) -> AuthUser:
    raw_token = (token or "").strip()
    if not raw_token:
        raise AuthError("Ссылка сброса неполная.")
    valid_password = _validate_password(new_password)
    token_hash = _hash_email_token(raw_token)
    with closing(store._connect()) as conn:
        row = conn.execute(
            """
            SELECT username, email, server_code
            FROM users
            WHERE password_reset_token_hash = ?
            """,
            (token_hash,),
        ).fetchone()
        if row is None:
            raise AuthError("Ссылка сброса недействительна или уже использована.")
        record = _build_user_record(valid_password, str(row["email"] or ""), create_email_verification_token())
        conn.execute(
            """
            UPDATE users
            SET salt = ?,
                password_hash = ?,
                password_reset_token_hash = NULL,
                password_reset_sent_at = NULL
            WHERE username = ?
            """,
            (
                record["salt"],
                record["password_hash"],
                str(row["username"]),
            ),
        )
        conn.commit()
    return store._auth_user_from_row(row)


def change_password(store: UserStore, username: str, current_password: str, new_password: str) -> AuthUser:
    normalized = _normalize_username(username)
    valid_current_password = _validate_password(current_password)
    valid_new_password = _validate_password(new_password)
    row = store._fetch_user_by_username(normalized, "username, email, server_code, salt, password_hash")
    if row is None:
        raise AuthError("Пользователь не найден.")
    if not verify_password(valid_current_password, str(row["salt"]), str(row["password_hash"])):
        raise AuthError("Текущий пароль введен неверно.")
    if valid_current_password == valid_new_password:
        raise AuthError("Новый пароль должен отличаться от текущего.")
    record = _build_user_record(valid_new_password, str(row["email"] or ""), create_email_verification_token())
    store._execute(
        """
        UPDATE users
        SET salt = ?,
            password_hash = ?,
            password_reset_token_hash = NULL,
            password_reset_sent_at = NULL
        WHERE username = ?
        """,
        (
            record["salt"],
            record["password_hash"],
            normalized,
        ),
    )
    return store._auth_user_from_row(row)

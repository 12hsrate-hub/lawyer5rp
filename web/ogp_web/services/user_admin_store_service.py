from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Any

from ogp_web.db.errors import IntegrityConflictError
from ogp_web.services.auth_service import (
    AuthError,
    _build_user_record,
    _normalize_email,
    _normalize_username,
    _validate_password,
    create_email_verification_token,
)

if TYPE_CHECKING:
    from ogp_web.storage.user_store import UserStore


def list_users(store: UserStore) -> list[dict[str, Any]]:
    with store._connect() as conn:
        rows = conn.execute(
            """
            SELECT username, email, created_at, email_verified_at, access_blocked_at, access_blocked_reason, server_code, is_tester, is_gka
            FROM users
            ORDER BY created_at DESC, username ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def is_access_blocked(store: UserStore, username: str) -> bool:
    row = store._fetch_user_by_username(username, "access_blocked_at")
    if row is None:
        raise AuthError("Пользователь не найден.")
    return bool(str(row["access_blocked_at"] or "").strip())


def is_tester_user(store: UserStore, username: str, *, server_code: str | None = None) -> bool:
    row = store._fetch_user_by_username(username, "is_tester, server_code")
    if row is None:
        return False
    if server_code and str(row["server_code"] or "").strip().lower() != str(server_code).strip().lower():
        return False
    return bool(int(row["is_tester"] or 0))


def is_gka_user(store: UserStore, username: str, *, server_code: str | None = None) -> bool:
    row = store._fetch_user_by_username(username, "is_gka, server_code")
    if row is None:
        return False
    if server_code and str(row["server_code"] or "").strip().lower() != str(server_code).strip().lower():
        return False
    return bool(int(row["is_gka"] or 0))


def admin_mark_email_verified(store: UserStore, username: str) -> dict[str, Any]:
    normalized = _normalize_username(username)
    rowcount = store._execute(
        """
        UPDATE users
        SET email_verified_at = COALESCE(email_verified_at, CURRENT_TIMESTAMP),
            email_verification_token_hash = NULL
        WHERE username = ?
        """,
        (normalized,),
    )
    if rowcount <= 0:
        raise AuthError("Пользователь не найден.")
    row = store._fetch_user_by_username(
        normalized,
        "username, email, created_at, email_verified_at, access_blocked_at, access_blocked_reason, server_code",
    )
    return dict(row) if row else {}


def admin_set_access_blocked(store: UserStore, username: str, reason: str = "") -> dict[str, Any]:
    normalized = _normalize_username(username)
    rowcount = store._execute(
        """
        UPDATE users
        SET access_blocked_at = CURRENT_TIMESTAMP,
            access_blocked_reason = ?
        WHERE username = ?
        """,
        (str(reason or "").strip(), normalized),
    )
    if rowcount <= 0:
        raise AuthError("Пользователь не найден.")
    row = store._fetch_user_by_username(
        normalized,
        "username, email, created_at, email_verified_at, access_blocked_at, access_blocked_reason, server_code",
    )
    return dict(row) if row else {}


def admin_clear_access_blocked(store: UserStore, username: str) -> dict[str, Any]:
    normalized = _normalize_username(username)
    rowcount = store._execute(
        """
        UPDATE users
        SET access_blocked_at = NULL,
            access_blocked_reason = NULL
        WHERE username = ?
        """,
        (normalized,),
    )
    if rowcount <= 0:
        raise AuthError("Пользователь не найден.")
    row = store._fetch_user_by_username(
        normalized,
        "username, email, created_at, email_verified_at, access_blocked_at, access_blocked_reason, server_code",
    )
    return dict(row) if row else {}


def admin_set_tester_status(store: UserStore, username: str, is_tester: bool) -> dict[str, Any]:
    normalized = _normalize_username(username)
    rowcount = store._execute(
        "UPDATE users SET is_tester = ? WHERE username = ?",
        (1 if is_tester else 0, normalized),
    )
    if rowcount <= 0:
        raise AuthError("Пользователь не найден.")
    row = store._fetch_user_by_username(
        normalized,
        "username, email, created_at, email_verified_at, access_blocked_at, access_blocked_reason, server_code, is_tester, is_gka",
    )
    return dict(row) if row else {}


def admin_set_gka_status(store: UserStore, username: str, is_gka: bool) -> dict[str, Any]:
    normalized = _normalize_username(username)
    rowcount = store._execute(
        "UPDATE users SET is_gka = ? WHERE username = ?",
        (1 if is_gka else 0, normalized),
    )
    if rowcount <= 0:
        raise AuthError("Пользователь не найден.")
    row = store._fetch_user_by_username(
        normalized,
        "username, email, created_at, email_verified_at, access_blocked_at, access_blocked_reason, server_code, is_tester, is_gka",
    )
    return dict(row) if row else {}


def admin_update_email(store: UserStore, username: str, email: str) -> dict[str, Any]:
    normalized = _normalize_username(username)
    normalized_email = _normalize_email(email)
    try:
        rowcount = store._execute(
            """
            UPDATE users
            SET email = ?,
                email_verified_at = NULL,
                email_verification_token_hash = NULL
            WHERE username = ?
            """,
            (normalized_email, normalized),
        )
    except (sqlite3.IntegrityError, IntegrityConflictError) as exc:
        raise AuthError("Пользователь с таким email уже существует.") from exc
    if rowcount <= 0:
        raise AuthError("Пользователь не найден.")
    row = store._fetch_user_by_username(
        normalized,
        "username, email, created_at, email_verified_at, access_blocked_at, access_blocked_reason, server_code, is_tester, is_gka",
    )
    return dict(row) if row else {}


def admin_reset_password(store: UserStore, username: str, new_password: str) -> dict[str, Any]:
    normalized = _normalize_username(username)
    valid_password = _validate_password(new_password)
    row = store._fetch_user_by_username(normalized, "username, email")
    if row is None:
        raise AuthError("Пользователь не найден.")
    record = _build_user_record(valid_password, str(row["email"] or ""), create_email_verification_token())
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
    refreshed = store._fetch_user_by_username(
        normalized,
        "username, email, created_at, email_verified_at, access_blocked_at, access_blocked_reason, server_code, is_tester, is_gka",
    )
    return dict(refreshed) if refreshed else {}

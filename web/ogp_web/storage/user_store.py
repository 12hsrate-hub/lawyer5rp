from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from ogp_web.db.errors import IntegrityConflictError
from ogp_web.db.factory import get_database_backend
from ogp_web.db.types import DatabaseBackend
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
from ogp_web.storage.profile_codec import dump_profile_json, load_profile_json
from ogp_web.storage.user_repository import UserRepository


DEFAULT_SERVER_CODE = "blackberry"


_USERS_COLUMNS = frozenset({
    "username", "email", "salt", "password_hash", "created_at",
    "email_verified_at", "email_verification_token_hash", "email_verification_sent_at",
    "password_reset_token_hash", "password_reset_sent_at",
    "access_blocked_at", "access_blocked_reason",
    "deactivated_at", "deactivated_reason", "api_quota_daily",
    "server_code", "is_tester", "is_gka",
    "representative_profile", "complaint_draft_json", "complaint_draft_updated_at",
})


def _validate_columns(columns: str) -> str:
    if columns == "*":
        return columns
    for col in (c.strip() for c in columns.split(",")):
        if col and col not in _USERS_COLUMNS:
            raise ValueError(f"Unknown column requested: {col!r}")
    return columns


ROOT_DIR = Path(__file__).resolve().parents[3]
AUTH_DIR = ROOT_DIR / "web" / "data"
DB_PATH = AUTH_DIR / "app.db"
LEGACY_USERS_PATH = AUTH_DIR / "users.json"
REPRESENTATIVE_PROFILE_DEFAULTS = {
    "name": "",
    "passport": "",
    "address": "",
    "phone": "",
    "discord": "",
    "passport_scan_url": "",
}

_POSTGRES_SELECT_COLUMNS = {
    "username": "u.username AS username",
    "email": "u.email AS email",
    "salt": "u.salt AS salt",
    "password_hash": "u.password_hash AS password_hash",
    "created_at": "u.created_at AS created_at",
    "email_verified_at": "u.email_verified_at AS email_verified_at",
    "email_verification_token_hash": "u.email_verification_token_hash AS email_verification_token_hash",
    "email_verification_sent_at": "u.email_verification_sent_at AS email_verification_sent_at",
    "password_reset_token_hash": "u.password_reset_token_hash AS password_reset_token_hash",
    "password_reset_sent_at": "u.password_reset_sent_at AS password_reset_sent_at",
    "access_blocked_at": "u.access_blocked_at AS access_blocked_at",
    "access_blocked_reason": "u.access_blocked_reason AS access_blocked_reason",
    "server_code": f"COALESCE(usr.server_code, '{DEFAULT_SERVER_CODE}') AS server_code",
    "is_tester": "COALESCE(usr.is_tester, FALSE) AS is_tester",
    "is_gka": "COALESCE(usr.is_gka, FALSE) AS is_gka",
    "representative_profile": "CAST(u.representative_profile AS TEXT) AS representative_profile",
    "complaint_draft_json": "CAST(cd.draft_json AS TEXT) AS complaint_draft_json",
    "complaint_draft_updated_at": "cd.updated_at AS complaint_draft_updated_at",
}


def _safe_json_load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"users": {}}
    except json.JSONDecodeError:
        return {"users": {}}
    if not isinstance(data, dict):
        return {"users": {}}
    users = data.get("users")
    if not isinstance(users, dict):
        return {"users": {}}
    return data


class UserStore:
    def __init__(self, db_path: Path, legacy_json_path: Path, repository: UserRepository | None = None):
        self.db_path = db_path
        self.legacy_json_path = legacy_json_path
        self.repository = repository or UserRepository(get_database_backend())
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.legacy_json_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()
        self._migrate_legacy_json_if_needed()

    def _connect(self):
        return self.repository.connect()

    @property
    def backend(self) -> DatabaseBackend:
        return self.repository.backend

    @property
    def is_postgres_backend(self) -> bool:
        return self.backend.__class__.__name__ == "PostgresBackend"

    def healthcheck(self) -> dict[str, object]:
        details = dict(self.backend.healthcheck())
        if not details.get("ok") or not self.is_postgres_backend:
            return details

        required_tables = (
            "users",
            "servers",
            "user_server_roles",
            "complaint_drafts",
        )
        conn = self._connect()
        missing: list[str] = []
        try:
            for table_name in required_tables:
                row = conn.execute(
                    "SELECT to_regclass(%s) AS regclass",
                    (f"public.{table_name}",),
                ).fetchone()
                if not row or not row.get("regclass"):
                    missing.append(table_name)
        except Exception as exc:
            details["ok"] = False
            details["error"] = str(exc)
            details["schema_ok"] = False
            return details

        details["schema_ok"] = not missing
        if missing:
            details["ok"] = False
            details["missing_tables"] = missing
            details["error"] = "missing_required_tables"
        return details

    def _fetchone(self, query: str, params: tuple[Any, ...] = ()):
        return self.repository.fetch_one(query, params)

    def _execute(self, query: str, params: tuple[Any, ...] = (), *, commit: bool = True) -> int:
        return self.repository.execute(query, params, commit=commit)

    def _pg_fetchone(self, query: str, params: tuple[Any, ...] = ()):
        try:
            return self._connect().execute(query, params).fetchone()
        except Exception as exc:
            raise self.backend.map_exception(exc) from exc

    def _pg_fetchall(self, query: str, params: tuple[Any, ...] = ()):
        try:
            return self._connect().execute(query, params).fetchall()
        except Exception as exc:
            raise self.backend.map_exception(exc) from exc

    def _pg_execute(self, query: str, params: tuple[Any, ...] = (), *, commit: bool = True) -> int:
        conn = self._connect()
        try:
            cursor = conn.execute(query, params)
            if commit:
                conn.commit()
            return int(cursor.rowcount)
        except Exception as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            raise self.backend.map_exception(exc) from exc

    def _pg_select_list(self, columns: str) -> str:
        validated = _validate_columns(columns)
        if validated == "*":
            names = sorted(_USERS_COLUMNS)
        else:
            names = [name.strip() for name in validated.split(",") if name.strip()]
        return ", ".join(_POSTGRES_SELECT_COLUMNS[name] for name in names)

    def _pg_fetch_user(self, where_clause: str, params: tuple[Any, ...], *, columns: str = "*"):
        query = f"""
            SELECT {self._pg_select_list(columns)}
            FROM users u
            LEFT JOIN user_server_roles usr
                ON usr.user_id = u.id AND usr.server_code = %s
            LEFT JOIN complaint_drafts cd
                ON cd.user_id = u.id AND cd.server_code = %s
            WHERE {where_clause}
            LIMIT 1
        """
        return self._pg_fetchone(query, (DEFAULT_SERVER_CODE, DEFAULT_SERVER_CODE, *params))

    def _auth_user_from_row(self, row) -> AuthUser:
        keys = set(row.keys())
        return AuthUser(
            username=str(row["username"]),
            email=str(row["email"] or ""),
            server_code=str(row["server_code"] or DEFAULT_SERVER_CODE) if "server_code" in keys else DEFAULT_SERVER_CODE,
        )

    def _fetch_user_by_username(self, username: str, columns: str = "*"):
        if self.is_postgres_backend:
            return self._pg_fetch_user("u.username = %s", (_normalize_username(username),), columns=columns)
        return self._fetchone(
            f"SELECT {_validate_columns(columns)} FROM users WHERE username = ?",
            (_normalize_username(username),),
        )

    def _fetch_user_by_email(self, email: str, columns: str = "*"):
        if self.is_postgres_backend:
            return self._pg_fetch_user("u.email = %s", (_normalize_email(email),), columns=columns)
        return self._fetchone(
            f"SELECT {_validate_columns(columns)} FROM users WHERE email = ?",
            (_normalize_email(email),),
        )

    def _ensure_schema(self) -> None:
        if self.is_postgres_backend:
            return
        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    email TEXT,
                    salt TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    email_verified_at TEXT,
                    email_verification_token_hash TEXT,
                    email_verification_sent_at TEXT,
                    password_reset_token_hash TEXT,
                    password_reset_sent_at TEXT,
                    access_blocked_at TEXT,
                    access_blocked_reason TEXT,
                    deactivated_at TEXT,
                    deactivated_reason TEXT,
                    api_quota_daily INTEGER NOT NULL DEFAULT 0,
                    server_code TEXT NOT NULL DEFAULT 'blackberry',
                    is_tester INTEGER NOT NULL DEFAULT 0,
                    is_gka INTEGER NOT NULL DEFAULT 0,
                    representative_profile TEXT NOT NULL,
                    complaint_draft_json TEXT,
                    complaint_draft_updated_at TEXT
                )
                """
            )
            existing_columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(users)").fetchall()
            }
            additions = {
                "email": "ALTER TABLE users ADD COLUMN email TEXT",
                "email_verified_at": "ALTER TABLE users ADD COLUMN email_verified_at TEXT",
                "email_verification_token_hash": "ALTER TABLE users ADD COLUMN email_verification_token_hash TEXT",
                "email_verification_sent_at": "ALTER TABLE users ADD COLUMN email_verification_sent_at TEXT",
                "password_reset_token_hash": "ALTER TABLE users ADD COLUMN password_reset_token_hash TEXT",
                "password_reset_sent_at": "ALTER TABLE users ADD COLUMN password_reset_sent_at TEXT",
                "access_blocked_at": "ALTER TABLE users ADD COLUMN access_blocked_at TEXT",
                "access_blocked_reason": "ALTER TABLE users ADD COLUMN access_blocked_reason TEXT",
                "deactivated_at": "ALTER TABLE users ADD COLUMN deactivated_at TEXT",
                "deactivated_reason": "ALTER TABLE users ADD COLUMN deactivated_reason TEXT",
                "api_quota_daily": "ALTER TABLE users ADD COLUMN api_quota_daily INTEGER NOT NULL DEFAULT 0",
                "server_code": f"ALTER TABLE users ADD COLUMN server_code TEXT NOT NULL DEFAULT '{DEFAULT_SERVER_CODE}'",
                "is_tester": "ALTER TABLE users ADD COLUMN is_tester INTEGER NOT NULL DEFAULT 0",
                "is_gka": "ALTER TABLE users ADD COLUMN is_gka INTEGER NOT NULL DEFAULT 0",
                "complaint_draft_json": "ALTER TABLE users ADD COLUMN complaint_draft_json TEXT",
                "complaint_draft_updated_at": "ALTER TABLE users ADD COLUMN complaint_draft_updated_at TEXT",
            }
            for column_name, statement in additions.items():
                if column_name not in existing_columns:
                    try:
                        conn.execute(statement)
                    except sqlite3.OperationalError as exc:
                        if "duplicate column name" not in str(exc).lower():
                            raise
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique
                ON users(email)
                WHERE email IS NOT NULL AND email <> ''
                """
            )
            conn.commit()

    def _user_count(self) -> int:
        if self.is_postgres_backend:
            row = self._pg_fetchone("SELECT COUNT(*) AS total FROM users")
            return int(row["total"] if row else 0)
        row = self._fetchone("SELECT COUNT(*) AS total FROM users")
        return int(row["total"] if row else 0)

    def _migrate_legacy_json_if_needed(self) -> None:
        if self.is_postgres_backend:
            return
        if self._user_count() > 0 or not self.legacy_json_path.exists():
            return
        data = _safe_json_load(self.legacy_json_path)
        users = data.get("users", {})
        if not isinstance(users, dict) or not users:
            return

        with closing(self._connect()) as conn:
            for username, raw_record in users.items():
                if not isinstance(raw_record, dict):
                    continue
                profile = raw_record.get("representative_profile")
                if not isinstance(profile, dict):
                    profile = {}
                sanitized_profile = {
                    key: str(profile.get(key, "") or "").strip()
                    for key in REPRESENTATIVE_PROFILE_DEFAULTS
                }
                conn.execute(
                    """
                    INSERT OR IGNORE INTO users (
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
                        is_gka,
                        representative_profile
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(username).strip().lower(),
                        None,
                        str(raw_record.get("salt", "") or ""),
                        str(raw_record.get("password_hash", "") or ""),
                        str(raw_record.get("created_at", "") or ""),
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        DEFAULT_SERVER_CODE,
                        0,
                        0,
                        json.dumps(sanitized_profile, ensure_ascii=False),
                    ),
                )
            conn.commit()

    def _pg_register(self, username: str, email: str, password: str) -> tuple[AuthUser, str]:
        normalized = _normalize_username(username)
        normalized_email = _normalize_email(email)
        valid_password = _validate_password(password)
        verification_token = create_email_verification_token()
        record = _build_user_record(valid_password, normalized_email, verification_token)
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO servers (code, title) VALUES (%s, %s) ON CONFLICT (code) DO NOTHING",
                (DEFAULT_SERVER_CODE, "BlackBerry"),
            )
            row = conn.execute(
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
                    representative_profile
                )
                VALUES (%s, %s, %s, %s, %s, NULL, %s, %s, NULL, NULL, NULL, NULL, %s::jsonb)
                RETURNING id
                """,
                (
                    normalized,
                    record["email"],
                    record["salt"],
                    record["password_hash"],
                    record["created_at"],
                    record["email_verification_token_hash"],
                    record["email_verification_sent_at"],
                    json.dumps(record["representative_profile"], ensure_ascii=False),
                ),
            ).fetchone()
            user_id = int(row["id"])
            conn.execute(
                """
                INSERT INTO user_server_roles (user_id, server_code, is_tester, is_gka, is_active)
                VALUES (%s, %s, FALSE, FALSE, TRUE)
                ON CONFLICT (user_id, server_code) DO NOTHING
                """,
                (user_id, DEFAULT_SERVER_CODE),
            )
            conn.execute(
                """
                INSERT INTO complaint_drafts (user_id, server_code, draft_json)
                VALUES (%s, %s, '{}'::jsonb)
                ON CONFLICT (user_id, server_code) DO NOTHING
                """,
                (user_id, DEFAULT_SERVER_CODE),
            )
            conn.commit()
        except Exception as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            mapped = self.backend.map_exception(exc)
            if isinstance(mapped, IntegrityConflictError):
                message = "Пользователь с таким логином уже существует."
                if "email" in str(exc).lower():
                    message = "Пользователь с таким email уже существует."
                raise AuthError(message) from exc
            raise mapped from exc
        return AuthUser(username=normalized, email=normalized_email, server_code=DEFAULT_SERVER_CODE), verification_token

    def _pg_authenticate(self, username: str, password: str) -> AuthUser:
        normalized = (username or "").strip().lower()
        valid_password = _validate_password(password)
        if "@" in normalized:
            row = self._fetch_user_by_email(
                normalized,
                "username, email, server_code, salt, password_hash, email_verified_at, access_blocked_at",
            )
        else:
            row = self._fetch_user_by_username(
                normalized,
                "username, email, server_code, salt, password_hash, email_verified_at, access_blocked_at",
            )
        if row is None:
            raise AuthError("Неверный логин/email или пароль.")
        if not verify_password(valid_password, str(row["salt"]), str(row["password_hash"])):
            raise AuthError("Неверный логин/email или пароль.")
        if str(row["access_blocked_at"] or "").strip():
            raise AuthError("Доступ к аккаунту заблокирован администратором.")
        if not str(row["email_verified_at"] or "").strip():
            raise AuthError("Сначала подтвердите email по ссылке из письма.")
        return self._auth_user_from_row(row)

    def _pg_confirm_email(self, token: str) -> AuthUser:
        raw_token = (token or "").strip()
        if not raw_token:
            raise AuthError("Ссылка подтверждения неполная.")
        token_hash = _hash_email_token(raw_token)
        row = self._pg_fetch_user("u.email_verification_token_hash = %s", (token_hash,), columns="username, email, server_code")
        if row is None:
            raise AuthError("Ссылка подтверждения недействительна или уже использована.")
        self._pg_execute(
            """
            UPDATE users
            SET email_verified_at = NOW(),
                email_verification_token_hash = NULL
            WHERE username = %s
            """,
            (str(row["username"]),),
        )
        return self._auth_user_from_row(row)

    def _pg_issue_email_verification_token(self, email: str) -> tuple[AuthUser, str]:
        normalized_email = _normalize_email(email)
        verification_token = create_email_verification_token()
        row = self._fetch_user_by_email(normalized_email, "username, email, server_code, email_verified_at")
        if row is None:
            raise AuthError("Пользователь с таким email не найден.")
        if str(row["email_verified_at"] or "").strip():
            raise AuthError("Этот email уже подтвержден.")
        self._pg_execute(
            """
            UPDATE users
            SET email_verification_token_hash = %s,
                email_verification_sent_at = NOW()
            WHERE email = %s
            """,
            (_hash_email_token(verification_token), normalized_email),
        )
        return self._auth_user_from_row(row), verification_token

    def _pg_issue_password_reset_token(self, email: str) -> tuple[AuthUser, str]:
        normalized_email = _normalize_email(email)
        reset_token = create_email_verification_token()
        row = self._fetch_user_by_email(normalized_email, "username, email, server_code, email_verified_at")
        if row is None:
            raise AuthError("Пользователь с таким email не найден.")
        if not str(row["email_verified_at"] or "").strip():
            raise AuthError("Сначала подтвердите email, а затем сбрасывайте пароль.")
        self._pg_execute(
            """
            UPDATE users
            SET password_reset_token_hash = %s,
                password_reset_sent_at = NOW()
            WHERE email = %s
            """,
            (_hash_email_token(reset_token), normalized_email),
        )
        return self._auth_user_from_row(row), reset_token

    def _pg_reset_password(self, token: str, new_password: str) -> AuthUser:
        raw_token = (token or "").strip()
        if not raw_token:
            raise AuthError("Ссылка сброса неполная.")
        valid_password = _validate_password(new_password)
        token_hash = _hash_email_token(raw_token)
        row = self._pg_fetch_user("u.password_reset_token_hash = %s", (token_hash,), columns="username, email, server_code")
        if row is None:
            raise AuthError("Ссылка сброса недействительна или уже использована.")
        record = _build_user_record(valid_password, str(row["email"] or ""), create_email_verification_token())
        self._pg_execute(
            """
            UPDATE users
            SET salt = %s,
                password_hash = %s,
                password_reset_token_hash = NULL,
                password_reset_sent_at = NULL
            WHERE username = %s
            """,
            (
                record["salt"],
                record["password_hash"],
                str(row["username"]),
            ),
        )
        return self._auth_user_from_row(row)

    def _pg_change_password(self, username: str, current_password: str, new_password: str) -> AuthUser:
        normalized = _normalize_username(username)
        valid_current_password = _validate_password(current_password)
        valid_new_password = _validate_password(new_password)
        row = self._fetch_user_by_username(normalized, "username, email, server_code, salt, password_hash")
        if row is None:
            raise AuthError("Пользователь не найден.")
        if not verify_password(valid_current_password, str(row["salt"]), str(row["password_hash"])):
            raise AuthError("Текущий пароль введен неверно.")
        if valid_current_password == valid_new_password:
            raise AuthError("Новый пароль должен отличаться от текущего.")
        record = _build_user_record(valid_new_password, str(row["email"] or ""), create_email_verification_token())
        self._pg_execute(
            """
            UPDATE users
            SET salt = %s,
                password_hash = %s,
                password_reset_token_hash = NULL,
                password_reset_sent_at = NULL
            WHERE username = %s
            """,
            (
                record["salt"],
                record["password_hash"],
                normalized,
            ),
        )
        return self._auth_user_from_row(row)

    def _pg_set_role_flag(self, username: str, flag_column: str, enabled: bool) -> dict[str, Any]:
        normalized = _normalize_username(username)
        if flag_column not in {"is_tester", "is_gka"}:
            raise ValueError(f"Unsupported role flag: {flag_column!r}")
        user_row = self._pg_fetchone("SELECT id FROM users WHERE username = %s", (normalized,))
        if user_row is None:
            raise AuthError("Пользователь не найден.")
        current = self._fetch_user_by_username(normalized, "is_tester, is_gka")
        current_tester = bool(current["is_tester"]) if current else False
        current_gka = bool(current["is_gka"]) if current else False
        if flag_column == "is_tester":
            current_tester = bool(enabled)
        else:
            current_gka = bool(enabled)
        self._pg_execute(
            """
            INSERT INTO user_server_roles (user_id, server_code, is_tester, is_gka, is_active)
            VALUES (%s, %s, %s, %s, TRUE)
            ON CONFLICT (user_id, server_code)
            DO UPDATE SET
                is_tester = EXCLUDED.is_tester,
                is_gka = EXCLUDED.is_gka,
                updated_at = NOW()
            """,
            (int(user_row["id"]), DEFAULT_SERVER_CODE, current_tester, current_gka),
        )
        row = self._fetch_user_by_username(
            normalized,
            "username, email, created_at, email_verified_at, access_blocked_at, access_blocked_reason, deactivated_at, deactivated_reason, api_quota_daily, server_code, is_tester, is_gka",
        )
        return dict(row) if row else {}

    def register(self, username: str, email: str, password: str) -> tuple[AuthUser, str]:
        if self.is_postgres_backend:
            return self._pg_register(username, email, password)
        from ogp_web.services.user_auth_store_service import register_user

        return register_user(self, username, email, password)

    def authenticate(self, username: str, password: str) -> AuthUser:
        if self.is_postgres_backend:
            return self._pg_authenticate(username, password)
        from ogp_web.services.user_auth_store_service import authenticate_user

        return authenticate_user(self, username, password)

    def confirm_email(self, token: str) -> AuthUser:
        if self.is_postgres_backend:
            return self._pg_confirm_email(token)
        from ogp_web.services.user_auth_store_service import confirm_email

        return confirm_email(self, token)

    def issue_email_verification_token(self, email: str) -> tuple[AuthUser, str]:
        if self.is_postgres_backend:
            return self._pg_issue_email_verification_token(email)
        from ogp_web.services.user_auth_store_service import issue_email_verification_token

        return issue_email_verification_token(self, email)

    def issue_password_reset_token(self, email: str) -> tuple[AuthUser, str]:
        if self.is_postgres_backend:
            return self._pg_issue_password_reset_token(email)
        from ogp_web.services.user_auth_store_service import issue_password_reset_token

        return issue_password_reset_token(self, email)

    def reset_password(self, token: str, new_password: str) -> AuthUser:
        if self.is_postgres_backend:
            return self._pg_reset_password(token, new_password)
        from ogp_web.services.user_auth_store_service import reset_password

        return reset_password(self, token, new_password)

    def get_representative_profile(self, username: str) -> dict[str, str]:
        row = self._fetch_user_by_username(username, "representative_profile")
        if row is None:
            raise AuthError("Пользователь не найден.")
        return load_profile_json(str(row["representative_profile"] or ""), REPRESENTATIVE_PROFILE_DEFAULTS)

    def save_representative_profile(self, username: str, profile: dict[str, Any]) -> dict[str, str]:
        normalized = _normalize_username(username)
        sanitized = {
            key: str(profile.get(key, "") or "").strip()
            for key in REPRESENTATIVE_PROFILE_DEFAULTS
        }
        profile_json = dump_profile_json(sanitized, REPRESENTATIVE_PROFILE_DEFAULTS)
        if self.is_postgres_backend:
            rowcount = self._pg_execute(
                "UPDATE users SET representative_profile = %s::jsonb WHERE username = %s",
                (profile_json, normalized),
            )
        else:
            rowcount = self._execute(
                "UPDATE users SET representative_profile = ? WHERE username = ?",
                (profile_json, normalized),
            )
        if rowcount <= 0:
            raise AuthError("Пользователь не найден.")
        return sanitized

    def change_password(self, username: str, current_password: str, new_password: str) -> AuthUser:
        if self.is_postgres_backend:
            return self._pg_change_password(username, current_password, new_password)
        from ogp_web.services.user_auth_store_service import change_password

        return change_password(self, username, current_password, new_password)

    def get_complaint_draft(self, username: str) -> dict[str, Any]:
        row = self._fetch_user_by_username(
            username,
            "complaint_draft_json, complaint_draft_updated_at",
        )
        if row is None:
            raise AuthError("Пользователь не найден.")
        raw_draft = row["complaint_draft_json"]
        if not raw_draft:
            return {"draft": {}, "updated_at": ""}
        try:
            draft = json.loads(str(raw_draft))
        except json.JSONDecodeError:
            draft = {}
        if not isinstance(draft, dict):
            draft = {}
        return {
            "draft": draft,
            "updated_at": str(row["complaint_draft_updated_at"] or ""),
        }

    def save_complaint_draft(self, username: str, draft: dict[str, Any]) -> dict[str, Any]:
        normalized = _normalize_username(username)
        if not isinstance(draft, dict):
            raise AuthError("Черновик жалобы должен быть объектом.")
        if self.is_postgres_backend:
            rowcount = self._pg_execute(
                """
                INSERT INTO complaint_drafts (user_id, server_code, draft_json, updated_at)
                SELECT id, %s, %s::jsonb, NOW()
                FROM users
                WHERE username = %s
                ON CONFLICT (user_id, server_code)
                DO UPDATE SET draft_json = EXCLUDED.draft_json, updated_at = NOW()
                """,
                (DEFAULT_SERVER_CODE, json.dumps(draft, ensure_ascii=False), normalized),
            )
        else:
            rowcount = self._execute(
                """
                UPDATE users
                SET complaint_draft_json = ?,
                    complaint_draft_updated_at = CURRENT_TIMESTAMP
                WHERE username = ?
                """,
                (json.dumps(draft, ensure_ascii=False), normalized),
            )
        if rowcount <= 0:
            raise AuthError("Пользователь не найден.")
        return self.get_complaint_draft(normalized)

    def clear_complaint_draft(self, username: str) -> None:
        normalized = _normalize_username(username)
        if self.is_postgres_backend:
            self._pg_execute(
                """
                UPDATE complaint_drafts cd
                SET draft_json = '{}'::jsonb,
                    updated_at = NOW()
                FROM users u
                WHERE cd.user_id = u.id
                  AND cd.server_code = %s
                  AND u.username = %s
                """,
                (DEFAULT_SERVER_CODE, normalized),
            )
            return
        rowcount = self._execute(
            """
            UPDATE users
            SET complaint_draft_json = NULL,
                complaint_draft_updated_at = NULL
            WHERE username = ?
            """,
            (normalized,),
        )
        if rowcount <= 0:
            raise AuthError("Пользователь не найден.")

    def list_users(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        safe_limit = None
        if limit is not None:
            try:
                safe_limit = int(limit)
                if safe_limit <= 0:
                    safe_limit = None
            except (TypeError, ValueError):
                safe_limit = None

        if self.is_postgres_backend:
            limit_clause = ""
            if safe_limit:
                limit_clause = " LIMIT %s"
                params: tuple[Any, ...] = (DEFAULT_SERVER_CODE, safe_limit)
            else:
                params = (DEFAULT_SERVER_CODE,)
            rows = self._pg_fetchall(
                f"""
                SELECT
                    u.username AS username,
                    u.email AS email,
                    u.created_at AS created_at,
                    u.email_verified_at AS email_verified_at,
                    u.access_blocked_at AS access_blocked_at,
                    u.access_blocked_reason AS access_blocked_reason,
                    u.deactivated_at AS deactivated_at,
                    u.deactivated_reason AS deactivated_reason,
                    COALESCE(u.api_quota_daily, 0) AS api_quota_daily,
                    COALESCE(usr.server_code, '{DEFAULT_SERVER_CODE}') AS server_code,
                    COALESCE(usr.is_tester, FALSE) AS is_tester,
                    COALESCE(usr.is_gka, FALSE) AS is_gka
                FROM users u
                LEFT JOIN user_server_roles usr
                    ON usr.user_id = u.id AND usr.server_code = %s
                ORDER BY u.created_at DESC, u.username ASC
                {limit_clause}
                """,
                params,
            )
            return [dict(row) for row in rows]
        from ogp_web.services.user_admin_store_service import list_users

        if safe_limit:
            return list_users(self, limit=safe_limit)

        return list_users(self)

    def is_access_blocked(self, username: str) -> bool:
        if self.is_postgres_backend:
            row = self._fetch_user_by_username(username, "access_blocked_at")
            if row is None:
                raise AuthError("Пользователь не найден.")
            return bool(str(row["access_blocked_at"] or "").strip())
        from ogp_web.services.user_admin_store_service import is_access_blocked

        return is_access_blocked(self, username)

    def get_api_quota_daily(self, username: str) -> int:
        row = self._fetch_user_by_username(username, "api_quota_daily")
        if row is None:
            raise AuthError("РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ РЅРµ РЅР°Р№РґРµРЅ.")
        try:
            return max(0, int(row["api_quota_daily"] or 0))
        except (TypeError, ValueError):
            return 0

    def is_tester_user(self, username: str, *, server_code: str | None = None) -> bool:
        if self.is_postgres_backend:
            row = self._fetch_user_by_username(username, "is_tester, server_code")
            if row is None:
                return False
            if server_code and str(row["server_code"] or "").strip().lower() != str(server_code).strip().lower():
                return False
            return bool(row["is_tester"])
        from ogp_web.services.user_admin_store_service import is_tester_user

        return is_tester_user(self, username, server_code=server_code)

    def is_gka_user(self, username: str, *, server_code: str | None = None) -> bool:
        if self.is_postgres_backend:
            row = self._fetch_user_by_username(username, "is_gka, server_code")
            if row is None:
                return False
            if server_code and str(row["server_code"] or "").strip().lower() != str(server_code).strip().lower():
                return False
            return bool(row["is_gka"])
        from ogp_web.services.user_admin_store_service import is_gka_user

        return is_gka_user(self, username, server_code=server_code)

    def get_server_code(self, username: str) -> str:
        row = self._fetch_user_by_username(username, "server_code")
        if row is None:
            raise AuthError("Пользователь не найден.")
        code = str(row["server_code"] or DEFAULT_SERVER_CODE).strip().lower() or DEFAULT_SERVER_CODE
        from ogp_web.server_config.registry import get_server_config

        get_server_config(code)
        return code

    def get_auth_user(self, username: str) -> AuthUser:
        row = self._fetch_user_by_username(username, "username, email, server_code")
        if row is None:
            raise AuthError("Пользователь не найден.")
        return self._auth_user_from_row(row)

    def admin_mark_email_verified(self, username: str) -> dict[str, Any]:
        if self.is_postgres_backend:
            normalized = _normalize_username(username)
            rowcount = self._pg_execute(
                """
                UPDATE users
                SET email_verified_at = COALESCE(email_verified_at, NOW()),
                    email_verification_token_hash = NULL
                WHERE username = %s
                """,
                (normalized,),
            )
            if rowcount <= 0:
                raise AuthError("Пользователь не найден.")
            row = self._fetch_user_by_username(
                normalized,
                "username, email, created_at, email_verified_at, access_blocked_at, access_blocked_reason, deactivated_at, deactivated_reason, api_quota_daily, server_code, is_tester, is_gka",
            )
            return dict(row) if row else {}
        from ogp_web.services.user_admin_store_service import admin_mark_email_verified

        return admin_mark_email_verified(self, username)

    def admin_set_access_blocked(self, username: str, reason: str = "") -> dict[str, Any]:
        if self.is_postgres_backend:
            normalized = _normalize_username(username)
            rowcount = self._pg_execute(
                """
                UPDATE users
                SET access_blocked_at = NOW(),
                    access_blocked_reason = %s
                WHERE username = %s
                """,
                (str(reason or "").strip(), normalized),
            )
            if rowcount <= 0:
                raise AuthError("Пользователь не найден.")
            row = self._fetch_user_by_username(
                normalized,
                "username, email, created_at, email_verified_at, access_blocked_at, access_blocked_reason, deactivated_at, deactivated_reason, api_quota_daily, server_code, is_tester, is_gka",
            )
            return dict(row) if row else {}
        from ogp_web.services.user_admin_store_service import admin_set_access_blocked

        return admin_set_access_blocked(self, username, reason)

    def admin_clear_access_blocked(self, username: str) -> dict[str, Any]:
        if self.is_postgres_backend:
            normalized = _normalize_username(username)
            rowcount = self._pg_execute(
                """
                UPDATE users
                SET access_blocked_at = NULL,
                    access_blocked_reason = NULL
                WHERE username = %s
                """,
                (normalized,),
            )
            if rowcount <= 0:
                raise AuthError("Пользователь не найден.")
            row = self._fetch_user_by_username(
                normalized,
                "username, email, created_at, email_verified_at, access_blocked_at, access_blocked_reason, deactivated_at, deactivated_reason, api_quota_daily, server_code, is_tester, is_gka",
            )
            return dict(row) if row else {}
        from ogp_web.services.user_admin_store_service import admin_clear_access_blocked

        return admin_clear_access_blocked(self, username)

    def admin_set_tester_status(self, username: str, is_tester: bool) -> dict[str, Any]:
        if self.is_postgres_backend:
            return self._pg_set_role_flag(username, "is_tester", is_tester)
        from ogp_web.services.user_admin_store_service import admin_set_tester_status

        return admin_set_tester_status(self, username, is_tester)

    def admin_set_gka_status(self, username: str, is_gka: bool) -> dict[str, Any]:
        if self.is_postgres_backend:
            return self._pg_set_role_flag(username, "is_gka", is_gka)
        from ogp_web.services.user_admin_store_service import admin_set_gka_status

        return admin_set_gka_status(self, username, is_gka)

    def admin_update_email(self, username: str, email: str) -> dict[str, Any]:
        if self.is_postgres_backend:
            normalized = _normalize_username(username)
            normalized_email = _normalize_email(email)
            try:
                rowcount = self._pg_execute(
                    """
                    UPDATE users
                    SET email = %s,
                        email_verified_at = NULL,
                        email_verification_token_hash = NULL
                    WHERE username = %s
                    """,
                    (normalized_email, normalized),
                )
            except IntegrityConflictError as exc:
                raise AuthError("Пользователь с таким email уже существует.") from exc
            if rowcount <= 0:
                raise AuthError("Пользователь не найден.")
            row = self._fetch_user_by_username(
                normalized,
                "username, email, created_at, email_verified_at, access_blocked_at, access_blocked_reason, deactivated_at, deactivated_reason, api_quota_daily, server_code, is_tester, is_gka",
            )
            return dict(row) if row else {}
        from ogp_web.services.user_admin_store_service import admin_update_email

        return admin_update_email(self, username, email)

    def admin_reset_password(self, username: str, new_password: str) -> dict[str, Any]:
        if self.is_postgres_backend:
            normalized = _normalize_username(username)
            valid_password = _validate_password(new_password)
            row = self._fetch_user_by_username(normalized, "username, email")
            if row is None:
                raise AuthError("Пользователь не найден.")
            record = _build_user_record(valid_password, str(row["email"] or ""), create_email_verification_token())
            self._pg_execute(
                """
                UPDATE users
                SET salt = %s,
                    password_hash = %s,
                    password_reset_token_hash = NULL,
                    password_reset_sent_at = NULL
                WHERE username = %s
                """,
                (
                    record["salt"],
                    record["password_hash"],
                    normalized,
                ),
            )
            refreshed = self._fetch_user_by_username(
                normalized,
                "username, email, created_at, email_verified_at, access_blocked_at, access_blocked_reason, deactivated_at, deactivated_reason, api_quota_daily, server_code, is_tester, is_gka",
            )
            return dict(refreshed) if refreshed else {}
        from ogp_web.services.user_admin_store_service import admin_reset_password

        return admin_reset_password(self, username, new_password)

    def admin_deactivate_user(self, username: str, reason: str = "") -> dict[str, Any]:
        if self.is_postgres_backend:
            normalized = _normalize_username(username)
            rowcount = self._pg_execute(
                """
                UPDATE users
                SET deactivated_at = NOW(),
                    deactivated_reason = %s,
                    access_blocked_at = COALESCE(access_blocked_at, NOW()),
                    access_blocked_reason = COALESCE(NULLIF(access_blocked_reason, ''), %s)
                WHERE username = %s
                """,
                (str(reason or "").strip(), str(reason or "").strip(), normalized),
            )
            if rowcount <= 0:
                raise AuthError("Пользователь не найден.")
            row = self._fetch_user_by_username(
                normalized,
                "username, email, created_at, email_verified_at, access_blocked_at, access_blocked_reason, deactivated_at, deactivated_reason, api_quota_daily, server_code, is_tester, is_gka",
            )
            return dict(row) if row else {}
        from ogp_web.services.user_admin_store_service import admin_deactivate_user

        return admin_deactivate_user(self, username, reason)

    def admin_reactivate_user(self, username: str) -> dict[str, Any]:
        if self.is_postgres_backend:
            normalized = _normalize_username(username)
            rowcount = self._pg_execute(
                """
                UPDATE users
                SET deactivated_at = NULL,
                    deactivated_reason = NULL,
                    access_blocked_at = NULL,
                    access_blocked_reason = NULL
                WHERE username = %s
                """,
                (normalized,),
            )
            if rowcount <= 0:
                raise AuthError("Пользователь не найден.")
            row = self._fetch_user_by_username(
                normalized,
                "username, email, created_at, email_verified_at, access_blocked_at, access_blocked_reason, deactivated_at, deactivated_reason, api_quota_daily, server_code, is_tester, is_gka",
            )
            return dict(row) if row else {}
        from ogp_web.services.user_admin_store_service import admin_reactivate_user

        return admin_reactivate_user(self, username)

    def admin_set_daily_quota(self, username: str, daily_limit: int) -> dict[str, Any]:
        if self.is_postgres_backend:
            normalized = _normalize_username(username)
            safe_limit = max(0, int(daily_limit or 0))
            rowcount = self._pg_execute(
                """
                UPDATE users
                SET api_quota_daily = %s
                WHERE username = %s
                """,
                (safe_limit, normalized),
            )
            if rowcount <= 0:
                raise AuthError("Пользователь не найден.")
            row = self._fetch_user_by_username(
                normalized,
                "username, email, created_at, email_verified_at, access_blocked_at, access_blocked_reason, deactivated_at, deactivated_reason, api_quota_daily, server_code, is_tester, is_gka",
            )
            return dict(row) if row else {}
        from ogp_web.services.user_admin_store_service import admin_set_daily_quota

        return admin_set_daily_quota(self, username, daily_limit)


_DEFAULT_USER_STORE: UserStore | None = None


def get_default_user_store() -> UserStore:
    global _DEFAULT_USER_STORE
    if _DEFAULT_USER_STORE is None:
        _DEFAULT_USER_STORE = UserStore(
            DB_PATH,
            LEGACY_USERS_PATH,
            repository=UserRepository(get_database_backend()),
        )
    return _DEFAULT_USER_STORE

from __future__ import annotations

import json
import gc
import os
import shutil
import sys
import threading
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

os.environ.setdefault("OGP_DB_BACKEND", "sqlite")

from ogp_web.storage.exam_answers_store import ExamAnswersStore
from ogp_web.storage.user_store import UserStore
from ogp_web.storage.user_repository import UserRepository
from ogp_web.db.backends.sqlite import SQLiteBackend
from ogp_web.rate_limit import PersistentRateLimiter
from ogp_web.services.auth_service import AuthError
from ogp_web.services.exam_import_tasks import ExamImportTaskRegistry
from ogp_web.storage.admin_metrics_store import AdminMetricsStore
from tests.temp_helpers import make_temp_dir


class FakeCursor:
    def __init__(self, *, rowcount: int = 0, one=None, rows=None):
        self.rowcount = rowcount
        self._one = one
        self._rows = rows or []

    def fetchone(self):
        return self._one

    def fetchall(self):
        return list(self._rows)


class UniqueViolation(Exception):
    pass


class PostgresBackend:
    def __init__(self, *, missing_tables: set[str] | None = None):
        self._state = {
            "next_user_id": 1,
            "servers": {},
            "users": {},
            "roles": {},
            "drafts": {},
            "clock": 0,
            "missing_tables": set(missing_tables or set()),
        }

    def connect(self):
        return FakePostgresConnection(self._state)

    def healthcheck(self) -> dict[str, object]:
        return {"backend": "postgres", "ok": True}

    def map_exception(self, exc: Exception) -> Exception:
        from ogp_web.db.errors import DatabaseUnavailableError, IntegrityConflictError

        if exc.__class__.__name__ in {"UniqueViolation", "ForeignKeyViolation", "NotNullViolation"}:
            return IntegrityConflictError(str(exc))
        return DatabaseUnavailableError(str(exc))


class FakePostgresConnection:
    def __init__(self, state):
        self.state = state

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None

    def execute(self, query: str, params=()):
        normalized = " ".join(query.split())

        if normalized == "SELECT 1":
            return FakeCursor(rowcount=1, one={"?column?": 1})
        if normalized == "SELECT to_regclass(%s) AS regclass":
            table_name = str(params[0]).split(".", 1)[-1]
            present = table_name not in self.state["missing_tables"]
            return FakeCursor(rowcount=1, one={"regclass": params[0] if present else None})
        if normalized == "SELECT COUNT(*) AS total FROM users":
            return FakeCursor(rowcount=1, one={"total": len(self.state["users"])})
        if normalized.startswith("INSERT INTO servers"):
            code, title = params
            self.state["servers"][code] = {"code": code, "title": title}
            return FakeCursor(rowcount=1)
        if normalized.startswith("INSERT INTO users ") and "RETURNING id" in normalized:
            return self._insert_user(params)
        if normalized.startswith("INSERT INTO user_server_roles "):
            return self._upsert_role(params)
        if normalized.startswith("INSERT INTO complaint_drafts (user_id, server_code, draft_json) VALUES"):
            return self._insert_draft(params)
        if normalized.startswith("INSERT INTO complaint_drafts (user_id, server_code, draft_json, updated_at) SELECT"):
            return self._save_draft(params)
        if (
            "FROM users u LEFT JOIN user_server_roles usr" in normalized
            and "ORDER BY u.created_at DESC, u.username ASC" in normalized
        ):
            return self._list_users(params)
        if "FROM users u LEFT JOIN user_server_roles usr" in normalized and "LEFT JOIN complaint_drafts cd" in normalized:
            return self._fetch_user(normalized, params)
        if normalized.startswith("SELECT id FROM users WHERE username = %s"):
            user = self.state["users"].get(params[0])
            return FakeCursor(rowcount=1 if user else 0, one={"id": user["id"]} if user else None)
        if normalized.startswith("UPDATE users SET email_verified_at = NOW(), email_verification_token_hash = NULL WHERE username = %s"):
            return self._mark_email_verified(params[0])
        if normalized.startswith("UPDATE users SET email_verification_token_hash = %s, email_verification_sent_at = NOW() WHERE email = %s"):
            return self._set_email_verification_token(params)
        if normalized.startswith("UPDATE users SET password_reset_token_hash = %s, password_reset_sent_at = NOW() WHERE email = %s"):
            return self._set_password_reset_token(params)
        if normalized.startswith("UPDATE users SET salt = %s, password_hash = %s, password_reset_token_hash = NULL, password_reset_sent_at = NULL WHERE username = %s"):
            return self._update_password(params)
        if normalized.startswith("UPDATE users SET representative_profile = %s::jsonb WHERE username = %s"):
            return self._update_profile(params)
        if normalized.startswith("UPDATE complaint_drafts cd SET draft_json = '{}'::jsonb, updated_at = NOW() FROM users u"):
            return self._clear_draft(params)
        if normalized.startswith("UPDATE users SET access_blocked_at = NOW(), access_blocked_reason = %s WHERE username = %s"):
            return self._set_access_block(params)
        if normalized.startswith("UPDATE users SET access_blocked_at = NULL, access_blocked_reason = NULL WHERE username = %s"):
            return self._clear_access_block(params[0])
        if normalized.startswith("UPDATE users SET email_verified_at = COALESCE(email_verified_at, NOW()), email_verification_token_hash = NULL WHERE username = %s"):
            return self._mark_email_verified(params[0], preserve_existing=True)
        if normalized.startswith("UPDATE users SET email = %s, email_verified_at = NULL, email_verification_token_hash = NULL WHERE username = %s"):
            return self._update_email(params)

        raise AssertionError(f"Unsupported fake postgres query: {normalized}")

    def _now(self) -> str:
        self.state["clock"] += 1
        return f"2026-04-10T00:00:{self.state['clock']:02d}Z"

    def _insert_user(self, params):
        username, email, salt, password_hash, created_at, token_hash, token_sent_at, profile_json = params
        if username in self.state["users"]:
            raise UniqueViolation("duplicate username")
        if any(existing["email"] == email for existing in self.state["users"].values()):
            raise UniqueViolation("duplicate email")
        user_id = self.state["next_user_id"]
        self.state["next_user_id"] += 1
        self.state["users"][username] = {
            "id": user_id,
            "username": username,
            "email": email,
            "salt": salt,
            "password_hash": password_hash,
            "created_at": created_at,
            "email_verified_at": None,
            "email_verification_token_hash": token_hash,
            "email_verification_sent_at": token_sent_at,
            "password_reset_token_hash": None,
            "password_reset_sent_at": None,
            "access_blocked_at": None,
            "access_blocked_reason": None,
            "representative_profile": json.loads(profile_json),
        }
        return FakeCursor(rowcount=1, one={"id": user_id})

    def _upsert_role(self, params):
        if len(params) == 2:
            user_id, server_code = params
            is_tester = False
            is_gka = False
        else:
            user_id, server_code, is_tester, is_gka = params[:4]
        self.state["roles"][(user_id, server_code)] = {
            "user_id": user_id,
            "server_code": server_code,
            "is_tester": bool(is_tester),
            "is_gka": bool(is_gka),
            "is_active": True,
            "updated_at": self._now(),
        }
        return FakeCursor(rowcount=1)

    def _insert_draft(self, params):
        user_id, server_code = params
        self.state["drafts"][(user_id, server_code)] = {
            "draft_json": {},
            "updated_at": self._now(),
        }
        return FakeCursor(rowcount=1)

    def _save_draft(self, params):
        server_code, draft_json, username = params
        user = self.state["users"].get(username)
        if user is None:
            return FakeCursor(rowcount=0)
        self.state["drafts"][(user["id"], server_code)] = {
            "draft_json": json.loads(draft_json),
            "updated_at": self._now(),
        }
        return FakeCursor(rowcount=1)

    def _find_by(self, field: str, value: str):
        for user in self.state["users"].values():
            if user.get(field) == value:
                return user
        return None

    def _compose_user_row(self, user, server_code: str):
        role = self.state["roles"].get((user["id"], server_code), {})
        draft = self.state["drafts"].get((user["id"], server_code), {})
        return {
            "username": user["username"],
            "email": user["email"],
            "salt": user["salt"],
            "password_hash": user["password_hash"],
            "created_at": user["created_at"],
            "email_verified_at": user["email_verified_at"],
            "email_verification_token_hash": user["email_verification_token_hash"],
            "email_verification_sent_at": user["email_verification_sent_at"],
            "password_reset_token_hash": user["password_reset_token_hash"],
            "password_reset_sent_at": user["password_reset_sent_at"],
            "access_blocked_at": user["access_blocked_at"],
            "access_blocked_reason": user["access_blocked_reason"],
            "server_code": role.get("server_code", server_code),
            "is_tester": role.get("is_tester", False),
            "is_gka": role.get("is_gka", False),
            "representative_profile": json.dumps(user["representative_profile"], ensure_ascii=False),
            "complaint_draft_json": json.dumps(draft.get("draft_json", {}), ensure_ascii=False),
            "complaint_draft_updated_at": draft.get("updated_at"),
        }

    def _fetch_user(self, normalized: str, params):
        server_code = params[0]
        if "u.username = %s" in normalized:
            user = self.state["users"].get(params[2])
        elif "u.email = %s" in normalized:
            user = self._find_by("email", params[2])
        elif "u.email_verification_token_hash = %s" in normalized:
            user = self._find_by("email_verification_token_hash", params[2])
        elif "u.password_reset_token_hash = %s" in normalized:
            user = self._find_by("password_reset_token_hash", params[2])
        else:
            raise AssertionError(f"Unsupported fake postgres fetch query: {normalized}")
        row = self._compose_user_row(user, server_code) if user else None
        return FakeCursor(rowcount=1 if row else 0, one=row)

    def _list_users(self, params):
        server_code = params[0]
        rows = [
            self._compose_user_row(user, server_code)
            for user in sorted(
                self.state["users"].values(),
                key=lambda item: (item["created_at"], item["username"]),
                reverse=True,
            )
        ]
        return FakeCursor(rowcount=len(rows), rows=rows)

    def _mark_email_verified(self, username: str, *, preserve_existing: bool = False):
        user = self.state["users"].get(username)
        if user is None:
            return FakeCursor(rowcount=0)
        if not preserve_existing or not user["email_verified_at"]:
            user["email_verified_at"] = self._now()
        user["email_verification_token_hash"] = None
        return FakeCursor(rowcount=1)

    def _set_email_verification_token(self, params):
        token_hash, email = params
        user = self._find_by("email", email)
        if user is None:
            return FakeCursor(rowcount=0)
        user["email_verification_token_hash"] = token_hash
        user["email_verification_sent_at"] = self._now()
        return FakeCursor(rowcount=1)

    def _set_password_reset_token(self, params):
        token_hash, email = params
        user = self._find_by("email", email)
        if user is None:
            return FakeCursor(rowcount=0)
        user["password_reset_token_hash"] = token_hash
        user["password_reset_sent_at"] = self._now()
        return FakeCursor(rowcount=1)

    def _update_password(self, params):
        salt, password_hash, username = params
        user = self.state["users"].get(username)
        if user is None:
            return FakeCursor(rowcount=0)
        user["salt"] = salt
        user["password_hash"] = password_hash
        user["password_reset_token_hash"] = None
        user["password_reset_sent_at"] = None
        return FakeCursor(rowcount=1)

    def _update_profile(self, params):
        profile_json, username = params
        user = self.state["users"].get(username)
        if user is None:
            return FakeCursor(rowcount=0)
        user["representative_profile"] = json.loads(profile_json)
        return FakeCursor(rowcount=1)

    def _clear_draft(self, params):
        server_code, username = params
        user = self.state["users"].get(username)
        if user is None:
            return FakeCursor(rowcount=0)
        self.state["drafts"][(user["id"], server_code)] = {
            "draft_json": {},
            "updated_at": self._now(),
        }
        return FakeCursor(rowcount=1)

    def _set_access_block(self, params):
        reason, username = params
        user = self.state["users"].get(username)
        if user is None:
            return FakeCursor(rowcount=0)
        user["access_blocked_at"] = self._now()
        user["access_blocked_reason"] = reason
        return FakeCursor(rowcount=1)

    def _clear_access_block(self, username: str):
        user = self.state["users"].get(username)
        if user is None:
            return FakeCursor(rowcount=0)
        user["access_blocked_at"] = None
        user["access_blocked_reason"] = None
        return FakeCursor(rowcount=1)

    def _update_email(self, params):
        email, username = params
        user = self.state["users"].get(username)
        if user is None:
            return FakeCursor(rowcount=0)
        for existing_username, existing in self.state["users"].items():
            if existing_username != username and existing["email"] == email:
                raise UniqueViolation("duplicate email")
        user["email"] = email
        user["email_verified_at"] = None
        user["email_verification_token_hash"] = None
        return FakeCursor(rowcount=1)


class FakeAdminMetricsPostgresBackend:
    def __init__(self):
        self._state = {"metric_events": [], "next_id": 1, "clock": 0}

    def connect(self):
        return FakeAdminMetricsConnection(self._state)

    def healthcheck(self) -> dict[str, object]:
        return {"backend": "postgres", "ok": True}

    def map_exception(self, exc: Exception) -> Exception:
        from ogp_web.db.errors import DatabaseUnavailableError

        return DatabaseUnavailableError(str(exc))


class FakeAdminMetricsConnection:
    def __init__(self, state):
        self.state = state

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None

    def execute(self, query: str, params=()):
        normalized = " ".join(query.split())

        if normalized.startswith("CREATE TABLE IF NOT EXISTS metric_events"):
            return FakeCursor(rowcount=0)
        if normalized.startswith("CREATE INDEX IF NOT EXISTS idx_metric_events_"):
            return FakeCursor(rowcount=0)
        if normalized.startswith("INSERT INTO metric_events "):
            return self._insert_event(params)
        if "COUNT(*) AS total_events" in normalized and "FROM metric_events" in normalized:
            return self._totals()
        if normalized.startswith("SELECT path, COUNT(*) AS count FROM metric_events"):
            return self._top_endpoints()
        if normalized.startswith("SELECT created_at, username, server_code, event_type, path, method, status_code, duration_ms, request_bytes, response_bytes, resource_units, meta_json FROM metric_events"):
            return self._recent_events(normalized, params)
        if normalized.startswith("SELECT username, MAX(server_code) AS server_code,"):
            return self._user_metrics()
        if normalized.startswith("SELECT event_type, meta_json FROM metric_events WHERE event_type IN"):
            return self._ai_exam_stats()
        if normalized.startswith("SELECT created_at, username, server_code, event_type, path, status_code, meta_json FROM metric_events WHERE event_type IN"):
            return self._latest_event(params)

        raise AssertionError(f"Unsupported fake admin metrics query: {normalized}")

    def _now(self) -> str:
        self.state["clock"] += 1
        return f"2026-04-10T00:00:{self.state['clock']:02d}Z"

    def _insert_event(self, params):
        event = {
            "id": self.state["next_id"],
            "created_at": self._now(),
            "username": params[0],
            "server_code": params[1],
            "event_type": params[2],
            "path": params[3],
            "method": params[4],
            "status_code": params[5],
            "duration_ms": params[6],
            "request_bytes": params[7],
            "response_bytes": params[8],
            "resource_units": params[9],
            "meta_json": json.loads(params[10]),
        }
        self.state["metric_events"].append(event)
        self.state["next_id"] += 1
        return FakeCursor(rowcount=1)

    def _filtered_events(self, normalized: str, params):
        events = list(self.state["metric_events"])
        index = 0
        if "LOWER(COALESCE(username, '')) LIKE %s OR LOWER(COALESCE(path, '')) LIKE %s" in normalized:
            pattern = str(params[index]).strip("%")
            index += 2
            events = [
                item for item in events
                if pattern in str(item["username"] or "").lower() or pattern in str(item["path"] or "").lower()
            ]
        if "LOWER(event_type) = %s" in normalized:
            event_type = str(params[index]).lower()
            index += 1
            events = [item for item in events if str(item["event_type"] or "").lower() == event_type]
        if "status_code IS NOT NULL AND status_code >= 400" in normalized:
            events = [item for item in events if item["status_code"] is not None and int(item["status_code"]) >= 400]
        limit = int(params[-1]) if params else 50
        events.sort(key=lambda item: item["id"], reverse=True)
        return events[:limit]

    def _recent_events(self, normalized: str, params):
        rows = [
            {
                "created_at": item["created_at"],
                "username": item["username"],
                "server_code": item["server_code"],
                "event_type": item["event_type"],
                "path": item["path"],
                "method": item["method"],
                "status_code": item["status_code"],
                "duration_ms": item["duration_ms"],
                "request_bytes": item["request_bytes"],
                "response_bytes": item["response_bytes"],
                "resource_units": item["resource_units"],
                "meta_json": item["meta_json"],
            }
            for item in self._filtered_events(normalized, params)
        ]
        return FakeCursor(rowcount=len(rows), rows=rows)

    def _totals(self):
        events = self.state["metric_events"]
        api_events = [item for item in events if item["event_type"] == "api_request"]
        return FakeCursor(
            rowcount=1,
            one={
                "total_events": len(events),
                "api_requests_total": len(api_events),
                "complaints_total": sum(1 for item in events if item["event_type"] == "complaint_generated"),
                "rehab_total": sum(1 for item in events if item["event_type"] == "rehab_generated"),
                "ai_suggest_total": sum(1 for item in events if item["event_type"] == "ai_suggest"),
                "ai_ocr_total": sum(1 for item in events if item["event_type"] == "ai_extract_principal"),
                "request_bytes_total": sum(int(item["request_bytes"] or 0) for item in events),
                "response_bytes_total": sum(int(item["response_bytes"] or 0) for item in events),
                "resource_units_total": sum(int(item["resource_units"] or 0) for item in events),
                "avg_api_duration_ms": (
                    sum(int(item["duration_ms"] or 0) for item in api_events) / len(api_events)
                    if api_events else 0
                ),
                "events_last_24h": len(events),
            },
        )

    def _top_endpoints(self):
        counts = {}
        for item in self.state["metric_events"]:
            if item["event_type"] == "api_request" and item["path"]:
                counts[item["path"]] = counts.get(item["path"], 0) + 1
        rows = [
            {"path": path, "count": count}
            for path, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
        ][:10]
        return FakeCursor(rowcount=len(rows), rows=rows)

    def _user_metrics(self):
        grouped = {}
        for item in self.state["metric_events"]:
            username = str(item["username"] or "")
            if not username:
                continue
            row = grouped.setdefault(
                username,
                {
                    "username": username,
                    "server_code": item["server_code"],
                    "api_requests": 0,
                    "complaints": 0,
                    "rehabs": 0,
                    "ai_suggestions": 0,
                    "ai_ocr_requests": 0,
                    "request_bytes": 0,
                    "response_bytes": 0,
                    "resource_units": 0,
                    "last_seen_at": "",
                },
            )
            row["server_code"] = row["server_code"] or item["server_code"]
            row["api_requests"] += 1 if item["event_type"] == "api_request" else 0
            row["complaints"] += 1 if item["event_type"] == "complaint_generated" else 0
            row["rehabs"] += 1 if item["event_type"] == "rehab_generated" else 0
            row["ai_suggestions"] += 1 if item["event_type"] == "ai_suggest" else 0
            row["ai_ocr_requests"] += 1 if item["event_type"] == "ai_extract_principal" else 0
            row["request_bytes"] += int(item["request_bytes"] or 0)
            row["response_bytes"] += int(item["response_bytes"] or 0)
            row["resource_units"] += int(item["resource_units"] or 0)
            row["last_seen_at"] = max(str(row["last_seen_at"] or ""), str(item["created_at"] or ""))
        return FakeCursor(rowcount=len(grouped), rows=list(grouped.values()))

    def _ai_exam_stats(self):
        rows = [
            {"event_type": item["event_type"], "meta_json": item["meta_json"]}
            for item in self.state["metric_events"]
            if item["event_type"] in {"ai_exam_scoring", "exam_import_score_failures", "exam_import_row_score_error"}
        ]
        return FakeCursor(rowcount=len(rows), rows=rows)

    def _latest_event(self, params):
        event_types = set(params)
        matches = [item for item in self.state["metric_events"] if item["event_type"] in event_types]
        if not matches:
            return FakeCursor(rowcount=0, one=None)
        item = sorted(matches, key=lambda row: row["id"], reverse=True)[0]
        return FakeCursor(
            rowcount=1,
            one={
                "created_at": item["created_at"],
                "username": item["username"],
                "server_code": item["server_code"],
                "event_type": item["event_type"],
                "path": item["path"],
                "status_code": item["status_code"],
                "meta_json": item["meta_json"],
            },
        )


class FakeExamAnswersPostgresBackend:
    def __init__(self):
        self._state = {"rows": [], "next_id": 1, "clock": 0}

    def connect(self):
        return FakeExamAnswersConnection(self._state)

    def healthcheck(self) -> dict[str, object]:
        return {"backend": "postgres", "ok": True}

    def map_exception(self, exc: Exception) -> Exception:
        from ogp_web.db.errors import DatabaseUnavailableError

        return DatabaseUnavailableError(str(exc))


class FakeExamAnswersConnection:
    def __init__(self, state):
        self.state = state

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None

    def execute(self, query: str, params=()):
        normalized = " ".join(query.split())

        if normalized.startswith("CREATE TABLE IF NOT EXISTS exam_answers"):
            return FakeCursor(rowcount=0)
        if normalized.startswith("CREATE UNIQUE INDEX IF NOT EXISTS idx_exam_answers_import_key"):
            return FakeCursor(rowcount=0)
        if normalized.startswith("CREATE INDEX IF NOT EXISTS idx_exam_answers_source_row_import_key"):
            return FakeCursor(rowcount=0)
        if normalized.startswith("CREATE INDEX IF NOT EXISTS idx_exam_answers_pending_scores"):
            return FakeCursor(rowcount=0)
        if normalized.startswith("SELECT id, source_row, submitted_at, full_name, discord_tag, passport, exam_format, question_g_score, exam_scores_json, average_score FROM exam_answers"):
            rows = [
                {
                    "id": row["id"],
                    "source_row": row["source_row"],
                    "submitted_at": row["submitted_at"],
                    "full_name": row["full_name"],
                    "discord_tag": row["discord_tag"],
                    "passport": row["passport"],
                    "exam_format": row["exam_format"],
                    "question_g_score": row["question_g_score"],
                    "exam_scores_json": row["exam_scores_json"],
                    "average_score": row["average_score"],
                }
                for row in sorted(self.state["rows"], key=lambda item: item["id"])
            ]
            return FakeCursor(rowcount=len(rows), rows=rows)
        if normalized == "SELECT MIN(source_row) AS min_source_row FROM exam_answers":
            values = [row["source_row"] for row in self.state["rows"]]
            return FakeCursor(rowcount=1, one={"min_source_row": min(values) if values else None})
        if normalized.startswith("UPDATE exam_answers SET import_key = %s WHERE id = %s"):
            import_key, row_id = params
            row = self._find_by_id(int(row_id))
            if row:
                row["import_key"] = import_key
            return FakeCursor(rowcount=1 if row else 0)
        if normalized.startswith("UPDATE exam_answers SET import_key = NULL, source_row = %s WHERE id = %s"):
            source_row, row_id = params
            row = self._find_by_id(int(row_id))
            if row:
                row["import_key"] = None
                row["source_row"] = int(source_row)
            return FakeCursor(rowcount=1 if row else 0)
        if normalized.startswith("SELECT id, source_row, import_key FROM exam_answers"):
            rows = [{"id": row["id"], "source_row": row["source_row"], "import_key": row["import_key"]} for row in self.state["rows"]]
            return FakeCursor(rowcount=len(rows), rows=rows)
        if normalized.startswith("UPDATE exam_answers SET source_row = %s WHERE id = %s"):
            source_row, row_id = params
            row = self._find_by_id(int(row_id))
            if row:
                row["source_row"] = int(source_row)
            return FakeCursor(rowcount=1 if row else 0)
        if normalized.startswith("SELECT id, source_row, submitted_at, full_name, discord_tag, passport, exam_format, payload_json, answer_count FROM exam_answers WHERE import_key = %s"):
            row = self._find_by_import_key(str(params[0]))
            return FakeCursor(
                rowcount=1 if row else 0,
                one={
                    "id": row["id"],
                    "source_row": row["source_row"],
                    "submitted_at": row["submitted_at"],
                    "full_name": row["full_name"],
                    "discord_tag": row["discord_tag"],
                    "passport": row["passport"],
                    "exam_format": row["exam_format"],
                    "payload_json": row["payload_json"],
                    "answer_count": row["answer_count"],
                } if row else None,
            )
        if normalized.startswith("SELECT id, source_row, submitted_at, full_name, discord_tag, passport, exam_format, payload_json, answer_count, import_key FROM exam_answers WHERE submitted_at = %s"):
            submitted_at = str(params[0])
            rows = [
                {
                    "id": row["id"],
                    "source_row": row["source_row"],
                    "submitted_at": row["submitted_at"],
                    "full_name": row["full_name"],
                    "discord_tag": row["discord_tag"],
                    "passport": row["passport"],
                    "exam_format": row["exam_format"],
                    "payload_json": row["payload_json"],
                    "answer_count": row["answer_count"],
                    "import_key": row["import_key"],
                }
                for row in self.state["rows"]
                if row["submitted_at"] == submitted_at
            ]
            return FakeCursor(rowcount=len(rows), rows=rows)
        if normalized.startswith("INSERT INTO exam_answers ( source_row, submitted_at, full_name, discord_tag, passport, exam_format, payload_json, answer_count, needs_rescore, import_key ) VALUES"):
            return self._insert_row(params)
        if normalized.startswith("UPDATE exam_answers SET source_row = %s, submitted_at = %s, full_name = %s, discord_tag = %s, passport = %s, exam_format = %s, payload_json = %s::jsonb, answer_count = %s, updated_at = NOW() WHERE id = %s"):
            return self._update_row_preserve_scores(params)
        if normalized.startswith("UPDATE exam_answers SET source_row = %s, submitted_at = %s, full_name = %s, discord_tag = %s, passport = %s, exam_format = %s, payload_json = %s::jsonb, answer_count = %s, question_g_score = NULL, question_g_rationale = NULL, question_g_scored_at = NULL, exam_scores_json = NULL, exam_scores_scored_at = NULL, average_score = NULL, average_score_answer_count = NULL, average_score_scored_at = NULL, needs_rescore = %s, updated_at = NOW() WHERE id = %s"):
            return self._update_row(params)
        if normalized.startswith("SELECT COUNT(*) AS total FROM exam_answers WHERE source_row > 0"):
            total = sum(1 for row in self.state["rows"] if row["source_row"] > 0)
            return FakeCursor(rowcount=1, one={"total": total})
        if normalized.startswith("SELECT source_row, submitted_at, full_name, discord_tag, passport, exam_format, answer_count, average_score, COALESCE(average_score_answer_count, 0) AS average_score_answer_count, needs_rescore, imported_at FROM exam_answers WHERE source_row > 0 ORDER BY source_row DESC LIMIT %s"):
            return self._list_entries(int(params[0]))
        if normalized.startswith("SELECT source_row, submitted_at, full_name, discord_tag, passport, exam_format, answer_count, average_score, average_score_answer_count, imported_at FROM exam_answers WHERE source_row > 0 AND (average_score IS NULL OR needs_rescore = 1) ORDER BY source_row ASC LIMIT %s") or normalized.startswith("SELECT source_row, submitted_at, full_name, discord_tag, passport, exam_format, answer_count, average_score, average_score_answer_count, imported_at FROM exam_answers WHERE source_row > 0 AND (average_score IS NULL OR needs_rescore IS TRUE) ORDER BY source_row ASC LIMIT %s"):
            rows = [row for row in self.state["rows"] if row["source_row"] > 0 and (row["average_score"] is None or bool(row["needs_rescore"]))]
            rows.sort(key=lambda item: item["source_row"])
            rows = rows[: int(params[0])]
            return FakeCursor(rowcount=len(rows), rows=[self._summary_row(row) for row in rows])
        if normalized.startswith("SELECT source_row, submitted_at, full_name, discord_tag, passport, exam_format, answer_count, average_score, COALESCE(average_score_answer_count, 0) AS average_score_answer_count, needs_rescore, imported_at, exam_scores_json FROM exam_answers WHERE source_row > 0 AND exam_scores_json IS NOT NULL AND exam_scores_json <> '' ORDER BY source_row ASC LIMIT %s"):
            rows = [row for row in self.state["rows"] if row["source_row"] > 0 and row["exam_scores_json"] not in (None, "")]
            rows.sort(key=lambda item: item["source_row"])
            rows = rows[: int(params[0])]
            return FakeCursor(rowcount=len(rows), rows=[{**self._summary_row(row), "exam_scores_json": row["exam_scores_json"]} for row in rows])
        if normalized.startswith("SELECT source_row, submitted_at, full_name, discord_tag, passport, exam_format, answer_count, imported_at, updated_at, question_g_score, question_g_rationale, question_g_scored_at, exam_scores_json, exam_scores_scored_at, average_score, average_score_answer_count, average_score_scored_at, needs_rescore, payload_json FROM exam_answers WHERE source_row = %s AND source_row > 0"):
            row = self._find_by_source_row(int(params[0]))
            return FakeCursor(rowcount=1 if row else 0, one=self._detail_row(row) if row else None)
        if normalized.startswith("UPDATE exam_answers SET question_g_score = %s, question_g_rationale = %s, question_g_scored_at = NOW() WHERE source_row = %s"):
            score, rationale, source_row = params
            row = self._find_by_source_row(int(source_row))
            if row:
                row["question_g_score"] = int(score)
                row["question_g_rationale"] = str(rationale)
                row["question_g_scored_at"] = self._now()
            return FakeCursor(rowcount=1 if row else 0)
        if normalized.startswith("UPDATE exam_answers SET exam_scores_json = %s::jsonb, exam_scores_scored_at = NOW(), average_score = %s, average_score_answer_count = %s, average_score_scored_at = NOW(), needs_rescore = %s WHERE source_row = %s"):
            return self._save_scores(params)

        raise AssertionError(f"Unsupported fake exam answers query: {normalized}")

    def _now(self) -> str:
        self.state["clock"] += 1
        return f"2026-04-10T00:00:{self.state['clock']:02d}Z"

    def _find_by_id(self, row_id: int):
        return next((row for row in self.state["rows"] if row["id"] == row_id), None)

    def _find_by_import_key(self, import_key: str):
        return next((row for row in self.state["rows"] if row["import_key"] == import_key), None)

    def _find_by_source_row(self, source_row: int):
        return next((row for row in self.state["rows"] if row["source_row"] == source_row), None)

    def _insert_row(self, params):
        source_row, submitted_at, full_name, discord_tag, passport, exam_format, payload_json, answer_count, needs_rescore, import_key = params
        row = {
            "id": self.state["next_id"],
            "source_row": int(source_row),
            "submitted_at": str(submitted_at),
            "full_name": str(full_name),
            "discord_tag": str(discord_tag),
            "passport": str(passport),
            "exam_format": str(exam_format),
            "payload_json": payload_json,
            "answer_count": int(answer_count),
            "imported_at": self._now(),
            "updated_at": self._now(),
            "question_g_score": None,
            "question_g_rationale": None,
            "question_g_scored_at": None,
            "exam_scores_json": None,
            "exam_scores_scored_at": None,
            "average_score": None,
            "average_score_answer_count": None,
            "average_score_scored_at": None,
            "needs_rescore": bool(needs_rescore),
            "import_key": str(import_key),
        }
        self.state["rows"].append(row)
        self.state["next_id"] += 1
        return FakeCursor(rowcount=1)

    def _update_row(self, params):
        source_row, submitted_at, full_name, discord_tag, passport, exam_format, payload_json, answer_count, needs_rescore, row_id = params
        row = self._find_by_id(int(row_id))
        if not row:
            return FakeCursor(rowcount=0)
        row.update(
            {
                "source_row": int(source_row),
                "submitted_at": str(submitted_at),
                "full_name": str(full_name),
                "discord_tag": str(discord_tag),
                "passport": str(passport),
                "exam_format": str(exam_format),
                "payload_json": payload_json,
                "answer_count": int(answer_count),
                "question_g_score": None,
                "question_g_rationale": None,
                "question_g_scored_at": None,
                "exam_scores_json": None,
                "exam_scores_scored_at": None,
                "average_score": None,
                "average_score_answer_count": None,
                "average_score_scored_at": None,
                "needs_rescore": bool(needs_rescore),
                "updated_at": self._now(),
            }
        )
        return FakeCursor(rowcount=1)

    def _update_row_preserve_scores(self, params):
        source_row, submitted_at, full_name, discord_tag, passport, exam_format, payload_json, answer_count, row_id = params
        row = self._find_by_id(int(row_id))
        if not row:
            return FakeCursor(rowcount=0)
        row.update(
            {
                "source_row": int(source_row),
                "submitted_at": str(submitted_at),
                "full_name": str(full_name),
                "discord_tag": str(discord_tag),
                "passport": str(passport),
                "exam_format": str(exam_format),
                "payload_json": payload_json,
                "answer_count": int(answer_count),
                "updated_at": self._now(),
            }
        )
        return FakeCursor(rowcount=1)

    def _summary_row(self, row):
        return {
            "source_row": row["source_row"],
            "submitted_at": row["submitted_at"],
            "full_name": row["full_name"],
            "discord_tag": row["discord_tag"],
            "passport": row["passport"],
            "exam_format": row["exam_format"],
            "answer_count": row["answer_count"],
            "average_score": row["average_score"],
            "average_score_answer_count": row["average_score_answer_count"] or 0,
            "needs_rescore": row["needs_rescore"],
            "imported_at": row["imported_at"],
        }

    def _detail_row(self, row):
        return {
            **self._summary_row(row),
            "updated_at": row["updated_at"],
            "question_g_score": row["question_g_score"],
            "question_g_rationale": row["question_g_rationale"],
            "question_g_scored_at": row["question_g_scored_at"],
            "exam_scores_json": row["exam_scores_json"],
            "exam_scores_scored_at": row["exam_scores_scored_at"],
            "average_score_scored_at": row["average_score_scored_at"],
            "payload_json": row["payload_json"],
        }

    def _list_entries(self, limit: int):
        rows = [row for row in self.state["rows"] if row["source_row"] > 0]
        rows.sort(key=lambda item: item["source_row"], reverse=True)
        rows = rows[:limit]
        return FakeCursor(rowcount=len(rows), rows=[self._summary_row(row) for row in rows])

    def _save_scores(self, params):
        exam_scores_json, average_score, average_score_answer_count, needs_rescore, source_row = params
        row = self._find_by_source_row(int(source_row))
        if not row:
            return FakeCursor(rowcount=0)
        row["exam_scores_json"] = exam_scores_json
        row["exam_scores_scored_at"] = self._now()
        row["average_score"] = average_score
        row["average_score_answer_count"] = average_score_answer_count
        row["average_score_scored_at"] = self._now()
        row["needs_rescore"] = bool(needs_rescore)
        return FakeCursor(rowcount=1)


class FakeExamImportTasksPostgresBackend:
    def __init__(self):
        self._state = {"rows": {}}

    def connect(self):
        return FakeExamImportTasksConnection(self._state)

    def healthcheck(self) -> dict[str, object]:
        return {"backend": "postgres", "ok": True}

    def map_exception(self, exc: Exception) -> Exception:
        from ogp_web.db.errors import DatabaseUnavailableError

        return DatabaseUnavailableError(str(exc))


class FakeExamImportTasksConnection:
    def __init__(self, state):
        self.state = state

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None

    def execute(self, query: str, params=()):
        normalized = " ".join(query.split())

        if normalized.startswith("CREATE TABLE IF NOT EXISTS exam_import_tasks"):
            return FakeCursor(rowcount=0)
        if normalized.startswith("CREATE INDEX IF NOT EXISTS idx_exam_import_tasks_created_at"):
            return FakeCursor(rowcount=0)
        if normalized.startswith("UPDATE exam_import_tasks SET status = 'failed', finished_at = %s, error = CASE"):
            changed = 0
            finished_at = params[0]
            for row in self.state["rows"].values():
                if row["status"] in {"queued", "running"}:
                    row["status"] = "failed"
                    row["finished_at"] = finished_at
                    if not row["error"]:
                        row["error"] = "Сервис был перезапущен до завершения задачи."
                    changed += 1
            return FakeCursor(rowcount=changed)
        if normalized.startswith("INSERT INTO exam_import_tasks ( id, task_type, source_row, status, created_at, started_at, finished_at, error, progress_json, result_json ) VALUES"):
            row = {
                "id": params[0],
                "task_type": params[1],
                "source_row": params[2],
                "status": params[3],
                "created_at": params[4],
                "started_at": params[5],
                "finished_at": params[6],
                "error": params[7],
                "progress_json": json.loads(params[8]),
                "result_json": json.loads(params[9]),
            }
            self.state["rows"][row["id"]] = row
            return FakeCursor(rowcount=1)
        if normalized.startswith("SELECT id, task_type, source_row, status, created_at, started_at, finished_at, error, progress_json, result_json FROM exam_import_tasks WHERE id = %s"):
            row = self.state["rows"].get(params[0])
            return FakeCursor(rowcount=1 if row else 0, one=row)
        if normalized.startswith("SELECT COUNT(*) AS active_count FROM exam_import_tasks WHERE status = %s"):
            status = str(params[0])
            active_count = sum(1 for row in self.state["rows"].values() if str(row.get("status") or "") == status)
            return FakeCursor(rowcount=1, one={"active_count": active_count})
        if normalized.startswith("UPDATE exam_import_tasks SET "):
            task_id = params[-1]
            row = self.state["rows"].get(task_id)
            if row is None:
                return FakeCursor(rowcount=0)
            assignments = normalized.split(" SET ", 1)[1].split(" WHERE ", 1)[0].split(", ")
            for assignment, value in zip(assignments, params[:-1]):
                column = assignment.split(" = ", 1)[0]
                if column in {"progress_json", "result_json"}:
                    row[column] = json.loads(value)
                else:
                    row[column] = value
            return FakeCursor(rowcount=1)

        raise AssertionError(f"Unsupported fake exam import tasks query: {normalized}")


class WebStorageTests(unittest.TestCase):
    def test_register_confirm_authenticate_and_profile_roundtrip(self):
        tmpdir = make_temp_dir()
        try:
            root = Path(tmpdir)
            store = UserStore(root / "app.db", root / "users.json", repository=UserRepository(SQLiteBackend(root / "app.db")))

            user, token = store.register("tester", "tester@example.com", "Password123!")
            self.assertEqual(user.username, "tester")
            self.assertTrue(token)

            confirmed = store.confirm_email(token)
            self.assertEqual(confirmed.email, "tester@example.com")

            authenticated = store.authenticate("tester@example.com", "Password123!")
            self.assertEqual(authenticated.username, "tester")

            saved = store.save_representative_profile(
                "tester",
                {
                    "name": "Rep",
                    "passport": "AA",
                    "address": "Addr",
                    "phone": "1234567",
                    "discord": "disc",
                    "passport_scan_url": "https://example.com/id",
                },
            )
            self.assertEqual(saved["name"], "Rep")

            loaded = store.get_representative_profile("tester")
            self.assertEqual(loaded["passport"], "AA")
        finally:
            store.repository.close()
            del store
            gc.collect()
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_unverified_user_cannot_authenticate(self):
        tmpdir = make_temp_dir()
        try:
            root = Path(tmpdir)
            store = UserStore(root / "custom.db", root / "users.json", repository=UserRepository(SQLiteBackend(root / "custom.db")))
            user, _ = store.register("tester2", "tester2@example.com", "Password123!")
            self.assertEqual(user.username, "tester2")

            with self.assertRaisesRegex(Exception, "подтвердите email"):
                store.authenticate("tester2", "Password123!")
        finally:
            store.repository.close()
            del store
            gc.collect()
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_password_can_be_reset_with_token(self):
        tmpdir = make_temp_dir()
        try:
            root = Path(tmpdir)
            store = UserStore(root / "reset.db", root / "users.json", repository=UserRepository(SQLiteBackend(root / "reset.db")))
            _, verify_token = store.register("resetuser", "reset@example.com", "Password123!")
            store.confirm_email(verify_token)

            _, reset_token = store.issue_password_reset_token("reset@example.com")
            user = store.reset_password(reset_token, "NewPassword456!")
            self.assertEqual(user.username, "resetuser")

            authenticated = store.authenticate("reset@example.com", "NewPassword456!")
            self.assertEqual(authenticated.username, "resetuser")
        finally:
            store.repository.close()
            del store
            gc.collect()
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_exam_answers_store_imports_only_new_rows_by_import_key(self):
        tmpdir = make_temp_dir()
        try:
            root = Path(tmpdir)
            store = ExamAnswersStore(root / "exam_answers.db", backend=SQLiteBackend(root / "exam_answers.db"))
            first = {
                "source_row": 2,
                "submitted_at": "2026-04-08 12:00:00",
                "full_name": "First User",
                "discord_tag": "first",
                "passport": "123456",
                "exam_format": "Очно",
                "payload": {"name": "First User"},
                "answer_count": 10,
            }
            duplicate = {
                "source_row": 2,
                "submitted_at": "2026-04-08 12:00:01",
                "full_name": "Updated User",
                "discord_tag": "updated",
                "passport": "654321",
                "exam_format": "Дистанционно",
                "payload": {"name": "Updated User"},
                "answer_count": 12,
            }

            first_result = store.import_rows([first])
            duplicate_result = store.import_rows([duplicate])
            entries = store.list_entries(limit=5)

            self.assertEqual(first_result["inserted_count"], 1)
            self.assertEqual(duplicate_result["inserted_count"], 1)
            self.assertEqual(duplicate_result["updated_count"], 0)
            self.assertEqual(duplicate_result["skipped_count"], 0)
            self.assertEqual(store.count(), 1)
            self.assertEqual(entries[0]["full_name"], "Updated User")
            self.assertEqual(entries[0]["passport"], "654321")
            self.assertEqual(entries[0]["answer_count"], 12)

            detailed = store.get_entry(2)
            self.assertIsNotNone(detailed)
            self.assertEqual(detailed["payload"]["name"], "Updated User")

            store.save_exam_scores(
                2,
                [
                    {"column": "F", "score": 80},
                    {"column": "G", "score": 100},
                    {"column": "H", "score": None},
                ],
            )
            rescored = store.get_entry(2)
            self.assertEqual(rescored["average_score"], 90.0)
            self.assertEqual(rescored["average_score_answer_count"], 2)
            self.assertEqual(rescored["needs_rescore"], 0)

            store.save_exam_scores(
                2,
                [
                    {
                        "column": "F",
                        "score": 1,
                        "rationale": "Модель не вернула корректную оценку по этому пункту.",
                    }
                ],
            )
            rescored_again = store.get_entry(2)
            self.assertEqual(rescored_again["needs_rescore"], 1)
        finally:
            del store
            gc.collect()
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_exam_answers_store_reconciles_shifted_source_rows(self):
        tmpdir = make_temp_dir()
        try:
            root = Path(tmpdir)
            store = ExamAnswersStore(root / "exam_answers.db", backend=SQLiteBackend(root / "exam_answers.db"))
            old_rows = [
                {
                    "source_row": 14,
                    "submitted_at": "02.06.2025 14:19:59",
                    "full_name": "Philip Mactavish",
                    "discord_tag": "rumit_gof",
                    "passport": "384908",
                    "exam_format": "Государственный адвокат",
                    "payload": {"name": "Philip Mactavish"},
                    "answer_count": 10,
                },
                {
                    "source_row": 15,
                    "submitted_at": "02.06.2025 14:19:59",
                    "full_name": "Philip Mactavish",
                    "discord_tag": "rumit_gof",
                    "passport": "384908",
                    "exam_format": "Государственный адвокат",
                    "payload": {"name": "Philip Mactavish"},
                    "answer_count": 10,
                },
            ]
            store.import_rows(old_rows)

            result = store.import_rows(
                [
                    {
                        "source_row": 14,
                        "submitted_at": "09.04.2026 19:12:41",
                        "full_name": "Ryota Experience",
                        "discord_tag": "popka2333",
                        "passport": "488495",
                        "exam_format": "Получение лицензии адвоката",
                        "payload": {"name": "Ryota Experience"},
                        "answer_count": 10,
                    }
                ]
            )

            self.assertEqual(result["inserted_count"], 1)
            self.assertEqual(result["total_rows"], 1)
            active_entries = store.list_entries(limit=10)
            self.assertEqual(len(active_entries), 1)
            self.assertEqual(active_entries[0]["full_name"], "Ryota Experience")
            self.assertIsNotNone(store.get_entry(14))
            self.assertEqual(store.get_entry(14)["full_name"], "Ryota Experience")
            self.assertIsNone(store.get_entry(15))
        finally:
            del store
            gc.collect()
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_exam_answers_store_preserves_scores_when_identity_fields_change_but_answers_match(self):
        tmpdir = make_temp_dir()
        try:
            root = Path(tmpdir)
            store = ExamAnswersStore(root / "exam_answers.db", backend=SQLiteBackend(root / "exam_answers.db"))
            original = {
                "source_row": 2,
                "submitted_at": "2026-04-08 12:00:00",
                "full_name": "Student One",
                "discord_tag": "student1",
                "passport": "111111",
                "exam_format": "remote",
                "payload": {
                    "submitted_at": "2026-04-08 12:00:00",
                    "full_name": "Student One",
                    "discord_tag": "student1",
                    "passport": "111111",
                    "exam_format": "remote",
                    "Question F": "Answer F",
                    "Question G": "Answer G",
                },
                "answer_count": 2,
            }
            updated = {
                "source_row": 3,
                "submitted_at": "2026-04-08 12:00:00",
                "full_name": "Student One Updated",
                "discord_tag": "student1_new",
                "passport": "999999",
                "exam_format": "remote",
                "payload": {
                    "submitted_at": "2026-04-08 12:00:00",
                    "full_name": "Student One Updated",
                    "discord_tag": "student1_new",
                    "passport": "999999",
                    "exam_format": "remote",
                    "Question F": "Answer F",
                    "Question G": "Answer G",
                },
                "answer_count": 2,
            }

            store.import_rows([original])
            store.save_exam_scores(
                2,
                [
                    {"column": "F", "score": 80},
                    {"column": "G", "score": 100},
                ],
            )

            result = store.import_rows([updated])
            rescored = store.get_entry(3)

            self.assertEqual(result["inserted_count"], 0)
            self.assertEqual(result["updated_count"], 1)
            self.assertIsNone(store.get_entry(2))
            self.assertIsNotNone(rescored)
            self.assertEqual(rescored["full_name"], "Student One Updated")
            self.assertEqual(rescored["passport"], "999999")
            self.assertEqual(rescored["average_score"], 90.0)
            self.assertEqual(rescored["average_score_answer_count"], 2)
            self.assertEqual(rescored["needs_rescore"], 0)
            self.assertEqual(len(store.list_entries_needing_scores(limit=10)), 0)
        finally:
            del store
            gc.collect()
            shutil.rmtree(tmpdir, ignore_errors=True)


class PostgresUserStoreTests(unittest.TestCase):
    def make_store(self) -> UserStore:
        tmpdir = make_temp_dir()
        self.addCleanup(shutil.rmtree, tmpdir, True)
        root = Path(tmpdir)
        repository = UserRepository(PostgresBackend())
        store = UserStore(root / "app.db", root / "users.json", repository=repository)
        self.addCleanup(repository.close)
        return store

    def test_postgres_register_confirm_auth_profile_and_draft_roundtrip(self):
        store = self.make_store()

        user, token = store.register("tester_pg", "tester_pg@example.com", "Password123!")
        self.assertEqual(user.server_code, "blackberry")

        with self.assertRaises(AuthError):
            store.authenticate("tester_pg@example.com", "Password123!")

        confirmed = store.confirm_email(token)
        self.assertEqual(confirmed.email, "tester_pg@example.com")

        authenticated = store.authenticate("tester_pg@example.com", "Password123!")
        self.assertEqual(authenticated.username, "tester_pg")

        saved_profile = store.save_representative_profile(
            "tester_pg",
            {
                "name": "Rep PG",
                "passport": "AA 123",
                "address": "Moscow",
                "phone": "1234567",
                "discord": "rep.pg",
                "passport_scan_url": "https://example.com/pg-id",
            },
        )
        self.assertEqual(saved_profile["name"], "Rep PG")
        self.assertEqual(store.get_representative_profile("tester_pg")["passport"], "AA 123")

        saved_draft = store.save_complaint_draft("tester_pg", {"summary": "draft text"})
        self.assertEqual(saved_draft["draft"]["summary"], "draft text")
        self.assertTrue(saved_draft["updated_at"])

        store.clear_complaint_draft("tester_pg")
        self.assertEqual(store.get_complaint_draft("tester_pg")["draft"], {})

    def test_postgres_reset_password_and_admin_role_flags(self):
        store = self.make_store()

        _, verify_token = store.register("roles_pg", "roles_pg@example.com", "Password123!")
        store.confirm_email(verify_token)

        _, reset_token = store.issue_password_reset_token("roles_pg@example.com")
        reset_user = store.reset_password(reset_token, "NewPassword456!")
        self.assertEqual(reset_user.username, "roles_pg")
        self.assertEqual(store.authenticate("roles_pg@example.com", "NewPassword456!").username, "roles_pg")

        tester_row = store.admin_set_tester_status("roles_pg", True)
        gka_row = store.admin_set_gka_status("roles_pg", True)
        self.assertTrue(tester_row["is_tester"])
        self.assertTrue(gka_row["is_gka"])
        self.assertTrue(store.is_tester_user("roles_pg", server_code="blackberry"))
        self.assertTrue(store.is_gka_user("roles_pg", server_code="blackberry"))

        listed = store.list_users()
        self.assertEqual(len(listed), 1)
        self.assertTrue(listed[0]["is_tester"])
        self.assertTrue(listed[0]["is_gka"])

    def test_postgres_access_block_and_email_admin_flow(self):
        store = self.make_store()

        _, verify_token = store.register("admin_pg", "admin_pg@example.com", "Password123!")
        store.confirm_email(verify_token)

        blocked = store.admin_set_access_blocked("admin_pg", "manual block")
        self.assertEqual(blocked["access_blocked_reason"], "manual block")
        self.assertTrue(store.is_access_blocked("admin_pg"))

        with self.assertRaises(AuthError):
            store.authenticate("admin_pg@example.com", "Password123!")

        cleared = store.admin_clear_access_blocked("admin_pg")
        self.assertFalse(bool(cleared["access_blocked_at"]))

        updated = store.admin_update_email("admin_pg", "admin_pg_new@example.com")
        self.assertEqual(updated["email"], "admin_pg_new@example.com")

        admin_reset = store.admin_reset_password("admin_pg", "AdminReset789!")
        self.assertEqual(admin_reset["username"], "admin_pg")

        verify_row, _ = store.issue_email_verification_token("admin_pg_new@example.com")
        self.assertEqual(verify_row.username, "admin_pg")
        verified = store.admin_mark_email_verified("admin_pg")
        self.assertTrue(verified["email_verified_at"])
        self.assertEqual(store.authenticate("admin_pg_new@example.com", "AdminReset789!").username, "admin_pg")

    def test_postgres_healthcheck_reports_missing_required_tables(self):
        repository = UserRepository(PostgresBackend(missing_tables={"complaint_drafts"}))
        store = UserStore(Path("ignored.db"), Path("ignored.json"), repository=repository)
        try:
            details = store.healthcheck()
        finally:
            repository.close()

        self.assertFalse(details["ok"])
        self.assertFalse(details["schema_ok"])
        self.assertIn("complaint_drafts", details["missing_tables"])


class RateLimiterHealthTests(unittest.TestCase):
    def test_healthcheck_reports_in_memory_fallback_after_storage_failure(self):
        class BrokenConnection:
            def execute(self, query: str, params=()):
                raise RuntimeError("db write failed")

            def commit(self) -> None:
                return None

            def rollback(self) -> None:
                return None

            def close(self) -> None:
                return None

        class BrokenBackend:
            def connect(self):
                return BrokenConnection()

            def healthcheck(self) -> dict[str, object]:
                return {"backend": "postgres", "ok": True}

            def map_exception(self, exc: Exception) -> Exception:
                return exc

        limiter = PersistentRateLimiter(BrokenBackend())
        limiter.check("127.0.0.1", 5, 60, action="login")
        details = limiter.healthcheck()

        self.assertFalse(details["ok"])
        self.assertEqual(details["storage"], "in-memory-fallback")
        self.assertIn("fallback_reason", details)


class PostgresAdminMetricsStoreTests(unittest.TestCase):
    def make_store(self) -> AdminMetricsStore:
        tmpdir = make_temp_dir()
        self.addCleanup(shutil.rmtree, tmpdir, True)
        root = Path(tmpdir)
        return AdminMetricsStore(root / "admin_metrics.db", backend=FakeAdminMetricsPostgresBackend())

    def test_summarize_ai_generation_logs_keeps_backward_compatibility_with_stage_timings(self):
        tmpdir = make_temp_dir()
        self.addCleanup(shutil.rmtree, tmpdir, True)
        root = Path(tmpdir)
        store = AdminMetricsStore(root / "admin_metrics.db", backend=SQLiteBackend(root / "admin_metrics.db"))

        self.assertTrue(
            store.log_ai_generation(
                username="alpha",
                server_code="blackberry",
                flow="suggest",
                generation_id="gen_old",
                path="/api/ai/suggest",
                meta={
                    "model": "gpt-5-mini",
                    "input_tokens": 100,
                    "output_tokens": 40,
                    "total_tokens": 140,
                    "latency_ms": 180,
                },
            )
        )
        self.assertTrue(
            store.log_ai_generation(
                username="alpha",
                server_code="blackberry",
                flow="suggest",
                generation_id="gen_new",
                path="/api/ai/suggest",
                meta={
                    "model": "gpt-5-mini",
                    "input_tokens": 160,
                    "output_tokens": 55,
                    "total_tokens": 215,
                    "latency_ms": 170,
                    "retrieval_ms": 22,
                    "openai_ms": 170,
                    "total_suggest_ms": 205,
                    "estimated_cost_usd": 0.0012,
                },
            )
        )

        summary = store.summarize_ai_generation_logs(flow="suggest", limit=10)

        self.assertEqual(summary["total_generations"], 2)
        self.assertEqual(summary["input_tokens_total"], 260)
        self.assertEqual(summary["output_tokens_total"], 95)
        self.assertEqual(summary["total_tokens_total"], 355)
        self.assertEqual(summary["latency_ms_p50"], 175)
        self.assertEqual(summary["latency_ms_p95"], 180)
        self.assertEqual(summary["retrieval_ms_p50"], 22)
        self.assertEqual(summary["retrieval_ms_p95"], 22)
        self.assertEqual(summary["openai_ms_p50"], 170)
        self.assertEqual(summary["openai_ms_p95"], 170)
        self.assertEqual(summary["total_suggest_ms_p50"], 205)
        self.assertEqual(summary["total_suggest_ms_p95"], 205)
        self.assertEqual(summary["estimated_cost_samples"], 1)
        self.assertEqual(summary["estimated_cost_total_usd"], 0.0012)

    def test_list_ai_generation_logs_supports_context_and_guard_filters(self):
        tmpdir = make_temp_dir()
        self.addCleanup(shutil.rmtree, tmpdir, True)
        root = Path(tmpdir)
        store = AdminMetricsStore(root / "admin_metrics.db", backend=SQLiteBackend(root / "admin_metrics.db"))

        store.log_ai_generation(
            username="alpha",
            server_code="blackberry",
            flow="suggest",
            generation_id="gen_low",
            path="/api/ai/suggest",
            meta={
                "retrieval_context_mode": "low_confidence_context",
                "guard_warnings": ["suggest_low_confidence_context"],
            },
        )
        store.log_ai_generation(
            username="alpha",
            server_code="blackberry",
            flow="suggest",
            generation_id="gen_normal",
            path="/api/ai/suggest",
            meta={
                "retrieval_context_mode": "normal_context",
                "guard_warnings": [],
            },
        )

        low_context_only = store.list_ai_generation_logs(
            flow="suggest",
            retrieval_context_mode="low_confidence_context",
            limit=10,
        )
        self.assertEqual(len(low_context_only), 1)
        self.assertEqual(low_context_only[0]["meta"]["generation_id"], "gen_low")

        with_guard_warning = store.list_ai_generation_logs(
            flow="suggest",
            guard_warning="suggest_low_confidence_context",
            limit=10,
        )
        self.assertEqual(len(with_guard_warning), 1)
        self.assertEqual(with_guard_warning[0]["meta"]["generation_id"], "gen_low")

    def test_postgres_admin_metrics_store_logs_overview_and_csv(self):
        store = self.make_store()

        self.assertTrue(
            store.log_event(
                event_type="api_request",
                username="alpha",
                server_code="blackberry",
                path="/api/test",
                method="POST",
                status_code=200,
                duration_ms=120,
                request_bytes=50,
                response_bytes=200,
                resource_units=3,
                meta={"trace": "one"},
            )
        )
        self.assertTrue(
            store.log_event(
                event_type="complaint_generated",
                username="alpha",
                server_code="blackberry",
                path="/api/generate",
                method="POST",
                status_code=200,
                resource_units=5,
                meta={"kind": "complaint"},
            )
        )
        self.assertTrue(
            store.log_event(
                event_type="ai_exam_scoring",
                username="alpha",
                server_code="blackberry",
                path="/api/exam-import/score",
                method="POST",
                status_code=200,
                meta={
                    "rows_scored": 2,
                    "answer_count": 8,
                    "heuristic_count": 2,
                    "cache_hit_count": 1,
                    "llm_count": 4,
                    "llm_calls": 2,
                    "invalid_batch_item_count": 1,
                    "retry_batch_items": 1,
                    "retry_batch_calls": 1,
                    "retry_single_items": 1,
                    "retry_single_calls": 1,
                    "scoring_ms": 240,
                },
            )
        )
        self.assertTrue(
            store.log_event(
                event_type="exam_import_score_failures",
                username="alpha",
                server_code="blackberry",
                path="/api/exam-import/score",
                method="POST",
                status_code=200,
                meta={"scored_count": 0, "failed_count": 1, "failed_rows": [10]},
            )
        )

        overview = store.get_overview(
            users=[
                {
                    "username": "alpha",
                    "email": "alpha@example.com",
                    "created_at": "2026-04-10T00:00:00Z",
                    "email_verified_at": "2026-04-10T00:00:01Z",
                    "access_blocked_at": "",
                    "access_blocked_reason": "",
                    "is_tester": False,
                    "is_gka": True,
                }
            ]
        )
        self.assertEqual(overview["totals"]["events_total"], 4)
        self.assertEqual(overview["totals"]["complaints_total"], 1)
        self.assertEqual(overview["totals"]["ai_exam_scoring_total"], 1)
        self.assertEqual(overview["totals"]["ai_exam_scoring_rows"], 2)
        self.assertEqual(overview["totals"]["ai_exam_scoring_answers"], 8)
        self.assertEqual(overview["totals"]["ai_exam_heuristic_total"], 2)
        self.assertEqual(overview["totals"]["ai_exam_cache_total"], 1)
        self.assertEqual(overview["totals"]["ai_exam_llm_total"], 4)
        self.assertEqual(overview["totals"]["ai_exam_llm_calls_total"], 2)
        self.assertEqual(overview["totals"]["ai_exam_invalid_batch_items_total"], 1)
        self.assertEqual(overview["totals"]["ai_exam_retry_batch_items_total"], 1)
        self.assertEqual(overview["totals"]["ai_exam_retry_batch_calls_total"], 1)
        self.assertEqual(overview["totals"]["ai_exam_retry_single_items_total"], 1)
        self.assertEqual(overview["totals"]["ai_exam_retry_single_calls_total"], 1)
        self.assertEqual(overview["totals"]["ai_exam_failure_total"], 1)
        self.assertEqual(overview["totals"]["ai_exam_scoring_ms_p50"], 240)
        self.assertEqual(overview["totals"]["ai_exam_scoring_ms_p95"], 240)
        self.assertEqual(overview["users"][0]["api_requests"], 1)
        self.assertEqual(overview["users"][0]["complaints"], 1)
        self.assertEqual(overview["top_endpoints"][0]["path"], "/api/test")

        users_csv = store.export_users_csv(
            users=[
                {
                    "username": "alpha",
                    "email": "alpha@example.com",
                    "created_at": "2026-04-10T00:00:00Z",
                    "email_verified_at": "2026-04-10T00:00:01Z",
                    "access_blocked_at": "",
                    "access_blocked_reason": "",
                    "is_tester": False,
                    "is_gka": True,
                }
            ]
        )
        self.assertIn("alpha@example.com", users_csv)

        events_csv = store.export_events_csv()
        self.assertIn("created_at,username,event_type,path", events_csv)
        self.assertIn("/api/generate", events_csv)


class PostgresExamAnswersStoreTests(unittest.TestCase):
    def make_store(self) -> ExamAnswersStore:
        tmpdir = make_temp_dir()
        self.addCleanup(shutil.rmtree, tmpdir, True)
        root = Path(tmpdir)
        return ExamAnswersStore(root / "exam_answers.db", backend=FakeExamAnswersPostgresBackend())

    def test_postgres_exam_answers_store_imports_updates_and_scores(self):
        store = self.make_store()

        first = {
            "source_row": 2,
            "submitted_at": "2026-04-08 12:00:00",
            "full_name": "First User",
            "discord_tag": "first",
            "passport": "123456",
            "exam_format": "remote",
            "payload": {"name": "First User"},
            "answer_count": 10,
        }
        updated = {
            "source_row": 2,
            "submitted_at": "2026-04-08 12:00:01",
            "full_name": "Updated User",
            "discord_tag": "updated",
            "passport": "654321",
            "exam_format": "remote",
            "payload": {"name": "Updated User"},
            "answer_count": 12,
        }

        first_result = store.import_rows([first])
        updated_result = store.import_rows([updated])
        self.assertEqual(first_result["inserted_count"], 1)
        self.assertEqual(updated_result["inserted_count"], 1)
        self.assertEqual(updated_result["updated_count"], 0)
        self.assertEqual(store.count(), 1)
        self.assertEqual(store.get_entry(2)["full_name"], "Updated User")

        store.save_exam_scores(
            2,
            [
                {"column": "F", "score": 80},
                {"column": "G", "score": 100},
            ],
        )
        scored = store.get_entry(2)
        self.assertEqual(scored["average_score"], 90.0)
        self.assertEqual(scored["average_score_answer_count"], 2)
        self.assertEqual(scored["needs_rescore"], 0)

        pending = store.list_entries_needing_scores(limit=10)
        self.assertEqual(pending, [])

    def test_postgres_exam_answers_store_preserves_scores_when_identity_fields_change_but_answers_match(self):
        store = self.make_store()

        original = {
            "source_row": 2,
            "submitted_at": "2026-04-08 12:00:00",
            "full_name": "Student One",
            "discord_tag": "student1",
            "passport": "111111",
            "exam_format": "remote",
            "payload": {
                "submitted_at": "2026-04-08 12:00:00",
                "full_name": "Student One",
                "discord_tag": "student1",
                "passport": "111111",
                "exam_format": "remote",
                "Question F": "Answer F",
                "Question G": "Answer G",
            },
            "answer_count": 2,
        }
        updated = {
            "source_row": 3,
            "submitted_at": "2026-04-08 12:00:00",
            "full_name": "Student One Updated",
            "discord_tag": "student1_new",
            "passport": "999999",
            "exam_format": "remote",
            "payload": {
                "submitted_at": "2026-04-08 12:00:00",
                "full_name": "Student One Updated",
                "discord_tag": "student1_new",
                "passport": "999999",
                "exam_format": "remote",
                "Question F": "Answer F",
                "Question G": "Answer G",
            },
            "answer_count": 2,
        }

        store.import_rows([original])
        store.save_exam_scores(
            2,
            [
                {"column": "F", "score": 80},
                {"column": "G", "score": 100},
            ],
        )

        result = store.import_rows([updated])
        rescored = store.get_entry(3)

        self.assertEqual(result["inserted_count"], 0)
        self.assertEqual(result["updated_count"], 1)
        self.assertIsNone(store.get_entry(2))
        self.assertIsNotNone(rescored)
        self.assertEqual(rescored["average_score"], 90.0)
        self.assertEqual(rescored["average_score_answer_count"], 2)
        self.assertEqual(rescored["needs_rescore"], 0)
        self.assertEqual(len(store.list_entries_needing_scores(limit=10)), 0)


class PostgresExamImportTaskRegistryTests(unittest.TestCase):
    def make_registry(self) -> ExamImportTaskRegistry:
        tmpdir = make_temp_dir()
        self.addCleanup(shutil.rmtree, tmpdir, True)
        root = Path(tmpdir)
        return ExamImportTaskRegistry(root / "exam_import_tasks.db", backend=FakeExamImportTasksPostgresBackend())

    def test_postgres_exam_import_task_registry_runs_and_persists_json_payloads(self):
        registry = self.make_registry()
        done = threading.Event()

        def runner(progress_callback):
            progress_callback({"step": "started"})
            done.set()
            return {"ok": True, "processed": 3}

        record = registry.create_task(task_type="bulk-score", runner=runner, source_row=12)
        self.assertTrue(done.wait(timeout=2))

        loaded = None
        for _ in range(50):
            loaded = registry.get_task(record.id)
            if loaded is not None and loaded.status == "completed":
                break
            threading.Event().wait(0.01)

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.status, "completed")
        self.assertEqual(loaded.source_row, 12)
        self.assertEqual(loaded.progress, {"step": "started"})
        self.assertEqual(loaded.result, {"ok": True, "processed": 3})


if __name__ == "__main__":
    unittest.main()

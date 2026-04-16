from __future__ import annotations

import json
import gc
import os
import shutil
import sys
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

os.environ.setdefault("OGP_DB_BACKEND", "postgres")

from ogp_web.storage.exam_answers_store import ExamAnswersStore, INVALID_BATCH_RATIONALE
from ogp_web.storage.user_store import UserStore
from ogp_web.storage.user_repository import UserRepository
from ogp_web.rate_limit import PersistentRateLimiter
from ogp_web.db.errors import DatabaseSchemaError
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
        permissions_catalog = {
            "manage_servers": {"id": 1, "code": "manage_servers", "description": "Manage admin users, flags, and server level settings", "created_at": "2026-01-01T00:00:00+00:00"},
            "manage_laws": {"id": 2, "code": "manage_laws", "description": "Manage legal and exam-related administrative actions", "created_at": "2026-01-01T00:00:00+00:00"},
            "view_analytics": {"id": 3, "code": "view_analytics", "description": "Access metrics dashboards and exports", "created_at": "2026-01-01T00:00:00+00:00"},
            "court_claims": {"id": 4, "code": "court_claims", "description": "Access test pages for court claims and law Q&A", "created_at": "2026-01-01T00:00:00+00:00"},
            "exam_import": {"id": 5, "code": "exam_import", "description": "Access exam import pages and API", "created_at": "2026-01-01T00:00:00+00:00"},
            "complaint_presets": {"id": 6, "code": "complaint_presets", "description": "Access complaint test presets", "created_at": "2026-01-01T00:00:00+00:00"},
        }
        role_catalog = {
            "super_admin": {"id": 1, "code": "super_admin", "name": "Super Admin", "created_at": "2026-01-01T00:00:00+00:00"},
            "analytics_viewer": {"id": 2, "code": "analytics_viewer", "name": "Analytics Viewer", "created_at": "2026-01-01T00:00:00+00:00"},
            "law_manager": {"id": 3, "code": "law_manager", "name": "Law Manager", "created_at": "2026-01-01T00:00:00+00:00"},
            "tester": {"id": 4, "code": "tester", "name": "Tester", "created_at": "2026-01-01T00:00:00+00:00"},
            "gka": {"id": 5, "code": "gka", "name": "GKA", "created_at": "2026-01-01T00:00:00+00:00"},
        }
        role_permission_map = {
            "super_admin": ["manage_servers", "manage_laws", "view_analytics", "court_claims", "exam_import", "complaint_presets"],
            "analytics_viewer": ["view_analytics"],
            "law_manager": ["manage_laws", "exam_import"],
            "tester": ["court_claims"],
            "gka": ["exam_import", "complaint_presets"],
        }
        self._state = {
            "next_user_id": 1,
            "next_generated_document_id": 1,
            "next_case_id": 1,
            "next_case_event_id": 1,
            "next_case_document_id": 1,
            "next_document_version_id": 1,
            "next_generation_snapshot_id": 1,
            "next_law_qa_run_id": 1,
            "next_validation_requirement_id": 1,
            "next_readiness_gate_id": 1,
            "next_validation_run_id": 1,
            "next_validation_issue_id": 1,
            "next_attachment_id": 1,
            "next_export_id": 1,
            "servers": {},
            "users": {},
            "roles": {},
            "permissions_catalog": permissions_catalog,
            "role_catalog": role_catalog,
            "role_permission_map": role_permission_map,
            "user_role_assignments": [],
            "selected_servers": {},
            "drafts": {},
            "generated_documents": [],
            "cases": {},
            "case_events": [],
            "case_documents": {},
            "document_versions": {},
            "generation_snapshots": {},
            "law_qa_runs": {},
            "validation_requirements": {},
            "readiness_gates": {},
            "validation_runs": {},
            "validation_issues": {},
            "attachments": {},
            "document_version_attachment_links": {},
            "exports": {},
            "auth_rate_limit_events": [],
            "clock": 0,
            "missing_tables": set(missing_tables or set()),
            "closed_connections": 0,
            "commit_calls": 0,
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
        self.state["commit_calls"] += 1
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        self.state["closed_connections"] += 1
        return None

    def execute(self, query: str, params=()):
        normalized = " ".join(query.split())

        if normalized == "SELECT 1":
            return FakeCursor(rowcount=1, one={"?column?": 1})
        if normalized == "SELECT pg_advisory_xact_lock(hashtext(%s))":
            return FakeCursor(rowcount=1, one={"pg_advisory_xact_lock": None})
        if normalized == "SELECT to_regclass(%s) AS regclass":
            table_name = str(params[0]).split(".", 1)[-1]
            present = table_name not in self.state["missing_tables"]
            return FakeCursor(rowcount=1, one={"regclass": params[0] if present else None})
        if normalized == "SELECT COUNT(*) AS total FROM users":
            return FakeCursor(rowcount=1, one={"total": len(self.state["users"])})
        if normalized == "DELETE FROM auth_rate_limit_events":
            deleted = len(self.state["auth_rate_limit_events"])
            self.state["auth_rate_limit_events"] = []
            return FakeCursor(rowcount=deleted)
        if normalized.startswith("DELETE FROM auth_rate_limit_events WHERE action = %s AND subject_key = %s"):
            return self._delete_rate_limit_events(params)
        if normalized.startswith("SELECT COUNT(*) AS total FROM auth_rate_limit_events WHERE action = %s AND subject_key = %s"):
            return self._count_rate_limit_events(params)
        if normalized.startswith("INSERT INTO auth_rate_limit_events (action, subject_key) VALUES (%s, %s)"):
            return self._insert_rate_limit_event(params)
        if normalized.startswith("INSERT INTO servers"):
            code, title = params
            self.state["servers"][code] = {"code": code, "title": title}
            return FakeCursor(rowcount=1)
        if normalized.startswith("INSERT INTO users ") and "RETURNING id" in normalized:
            return self._insert_user(params)
        if normalized.startswith("INSERT INTO user_server_roles "):
            return self._upsert_role(params)
        if normalized.startswith("INSERT INTO user_selected_servers (user_id, server_code, updated_at)"):
            return self._upsert_selected_server(params)
        if normalized.startswith("INSERT INTO complaint_drafts (user_id, server_code, document_type, draft_json) VALUES"):
            return self._insert_draft(params)
        if normalized.startswith("INSERT INTO complaint_drafts (user_id, server_code, document_type, draft_json, updated_at) SELECT"):
            return self._save_draft(params)
        if normalized.startswith("INSERT INTO generated_documents ("):
            return self._insert_generated_document(params)
        if normalized.startswith("SELECT cd.id AS document_id, cd.case_id AS case_id FROM case_documents cd JOIN cases c ON c.id = cd.case_id WHERE c.owner_user_id = %s AND c.server_id = %s AND c.case_type = %s AND cd.document_type = %s ORDER BY cd.id DESC LIMIT 1"):
            return self._find_generated_bridge_document(params)
        if normalized.startswith("INSERT INTO cases (server_id, owner_user_id, title, case_type, status, metadata_json)"):
            return self._insert_case(params)
        if normalized.startswith("SELECT id, server_id, owner_user_id, title, case_type, status, CAST(metadata_json AS TEXT) AS metadata_json, created_at, updated_at FROM cases WHERE id = %s LIMIT 1"):
            return self._fetch_case(params[0])
        if normalized.startswith("INSERT INTO case_events (case_id, server_id, event_type, actor_user_id, payload_json)"):
            return self._insert_case_event(params)
        if normalized.startswith("INSERT INTO case_documents (case_id, server_id, document_type, status, created_by, metadata_json)"):
            return self._insert_case_document(params)
        if normalized.startswith("INSERT INTO generation_snapshots ("):
            return self._insert_generation_snapshot(params)
        if normalized.startswith("UPDATE generation_snapshots SET legacy_generated_document_id = %s WHERE id = %s"):
            return self._update_generation_snapshot_generated_id(params)
        if normalized.startswith("SELECT id, case_id, server_id, document_type, status, created_by, latest_version_id, CAST(metadata_json AS TEXT) AS metadata_json, created_at, updated_at FROM case_documents WHERE case_id = %s ORDER BY created_at DESC, id DESC"):
            return self._list_case_documents(params[0])
        if normalized.startswith("SELECT id, case_id, server_id, document_type, status, created_by, latest_version_id, CAST(metadata_json AS TEXT) AS metadata_json, created_at, updated_at FROM case_documents WHERE id = %s LIMIT 1"):
            return self._fetch_case_document(params[0])
        if normalized.startswith("SELECT version_number FROM document_versions WHERE document_id = %s ORDER BY version_number DESC LIMIT 1"):
            return self._last_document_version(params[0])
        if normalized.startswith("INSERT INTO document_versions (document_id, version_number, content_json, created_by, generation_snapshot_id)"):
            return self._insert_document_version(params)
        if normalized.startswith("INSERT INTO document_versions (document_id, version_number, content_json, created_by)"):
            return self._insert_document_version(params)
        if normalized.startswith("INSERT INTO document_versions ( document_id, version_number, content_json, created_by, generation_snapshot_id ) SELECT"):
            return self._insert_document_version_bridge(params)
        if normalized.startswith("UPDATE case_documents SET latest_version_id = %s, updated_at = NOW() WHERE id = %s"):
            return self._update_case_document_latest_version(params)
        if normalized.startswith("UPDATE case_documents SET latest_version_id = %s, updated_at = NOW(), metadata_json = jsonb_set("):
            return self._update_case_document_bridge_metadata(params)
        if normalized.startswith("UPDATE case_documents SET status = %s, updated_at = NOW(), metadata_json = jsonb_set("):
            return self._update_case_document_status(params)
        if normalized.startswith("SELECT id, document_id, version_number, CAST(content_json AS TEXT) AS content_json, created_by, generation_snapshot_id, created_at FROM document_versions WHERE document_id = %s ORDER BY version_number ASC"):
            return self._list_document_versions(params[0])
        if normalized.startswith("SELECT id, document_id, version_number, CAST(content_json AS TEXT) AS content_json, created_by, generation_snapshot_id, created_at FROM document_versions WHERE id = %s LIMIT 1"):
            return self._get_document_version(params[0])
        if normalized.startswith("SELECT id, document_id, version_number, CAST(content_json AS TEXT) AS content_json, created_by, generation_snapshot_id, created_at FROM document_versions WHERE generation_snapshot_id = %s ORDER BY id DESC LIMIT 1"):
            return self._get_latest_document_version_by_generation_snapshot_id(params[0])
        if (
            (
                "FROM users u LEFT JOIN user_server_roles usr" in normalized
                or "FROM users u LEFT JOIN user_selected_servers uss ON uss.user_id = u.id LEFT JOIN user_server_roles usr" in normalized
            )
            and "ORDER BY u.created_at DESC, u.username ASC" in normalized
        ):
            return self._list_users(params)
        if "FROM users u LEFT JOIN user_server_roles usr" in normalized and "LEFT JOIN complaint_drafts cd" in normalized:
            return self._fetch_user(normalized, params)
        if normalized.startswith("SELECT CAST(cd.draft_json AS TEXT) AS complaint_draft_json, cd.updated_at AS complaint_draft_updated_at FROM users u LEFT JOIN complaint_drafts cd ON cd.user_id = u.id AND cd.server_code = %s AND cd.document_type = %s WHERE u.username = %s LIMIT 1"):
            return self._fetch_user_draft(params)
        if normalized.startswith("SELECT uss.server_code AS selected_server_code FROM users u LEFT JOIN user_selected_servers uss ON uss.user_id = u.id WHERE u.username = %s LIMIT 1"):
            return self._fetch_selected_server(params[0])
        if normalized.startswith("SELECT id FROM users WHERE username = %s"):
            user = self.state["users"].get(params[0])
            return FakeCursor(rowcount=1 if user else 0, one={"id": user["id"]} if user else None)
        if normalized.startswith("SELECT id, name FROM roles WHERE code = %s"):
            return self._fetch_role_by_code(params[0])
        if normalized.startswith("SELECT id, code, description, created_at FROM permissions ORDER BY code ASC"):
            return self._list_permissions()
        if normalized.startswith("SELECT r.id AS id, r.code AS code, r.name AS name, r.created_at AS created_at, p.code AS permission_code FROM roles r LEFT JOIN role_permissions rp ON rp.role_id = r.id LEFT JOIN permissions p ON p.id = rp.permission_id ORDER BY r.code ASC, p.code ASC"):
            return self._list_roles_with_permissions()
        if normalized.startswith("SELECT r.code AS role_code, r.name AS role_name, ur.server_id AS server_id, ur.created_at AS created_at FROM users u JOIN user_roles ur ON ur.user_id = u.id JOIN roles r ON r.id = ur.role_id WHERE u.username = %s AND (%s = '' OR ur.server_id IS NULL OR ur.server_id = %s) ORDER BY CASE WHEN ur.server_id IS NULL THEN 0 ELSE 1 END, ur.server_id ASC NULLS FIRST, r.code ASC"):
            return self._list_user_role_assignments(params)
        if normalized.startswith("INSERT INTO user_roles (user_id, role_id, server_id, created_at) VALUES (%s, %s, %s, NOW()) ON CONFLICT (user_id, role_id, server_id) DO NOTHING"):
            return self._insert_user_role_assignment(params)
        if normalized.startswith("DELETE FROM user_roles WHERE user_id = %s AND role_id = %s AND ( (%s IS NULL AND server_id IS NULL) OR server_id = %s )"):
            return self._delete_user_role_assignment(params)
        if normalized.startswith("SELECT dv.id, dv.document_id, dv.version_number, CAST(dv.content_json AS TEXT) AS content_json, cd.server_id, cd.document_type FROM document_versions dv JOIN case_documents cd ON cd.id = dv.document_id WHERE dv.id = %s LIMIT 1"):
            return self._get_document_version_target(params[0])
        if normalized.startswith("SELECT id, server_id, question, answer_text, CAST(used_sources_json AS TEXT) AS used_sources_json, CAST(selected_norms_json AS TEXT) AS selected_norms_json, CAST(metadata_json AS TEXT) AS metadata_json FROM law_qa_runs WHERE id = %s LIMIT 1"):
            return self._get_law_qa_run(params[0])
        if normalized.startswith("INSERT INTO law_qa_runs ( server_id, user_id, question, answer_text, used_sources_json, selected_norms_json, metadata_json ) VALUES"):
            return self._insert_law_qa_run(params)
        if normalized.startswith("SELECT id, server_scope, server_id, target_type, target_subtype, field_key, CAST(rule_json AS TEXT) AS rule_json, is_required, is_active, created_at, updated_at FROM validation_requirements WHERE is_active = TRUE"):
            return self._list_validation_requirements(params)
        if normalized.startswith("SELECT id, server_scope, server_id, target_type, target_subtype, gate_code, enforcement_mode, CAST(threshold_json AS TEXT) AS threshold_json, is_active, created_at, updated_at FROM readiness_gates WHERE is_active = TRUE"):
            return self._list_readiness_gates(params)
        if normalized.startswith("INSERT INTO validation_runs ( target_type, target_id, server_id, status, risk_score, coverage_score, readiness_status, summary_json, score_breakdown_json, gate_decisions_json ) VALUES"):
            return self._insert_validation_run(params)
        if normalized.startswith("INSERT INTO validation_issues ( validation_run_id, issue_code, severity, message, field_ref, details_json ) VALUES"):
            return self._insert_validation_issue(params)
        if normalized.startswith("SELECT id, target_type, target_id, server_id, status, risk_score, coverage_score, readiness_status, CAST(summary_json AS TEXT) AS summary_json, CAST(score_breakdown_json AS TEXT) AS score_breakdown_json, CAST(gate_decisions_json AS TEXT) AS gate_decisions_json, created_at FROM validation_runs WHERE id = %s LIMIT 1"):
            return self._get_validation_run(params[0])
        if normalized.startswith("SELECT id, target_type, target_id, server_id, status, risk_score, coverage_score, readiness_status, CAST(summary_json AS TEXT) AS summary_json, CAST(score_breakdown_json AS TEXT) AS score_breakdown_json, CAST(gate_decisions_json AS TEXT) AS gate_decisions_json, created_at FROM validation_runs WHERE target_type = %s AND target_id = %s ORDER BY created_at DESC, id DESC LIMIT 1"):
            return self._get_latest_validation_run(params)
        if normalized.startswith("SELECT id, target_type, target_id, server_id, status, risk_score, coverage_score, readiness_status, CAST(summary_json AS TEXT) AS summary_json, CAST(score_breakdown_json AS TEXT) AS score_breakdown_json, CAST(gate_decisions_json AS TEXT) AS gate_decisions_json, created_at FROM validation_runs WHERE target_type = %s AND target_id = %s ORDER BY created_at DESC, id DESC"):
            return self._list_validation_runs(params)
        if normalized.startswith("SELECT id, validation_run_id, issue_code, severity, message, field_ref, CAST(details_json AS TEXT) AS details_json, created_at FROM validation_issues WHERE validation_run_id = %s ORDER BY created_at ASC, id ASC"):
            return self._list_validation_issues(params[0])
        if normalized.startswith("SELECT c.id, c.document_version_id, c.retrieval_run_id, c.citation_type, c.source_type, c.source_id, c.source_version_id, c.canonical_ref, c.quoted_text, c.usage_type, c.created_at FROM document_version_citations c JOIN document_versions dv ON dv.id = c.document_version_id JOIN case_documents d ON d.id = dv.document_id WHERE c.document_version_id = %s AND d.server_id = %s ORDER BY c.id ASC"):
            return self._get_document_version_citations(params[0], server_id=params[1])
        if normalized.startswith("SELECT id, document_version_id, retrieval_run_id, citation_type, source_type, source_id, source_version_id, canonical_ref, quoted_text, usage_type, created_at FROM document_version_citations WHERE document_version_id = %s ORDER BY id ASC"):
            return self._get_document_version_citations(params[0], server_id=None)
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
        if normalized.startswith("UPDATE users SET deactivated_at = NOW(), deactivated_reason = %s, access_blocked_at = COALESCE(access_blocked_at, NOW()), access_blocked_reason = COALESCE(NULLIF(access_blocked_reason, ''), %s) WHERE username = %s"):
            return self._deactivate_user(params)
        if normalized.startswith("UPDATE users SET deactivated_at = NULL, deactivated_reason = NULL, access_blocked_at = NULL, access_blocked_reason = NULL WHERE username = %s"):
            return self._reactivate_user(params[0])
        if normalized.startswith("UPDATE users SET api_quota_daily = %s WHERE username = %s"):
            return self._set_daily_quota(params)
        if normalized.startswith("SELECT DISTINCT p.code AS code FROM users u JOIN user_roles ur"):
            return self._list_permission_codes(params)
        if normalized.startswith("SELECT gd.id AS id, gd.server_code AS server_code, gd.document_kind AS document_kind, gd.created_at AS created_at FROM generated_documents gd JOIN users u ON u.id = gd.user_id WHERE u.username = %s ORDER BY gd.created_at DESC, gd.id DESC LIMIT %s"):
            return self._list_generated_documents(params)
        if normalized.startswith("SELECT gs.legacy_generated_document_id AS id, gs.server_id AS server_code, gs.document_kind AS document_kind, gs.created_at AS created_at FROM generation_snapshots gs JOIN users u ON u.id = gs.user_id WHERE u.username = %s AND gs.legacy_generated_document_id IS NOT NULL ORDER BY gs.created_at DESC, gs.id DESC LIMIT %s"):
            return self._list_generation_snapshots_history(params)
        if normalized.startswith("SELECT gd.id AS id, gd.server_code AS server_code, gd.document_kind AS document_kind, gd.created_at AS created_at, CAST(gd.context_snapshot_json AS TEXT) AS context_snapshot_json FROM generated_documents gd JOIN users u ON u.id = gd.user_id WHERE u.username = %s AND gd.id = %s LIMIT 1"):
            return self._fetch_generated_document_snapshot(params)
        if normalized.startswith("SELECT gs.legacy_generated_document_id AS id, gs.server_id AS server_code, gs.document_kind AS document_kind, gs.created_at AS created_at FROM generation_snapshots gs JOIN users u ON u.id = gs.user_id WHERE u.username = %s ORDER BY gs.created_at DESC, gs.id DESC LIMIT %s"):
            return self._list_generation_snapshots_history(params)
        if normalized.startswith("SELECT gs.id AS generation_snapshot_id, gs.legacy_generated_document_id AS id, gs.server_id AS server_code, gs.document_kind AS document_kind, gs.created_at AS created_at, CAST(gs.context_snapshot_json AS TEXT) AS context_snapshot_json FROM generation_snapshots gs JOIN users u ON u.id = gs.user_id WHERE u.username = %s AND gs.legacy_generated_document_id = %s ORDER BY gs.id DESC LIMIT 1"):
            return self._fetch_generation_snapshot_by_legacy(params)
        if normalized.startswith("SELECT gs.legacy_generated_document_id AS id, gs.server_id AS server_code, gs.document_kind AS document_kind, gs.created_at AS created_at, CAST(gs.context_snapshot_json AS TEXT) AS context_snapshot_json FROM generation_snapshots gs JOIN users u ON u.id = gs.user_id WHERE u.username = %s AND gs.legacy_generated_document_id = %s ORDER BY gs.id DESC LIMIT 1"):
            return self._fetch_generation_snapshot_by_legacy(params)
        if normalized.startswith("SELECT gs.id AS generation_snapshot_id, gs.legacy_generated_document_id AS id, gs.server_id AS server_code, gs.document_kind AS document_kind, gs.created_at AS created_at, CAST(gs.context_snapshot_json AS TEXT) AS context_snapshot_json FROM generation_snapshots gs WHERE gs.legacy_generated_document_id = %s ORDER BY gs.id DESC LIMIT 1"):
            return self._fetch_generation_snapshot_by_admin_legacy(params)
        if normalized.startswith("SELECT gs.legacy_generated_document_id AS id, gs.id AS generation_snapshot_id, gs.server_id AS server_code, gs.document_kind AS document_kind, gs.created_at AS created_at, u.username AS username FROM generation_snapshots gs JOIN users u ON u.id = gs.user_id WHERE gs.legacy_generated_document_id IS NOT NULL ORDER BY gs.created_at DESC, gs.id DESC LIMIT %s"):
            return self._list_recent_generated_documents_admin(params[0])
        if normalized.startswith("SELECT id, document_version_id, server_id, format, status, storage_key, mime_type, size_bytes, checksum, created_by, job_run_id, CAST(metadata_json AS TEXT) AS metadata_json, created_at, updated_at FROM exports WHERE document_version_id = %s ORDER BY created_at DESC, id DESC"):
            return self._list_exports_for_document_version(params[0])
        if normalized.startswith("SELECT a.id, a.server_id, a.uploaded_by, a.storage_key, a.filename, a.mime_type, a.size_bytes, a.checksum, a.upload_status, CAST(a.metadata_json AS TEXT) AS metadata_json, a.created_at, l.link_type, l.created_by, l.created_at AS linked_at FROM document_version_attachment_links l JOIN attachments a ON a.id = l.attachment_id WHERE l.document_version_id = %s ORDER BY l.created_at DESC, l.id DESC"):
            return self._list_attachments_for_document_version(params[0])
        if normalized.startswith("SELECT gs.id, gs.server_id AS server_code, gs.document_kind AS document_kind, gs.created_at AS created_at, CAST(gs.context_snapshot_json AS TEXT) AS context_snapshot_json, CAST(gs.effective_config_snapshot_json AS TEXT) AS effective_config_snapshot_json, CAST(gs.content_workflow_ref_json AS TEXT) AS content_workflow_ref_json FROM generation_snapshots gs WHERE gs.id = %s LIMIT 1"):
            return self._fetch_generation_snapshot_by_id(params[0])

        raise AssertionError(f"Unsupported fake postgres query: {normalized}")

    def _now(self) -> str:
        self.state["clock"] += 1
        current = datetime.now(timezone.utc) + timedelta(seconds=self.state["clock"])
        return current.isoformat()

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
            "deactivated_at": None,
            "deactivated_reason": None,
            "api_quota_daily": 0,
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

    def _upsert_selected_server(self, params):
        user_id, server_code = params[:2]
        self.state["selected_servers"][user_id] = {
            "user_id": user_id,
            "server_code": server_code,
            "updated_at": self._now(),
        }
        return FakeCursor(rowcount=1)

    def _insert_draft(self, params):
        user_id, server_code, document_type = params
        self.state["drafts"][(user_id, server_code, document_type)] = {
            "draft_json": {},
            "updated_at": self._now(),
        }
        return FakeCursor(rowcount=1)

    def _save_draft(self, params):
        server_code, document_type, draft_json, username = params
        user = self.state["users"].get(username)
        if user is None:
            return FakeCursor(rowcount=0)
        self.state["drafts"][(user["id"], server_code, document_type)] = {
            "draft_json": json.loads(draft_json),
            "updated_at": self._now(),
        }
        return FakeCursor(rowcount=1)

    def _insert_generated_document(self, params):
        server_code, document_kind, payload_json, result_text, context_snapshot_json, username = params
        user = self.state["users"].get(username)
        if user is None:
            return FakeCursor(rowcount=0)
        document_id = self.state["next_generated_document_id"]
        self.state["next_generated_document_id"] += 1
        row = {
            "id": document_id,
            "user_id": user["id"],
            "server_code": str(server_code),
            "document_kind": str(document_kind),
            "payload_json": json.loads(payload_json),
            "result_text": str(result_text),
            "context_snapshot_json": json.loads(context_snapshot_json),
            "created_at": self._now(),
        }
        self.state["generated_documents"].append(row)
        return FakeCursor(rowcount=1, one={"id": document_id})

    def _insert_case(self, params):
        server_id, owner_user_id, title, case_type = params
        case_id = self.state["next_case_id"]
        self.state["next_case_id"] += 1
        row = {
            "id": case_id,
            "server_id": str(server_id),
            "owner_user_id": int(owner_user_id),
            "title": str(title),
            "case_type": str(case_type),
            "status": "draft",
            "metadata_json": {},
            "created_at": self._now(),
            "updated_at": self._now(),
        }
        self.state["cases"][case_id] = row
        return FakeCursor(rowcount=1, one={**row, "metadata_json": "{}"})

    def _fetch_case(self, case_id: int):
        row = self.state["cases"].get(int(case_id))
        if row is None:
            return FakeCursor(rowcount=0, one=None)
        return FakeCursor(rowcount=1, one={**row, "metadata_json": json.dumps(row["metadata_json"], ensure_ascii=False)})

    def _insert_case_event(self, params):
        case_id, server_id, event_type, actor_user_id, payload_json = params
        event = {
            "id": self.state["next_case_event_id"],
            "case_id": int(case_id),
            "server_id": str(server_id),
            "event_type": str(event_type),
            "actor_user_id": int(actor_user_id),
            "payload_json": json.loads(payload_json),
            "created_at": self._now(),
        }
        self.state["next_case_event_id"] += 1
        self.state["case_events"].append(event)
        return FakeCursor(rowcount=1)

    def _insert_case_document(self, params):
        case_id, server_id, document_type, created_by = params
        if int(case_id) not in self.state["cases"]:
            return FakeCursor(rowcount=0, one=None)
        document_id = self.state["next_case_document_id"]
        self.state["next_case_document_id"] += 1
        row = {
            "id": document_id,
            "case_id": int(case_id),
            "server_id": str(server_id),
            "document_type": str(document_type),
            "status": "draft",
            "created_by": int(created_by),
            "latest_version_id": None,
            "metadata_json": {},
            "created_at": self._now(),
            "updated_at": self._now(),
        }
        self.state["case_documents"][document_id] = row
        return FakeCursor(rowcount=1, one={**row, "metadata_json": "{}"})

    def _find_generated_bridge_document(self, params):
        owner_user_id, server_id, case_type, document_type = params
        matched = []
        for row in self.state["case_documents"].values():
            case = self.state["cases"].get(int(row["case_id"]))
            if case is None:
                continue
            if int(case["owner_user_id"]) != int(owner_user_id):
                continue
            if str(case["server_id"]) != str(server_id):
                continue
            if str(case["case_type"]) != str(case_type):
                continue
            if str(row["document_type"]) != str(document_type):
                continue
            matched.append(row)
        if not matched:
            return FakeCursor(rowcount=0, one=None)
        matched.sort(key=lambda item: int(item["id"]), reverse=True)
        top = matched[0]
        return FakeCursor(rowcount=1, one={"document_id": top["id"], "case_id": top["case_id"]})

    def _insert_generation_snapshot(self, params):
        (
            server_id,
            user_id,
            document_kind,
            payload_json,
            result_text,
            context_snapshot_json,
            effective_config_snapshot_json,
            content_workflow_ref_json,
            legacy_id,
        ) = params
        snapshot_id = self.state["next_generation_snapshot_id"]
        self.state["next_generation_snapshot_id"] += 1
        row = {
            "id": snapshot_id,
            "server_id": str(server_id),
            "user_id": int(user_id),
            "document_kind": str(document_kind),
            "payload_json": json.loads(payload_json),
            "result_text": str(result_text),
            "context_snapshot_json": json.loads(context_snapshot_json),
            "effective_config_snapshot_json": json.loads(effective_config_snapshot_json),
            "content_workflow_ref_json": json.loads(content_workflow_ref_json),
            "legacy_generated_document_id": int(legacy_id) if legacy_id is not None else None,
            "created_at": self._now(),
        }
        self.state["generation_snapshots"][snapshot_id] = row
        return FakeCursor(rowcount=1, one={"id": snapshot_id})

    def _update_generation_snapshot_generated_id(self, params):
        generated_document_id, snapshot_id = params
        row = self.state["generation_snapshots"].get(int(snapshot_id))
        if row is None:
            return FakeCursor(rowcount=0)
        row["legacy_generated_document_id"] = int(generated_document_id)
        return FakeCursor(rowcount=1)

    def _list_case_documents(self, case_id: int):
        rows = [
            row for row in self.state["case_documents"].values()
            if int(row["case_id"]) == int(case_id)
        ]
        rows.sort(key=lambda item: (item["created_at"], item["id"]), reverse=True)
        payload = [{**row, "metadata_json": json.dumps(row["metadata_json"], ensure_ascii=False)} for row in rows]
        return FakeCursor(rowcount=len(payload), rows=payload)

    def _fetch_case_document(self, document_id: int):
        row = self.state["case_documents"].get(int(document_id))
        if row is None:
            return FakeCursor(rowcount=0, one=None)
        return FakeCursor(rowcount=1, one={**row, "metadata_json": json.dumps(row["metadata_json"], ensure_ascii=False)})

    def _last_document_version(self, document_id: int):
        versions = [
            row for row in self.state["document_versions"].values()
            if int(row["document_id"]) == int(document_id)
        ]
        if not versions:
            return FakeCursor(rowcount=0, one=None)
        versions.sort(key=lambda item: int(item["version_number"]), reverse=True)
        return FakeCursor(rowcount=1, one={"version_number": int(versions[0]["version_number"])})

    def _insert_document_version(self, params):
        if len(params) == 5:
            document_id, version_number, content_json, created_by, generation_snapshot_id = params
        else:
            document_id, version_number, content_json, created_by = params
            generation_snapshot_id = None
        existing = [
            row for row in self.state["document_versions"].values()
            if int(row["document_id"]) == int(document_id) and int(row["version_number"]) == int(version_number)
        ]
        if existing:
            raise UniqueViolation("duplicate document version")
        version_id = self.state["next_document_version_id"]
        self.state["next_document_version_id"] += 1
        row = {
            "id": version_id,
            "document_id": int(document_id),
            "version_number": int(version_number),
            "content_json": json.loads(content_json),
            "created_by": int(created_by),
            "generation_snapshot_id": int(generation_snapshot_id) if generation_snapshot_id is not None else None,
            "created_at": self._now(),
        }
        self.state["document_versions"][version_id] = row
        return FakeCursor(
            rowcount=1,
            one={**row, "content_json": json.dumps(row["content_json"], ensure_ascii=False)},
        )

    def _insert_document_version_bridge(self, params):
        document_id, content_json, created_by, generation_snapshot_id, same_document_id = params
        assert int(document_id) == int(same_document_id)
        versions = [
            row for row in self.state["document_versions"].values()
            if int(row["document_id"]) == int(document_id)
        ]
        next_version = (max((int(item["version_number"]) for item in versions), default=0) + 1)
        return self._insert_document_version((document_id, next_version, content_json, created_by, generation_snapshot_id))

    def _update_case_document_latest_version(self, params):
        latest_version_id, document_id = params
        row = self.state["case_documents"].get(int(document_id))
        if row is None:
            return FakeCursor(rowcount=0)
        row["latest_version_id"] = int(latest_version_id)
        row["updated_at"] = self._now()
        return FakeCursor(rowcount=1)

    def _update_case_document_bridge_metadata(self, params):
        latest_version_id, legacy_generated_document_id, document_id = params
        row = self.state["case_documents"].get(int(document_id))
        if row is None:
            return FakeCursor(rowcount=0)
        row["latest_version_id"] = int(latest_version_id)
        bridge = dict((row.get("metadata_json") or {}).get("bridge") or {})
        bridge["legacy_generated_document_id"] = int(legacy_generated_document_id)
        row["metadata_json"] = dict(row.get("metadata_json") or {})
        row["metadata_json"]["bridge"] = bridge
        row["updated_at"] = self._now()
        return FakeCursor(rowcount=1)

    def _update_case_document_status(self, params):
        status, actor_user_id, document_id = params
        row = self.state["case_documents"].get(int(document_id))
        if row is None:
            return FakeCursor(rowcount=0, one=None)
        row["status"] = str(status)
        metadata = dict(row.get("metadata_json") or {})
        metadata["status_actor_user_id"] = int(actor_user_id)
        row["metadata_json"] = metadata
        row["updated_at"] = self._now()
        return FakeCursor(rowcount=1, one={**row, "metadata_json": json.dumps(row["metadata_json"], ensure_ascii=False)})

    def _list_document_versions(self, document_id: int):
        rows = [
            row for row in self.state["document_versions"].values()
            if int(row["document_id"]) == int(document_id)
        ]
        rows.sort(key=lambda item: int(item["version_number"]))
        payload = [{**row, "content_json": json.dumps(row["content_json"], ensure_ascii=False)} for row in rows]
        return FakeCursor(rowcount=len(payload), rows=payload)

    def _find_by(self, field: str, value: str):
        for user in self.state["users"].values():
            if user.get(field) == value:
                return user
        return None

    def _compose_user_row(self, user, server_code: str):
        selected_server = self.state["selected_servers"].get(user["id"], {}).get("server_code")
        effective_server = selected_server or server_code
        role = self.state["roles"].get((user["id"], effective_server), {})
        draft = self.state["drafts"].get((user["id"], effective_server, "complaint"), {})
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
            "deactivated_at": user.get("deactivated_at"),
            "deactivated_reason": user.get("deactivated_reason"),
            "api_quota_daily": user.get("api_quota_daily", 0),
            "server_code": role.get("server_code", effective_server),
            "is_tester": role.get("is_tester", False),
            "is_gka": role.get("is_gka", False),
            "representative_profile": json.dumps(user["representative_profile"], ensure_ascii=False),
            "complaint_draft_json": json.dumps(draft.get("draft_json", {}), ensure_ascii=False),
            "complaint_draft_updated_at": draft.get("updated_at"),
        }

    def _fetch_selected_server(self, username: str):
        user = self.state["users"].get(username)
        if user is None:
            return FakeCursor(rowcount=0, one=None)
        selected = self.state["selected_servers"].get(user["id"])
        payload = {
            "selected_server_code": selected.get("server_code") if selected else None,
        }
        return FakeCursor(rowcount=1, one=payload)

    def _fetch_user_draft(self, params):
        server_code, document_type, username = params
        user = self.state["users"].get(username)
        if user is None:
            return FakeCursor(rowcount=0, one=None)
        draft = self.state["drafts"].get((user["id"], server_code, document_type), {})
        return FakeCursor(
            rowcount=1,
            one={
                "complaint_draft_json": json.dumps(draft.get("draft_json", {}), ensure_ascii=False),
                "complaint_draft_updated_at": draft.get("updated_at"),
            },
        )

    def _fetch_user(self, normalized: str, params):
        server_code = params[0]
        username_index = 3
        if "u.username = %s" in normalized:
            user = self.state["users"].get(params[username_index])
        elif "u.email = %s" in normalized:
            user = self._find_by("email", params[username_index])
        elif "u.email_verification_token_hash = %s" in normalized:
            user = self._find_by("email_verification_token_hash", params[username_index])
        elif "u.password_reset_token_hash = %s" in normalized:
            user = self._find_by("password_reset_token_hash", params[username_index])
        else:
            raise AssertionError(f"Unsupported fake postgres fetch query: {normalized}")
        row = self._compose_user_row(user, server_code) if user else None
        return FakeCursor(rowcount=1 if row else 0, one=row)

    def _list_users(self, params):
        server_code = "blackberry"
        safe_limit = None
        if params:
            first_param = params[0]
            if isinstance(first_param, str):
                server_code = first_param
                if len(params) > 1:
                    try:
                        safe_limit = max(0, int(params[1]))
                    except (TypeError, ValueError):
                        safe_limit = None
            else:
                try:
                    safe_limit = max(0, int(first_param))
                except (TypeError, ValueError):
                    safe_limit = None
        rows = [
            self._compose_user_row(user, server_code)
            for user in sorted(
                self.state["users"].values(),
                key=lambda item: (item["created_at"], item["username"]),
                reverse=True,
            )
        ]
        if safe_limit:
            rows = rows[:safe_limit]
        return FakeCursor(rowcount=len(rows), rows=rows)

    def _fetch_role_by_code(self, role_code: str):
        role = self.state["role_catalog"].get(str(role_code or "").strip().lower())
        if role is None:
            return FakeCursor(rowcount=0, one=None)
        return FakeCursor(rowcount=1, one={"id": role["id"], "name": role["name"]})

    def _list_permissions(self):
        rows = list(sorted(self.state["permissions_catalog"].values(), key=lambda item: item["code"]))
        return FakeCursor(rowcount=len(rows), rows=rows)

    def _list_roles_with_permissions(self):
        rows = []
        for role in sorted(self.state["role_catalog"].values(), key=lambda item: item["code"]):
            permission_codes = self.state["role_permission_map"].get(role["code"], [])
            if not permission_codes:
                rows.append({**role, "permission_code": None})
                continue
            for permission_code in sorted(permission_codes):
                rows.append({**role, "permission_code": permission_code})
        return FakeCursor(rowcount=len(rows), rows=rows)

    def _list_user_role_assignments(self, params):
        username, server_code_filter, _server_code_filter_repeat = params
        user = self.state["users"].get(username)
        if user is None:
            return FakeCursor(rowcount=0, rows=[])
        rows = []
        for assignment in self.state["user_role_assignments"]:
            if int(assignment["user_id"]) != int(user["id"]):
                continue
            assignment_server_id = assignment.get("server_id")
            if server_code_filter and assignment_server_id not in {None, server_code_filter}:
                continue
            role = self.state["role_catalog"].get(assignment["role_code"])
            rows.append(
                {
                    "role_code": assignment["role_code"],
                    "role_name": role["name"] if role else assignment["role_code"],
                    "server_id": assignment_server_id,
                    "created_at": assignment["created_at"],
                }
            )
        rows.sort(key=lambda item: (item["server_id"] is not None, item["server_id"] or "", item["role_code"]))
        return FakeCursor(rowcount=len(rows), rows=rows)

    def _insert_user_role_assignment(self, params):
        user_id, role_id, server_id = params
        role_code = next((code for code, role in self.state["role_catalog"].items() if int(role["id"]) == int(role_id)), "")
        existing = next(
            (
                item for item in self.state["user_role_assignments"]
                if int(item["user_id"]) == int(user_id)
                and str(item["role_code"]) == role_code
                and item.get("server_id") == server_id
            ),
            None,
        )
        if existing is not None:
            return FakeCursor(rowcount=0)
        self.state["user_role_assignments"].append(
            {
                "user_id": int(user_id),
                "role_code": role_code,
                "server_id": server_id,
                "created_at": self._now(),
            }
        )
        return FakeCursor(rowcount=1)

    def _delete_user_role_assignment(self, params):
        user_id, role_id, assignment_server_id, assignment_server_id_repeat = params
        _ = assignment_server_id_repeat
        role_code = next((code for code, role in self.state["role_catalog"].items() if int(role["id"]) == int(role_id)), "")
        before = len(self.state["user_role_assignments"])
        self.state["user_role_assignments"] = [
            item
            for item in self.state["user_role_assignments"]
            if not (
                int(item["user_id"]) == int(user_id)
                and str(item["role_code"]) == role_code
                and item.get("server_id") == assignment_server_id
            )
        ]
        return FakeCursor(rowcount=before - len(self.state["user_role_assignments"]))

    def _list_permission_codes(self, params):
        username, server_code = params
        user = self.state["users"].get(username)
        if user is None:
            return FakeCursor(rowcount=0, rows=[])

        role = self.state["roles"].get((user["id"], server_code))
        permission_codes: list[str] = []
        if role:
            if role.get("is_tester"):
                permission_codes.append("court_claims")
            if role.get("is_gka"):
                permission_codes.extend(("exam_import", "complaint_presets"))
        for assignment in self.state["user_role_assignments"]:
            if int(assignment["user_id"]) != int(user["id"]):
                continue
            if assignment.get("server_id") not in {None, server_code}:
                continue
            permission_codes.extend(self.state["role_permission_map"].get(str(assignment["role_code"]), ()))

        rows = []
        seen_codes = set()
        for code in permission_codes:
            normalized = str(code or "").strip().lower()
            if not normalized or normalized in seen_codes:
                continue
            seen_codes.add(normalized)
            rows.append({"code": normalized})
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
        server_code, document_type, username = params
        user = self.state["users"].get(username)
        if user is None:
            return FakeCursor(rowcount=0)
        self.state["drafts"][(user["id"], server_code, document_type)] = {
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

    def _deactivate_user(self, params):
        reason, block_reason, username = params
        user = self.state["users"].get(username)
        if user is None:
            return FakeCursor(rowcount=0)
        user["deactivated_at"] = self._now()
        user["deactivated_reason"] = reason
        if not user.get("access_blocked_at"):
            user["access_blocked_at"] = self._now()
        if not str(user.get("access_blocked_reason") or "").strip():
            user["access_blocked_reason"] = block_reason
        return FakeCursor(rowcount=1)

    def _reactivate_user(self, username: str):
        user = self.state["users"].get(username)
        if user is None:
            return FakeCursor(rowcount=0)
        user["deactivated_at"] = None
        user["deactivated_reason"] = None
        user["access_blocked_at"] = None
        user["access_blocked_reason"] = None
        return FakeCursor(rowcount=1)

    def _set_daily_quota(self, params):
        daily_limit, username = params
        user = self.state["users"].get(username)
        if user is None:
            return FakeCursor(rowcount=0)
        user["api_quota_daily"] = int(daily_limit or 0)
        return FakeCursor(rowcount=1)

    def _list_generated_documents(self, params):
        username, limit = params
        user = self.state["users"].get(username)
        if user is None:
            return FakeCursor(rowcount=0, rows=[])
        rows = [
            {
                "id": item["id"],
                "server_code": item["server_code"],
                "document_kind": item["document_kind"],
                "created_at": item["created_at"],
            }
            for item in sorted(
                self.state["generated_documents"],
                key=lambda item: (item["created_at"], item["id"]),
                reverse=True,
            )
            if item["user_id"] == user["id"]
        ][: int(limit)]
        return FakeCursor(rowcount=len(rows), rows=rows)

    def _fetch_generated_document_snapshot(self, params):
        username, document_id = params
        user = self.state["users"].get(username)
        if user is None:
            return FakeCursor(rowcount=0)
        for item in self.state["generated_documents"]:
            if item["user_id"] == user["id"] and item["id"] == int(document_id):
                return FakeCursor(
                    rowcount=1,
                    one={
                        "id": item["id"],
                        "server_code": item["server_code"],
                        "document_kind": item["document_kind"],
                        "created_at": item["created_at"],
                        "context_snapshot_json": json.dumps(item["context_snapshot_json"], ensure_ascii=False),
                    },
                )
        return FakeCursor(rowcount=0)

    def _list_generation_snapshots_history(self, params):
        username, limit = params
        user = self.state["users"].get(username)
        if user is None:
            return FakeCursor(rowcount=0, rows=[])
        rows = [
            {
                "id": row["legacy_generated_document_id"],
                "server_code": row["server_id"],
                "document_kind": row["document_kind"],
                "created_at": row["created_at"],
            }
            for row in sorted(
                self.state["generation_snapshots"].values(),
                key=lambda item: (item["created_at"], item["id"]),
                reverse=True,
            )
            if int(row["user_id"]) == int(user["id"])
        ][: int(limit)]
        return FakeCursor(rowcount=len(rows), rows=rows)

    def _fetch_generation_snapshot_by_legacy(self, params):
        username, legacy_id = params
        user = self.state["users"].get(username)
        if user is None:
            return FakeCursor(rowcount=0, one=None)
        matched = [
            row for row in self.state["generation_snapshots"].values()
            if int(row["user_id"]) == int(user["id"]) and int(row["legacy_generated_document_id"]) == int(legacy_id)
        ]
        if not matched:
            return FakeCursor(rowcount=0, one=None)
        matched.sort(key=lambda item: int(item["id"]), reverse=True)
        row = matched[0]
        return FakeCursor(
            rowcount=1,
            one={
                "generation_snapshot_id": row["id"],
                "id": row["legacy_generated_document_id"],
                "server_code": row["server_id"],
                "document_kind": row["document_kind"],
                "created_at": row["created_at"],
                "context_snapshot_json": json.dumps(row["context_snapshot_json"], ensure_ascii=False),
            },
        )

    def _fetch_generation_snapshot_by_admin_legacy(self, params):
        legacy_id = params[0]
        matched = [
            row for row in self.state["generation_snapshots"].values()
            if int(row["legacy_generated_document_id"]) == int(legacy_id)
        ]
        if not matched:
            return FakeCursor(rowcount=0, one=None)
        matched.sort(key=lambda item: int(item["id"]), reverse=True)
        row = matched[0]
        return FakeCursor(
            rowcount=1,
            one={
                "generation_snapshot_id": row["id"],
                "id": row["legacy_generated_document_id"],
                "server_code": row["server_id"],
                "document_kind": row["document_kind"],
                "created_at": row["created_at"],
                "context_snapshot_json": json.dumps(row["context_snapshot_json"], ensure_ascii=False),
            },
        )

    def _list_recent_generated_documents_admin(self, limit):
        rows = [
            {
                "id": row["legacy_generated_document_id"],
                "generation_snapshot_id": row["id"],
                "server_code": row["server_id"],
                "document_kind": row["document_kind"],
                "created_at": row["created_at"],
                "username": next(
                    (
                        username
                        for username, user in self.state["users"].items()
                        if int(user["id"]) == int(row["user_id"])
                    ),
                    "",
                ),
            }
            for row in sorted(
                self.state["generation_snapshots"].values(),
                key=lambda item: (item["created_at"], item["id"]),
                reverse=True,
            )
            if int(row.get("legacy_generated_document_id") or 0) > 0
        ][: int(limit)]
        return FakeCursor(rowcount=len(rows), rows=rows)

    def _list_exports_for_document_version(self, document_version_id):
        rows = [
            {
                **row,
                "metadata_json": json.dumps(row.get("metadata_json") or {}, ensure_ascii=False),
            }
            for row in self.state["exports"].values()
            if int(row.get("document_version_id") or 0) == int(document_version_id)
        ]
        rows.sort(key=lambda item: (item["created_at"], item["id"]), reverse=True)
        return FakeCursor(rowcount=len(rows), rows=rows)

    def _list_attachments_for_document_version(self, document_version_id):
        rows = []
        for link in self.state["document_version_attachment_links"].values():
            if int(link.get("document_version_id") or 0) != int(document_version_id):
                continue
            attachment = self.state["attachments"].get(int(link.get("attachment_id") or 0))
            if attachment is None:
                continue
            rows.append(
                {
                    **attachment,
                    "metadata_json": json.dumps(attachment.get("metadata_json") or {}, ensure_ascii=False),
                    "link_type": str(link.get("link_type") or ""),
                    "created_by": int(link.get("created_by") or 0),
                    "linked_at": str(link.get("created_at") or ""),
                }
            )
        rows.sort(key=lambda item: (item["linked_at"], item["id"]), reverse=True)
        return FakeCursor(rowcount=len(rows), rows=rows)

    def _get_latest_document_version_by_generation_snapshot_id(self, generation_snapshot_id):
        matched = [
            row for row in self.state["document_versions"].values()
            if int(row.get("generation_snapshot_id") or 0) == int(generation_snapshot_id)
        ]
        if not matched:
            return FakeCursor(rowcount=0, one=None)
        matched.sort(key=lambda item: int(item["id"]), reverse=True)
        row = matched[0]
        return FakeCursor(
            rowcount=1,
            one={
                "id": row["id"],
                "document_id": row["document_id"],
                "version_number": row["version_number"],
                "content_json": json.dumps(row["content_json"], ensure_ascii=False),
                "created_by": row["created_by"],
                "generation_snapshot_id": row.get("generation_snapshot_id"),
                "created_at": row["created_at"],
            },
        )

    def _get_document_version(self, version_id):
        row = self.state["document_versions"].get(int(version_id))
        if row is None:
            return FakeCursor(rowcount=0, one=None)
        return FakeCursor(
            rowcount=1,
            one={
                "id": row["id"],
                "document_id": row["document_id"],
                "version_number": row["version_number"],
                "content_json": json.dumps(row["content_json"], ensure_ascii=False),
                "created_by": row["created_by"],
                "generation_snapshot_id": row.get("generation_snapshot_id"),
                "created_at": row["created_at"],
            },
        )

    def _fetch_generation_snapshot_by_id(self, snapshot_id):
        row = self.state["generation_snapshots"].get(int(snapshot_id))
        if row is None:
            return FakeCursor(rowcount=0, one=None)
        return FakeCursor(
            rowcount=1,
            one={
                "id": row["id"],
                "server_code": row["server_id"],
                "document_kind": row["document_kind"],
                "created_at": row["created_at"],
                "context_snapshot_json": json.dumps(row.get("context_snapshot_json") or {}, ensure_ascii=False),
                "effective_config_snapshot_json": json.dumps(row.get("effective_config_snapshot_json") or {}, ensure_ascii=False),
                "content_workflow_ref_json": json.dumps(row.get("content_workflow_ref_json") or {}, ensure_ascii=False),
            },
        )

    def _get_document_version_citations(self, document_version_id, server_id=None):
        rows = []
        for row in self.state.get("document_version_citations", {}).values():
            if int(row.get("document_version_id") or 0) != int(document_version_id):
                continue
            if server_id is not None:
                version = self.state["document_versions"].get(int(row["document_version_id"]))
                document = self.state["case_documents"].get(int((version or {}).get("document_id") or 0))
                if str((document or {}).get("server_id") or "").strip().lower() != str(server_id).strip().lower():
                    continue
            rows.append(dict(row))
        rows.sort(key=lambda item: int(item.get("id") or 0))
        return FakeCursor(rowcount=len(rows), rows=rows)

    def _insert_law_qa_run(self, params):
        server_id, user_id, question, answer_text, used_sources_json, selected_norms_json, metadata_json = params
        run_id = self.state["next_law_qa_run_id"]
        self.state["next_law_qa_run_id"] += 1
        row = {
            "id": run_id,
            "server_id": server_id,
            "user_id": int(user_id),
            "question": question,
            "answer_text": answer_text,
            "used_sources_json": json.loads(used_sources_json),
            "selected_norms_json": json.loads(selected_norms_json),
            "metadata_json": json.loads(metadata_json),
            "created_at": self._now(),
        }
        self.state["law_qa_runs"][run_id] = row
        return FakeCursor(rowcount=1, one={"id": run_id, "server_id": server_id, "question": question, "answer_text": answer_text, "created_at": row["created_at"]})

    def _get_law_qa_run(self, run_id: int):
        row = self.state["law_qa_runs"].get(int(run_id))
        if row is None:
            return FakeCursor(rowcount=0, one=None)
        return FakeCursor(rowcount=1, one={**row, "used_sources_json": json.dumps(row["used_sources_json"], ensure_ascii=False), "selected_norms_json": json.dumps(row["selected_norms_json"], ensure_ascii=False), "metadata_json": json.dumps(row["metadata_json"], ensure_ascii=False)})

    def _get_document_version_target(self, version_id: int):
        row = self.state["document_versions"].get(int(version_id))
        if row is None:
            return FakeCursor(rowcount=0, one=None)
        document = self.state["case_documents"].get(int(row["document_id"]))
        if document is None:
            return FakeCursor(rowcount=0, one=None)
        return FakeCursor(rowcount=1, one={"id": row["id"], "document_id": row["document_id"], "version_number": row["version_number"], "content_json": json.dumps(row.get("content_json") or {}, ensure_ascii=False), "server_id": document["server_id"], "document_type": document["document_type"]})

    def _list_validation_requirements(self, params):
        target_type, target_subtype, server_id = params
        rows = []
        for row in self.state["validation_requirements"].values():
            if not row["is_active"] or row["target_type"] != target_type:
                continue
            if row["target_subtype"] not in {"", target_subtype}:
                continue
            if not ((row["server_scope"] == "global" and row["server_id"] is None) or (row["server_scope"] == "server" and row["server_id"] == server_id)):
                continue
            rows.append({**row, "rule_json": json.dumps(row["rule_json"], ensure_ascii=False)})
        rows.sort(key=lambda item: (0 if item["server_scope"] == "server" else 1, item["id"]))
        return FakeCursor(rowcount=len(rows), rows=rows)

    def _list_readiness_gates(self, params):
        target_type, target_subtype, server_id = params
        rows = []
        for row in self.state["readiness_gates"].values():
            if not row["is_active"] or row["target_type"] != target_type:
                continue
            if row["target_subtype"] not in {"", target_subtype}:
                continue
            if not ((row["server_scope"] == "global" and row["server_id"] is None) or (row["server_scope"] == "server" and row["server_id"] == server_id)):
                continue
            rows.append({**row, "threshold_json": json.dumps(row["threshold_json"], ensure_ascii=False)})
        rows.sort(key=lambda item: (0 if item["server_scope"] == "server" else 1, item["id"]))
        return FakeCursor(rowcount=len(rows), rows=rows)

    def _insert_validation_run(self, params):
        target_type, target_id, server_id, status, risk_score, coverage_score, readiness_status, summary_json, score_breakdown_json, gate_decisions_json = params
        run_id = self.state["next_validation_run_id"]
        self.state["next_validation_run_id"] += 1
        row = {
            "id": run_id,
            "target_type": target_type,
            "target_id": int(target_id),
            "server_id": server_id,
            "status": status,
            "risk_score": float(risk_score),
            "coverage_score": float(coverage_score),
            "readiness_status": readiness_status,
            "summary_json": json.loads(summary_json),
            "score_breakdown_json": json.loads(score_breakdown_json),
            "gate_decisions_json": json.loads(gate_decisions_json),
            "created_at": self._now(),
        }
        self.state["validation_runs"][run_id] = row
        return FakeCursor(rowcount=1, one={**row, "summary_json": json.dumps(row["summary_json"], ensure_ascii=False), "score_breakdown_json": json.dumps(row["score_breakdown_json"], ensure_ascii=False), "gate_decisions_json": json.dumps(row["gate_decisions_json"], ensure_ascii=False)})

    def _insert_validation_issue(self, params):
        validation_run_id, issue_code, severity, message, field_ref, details_json = params
        issue_id = self.state["next_validation_issue_id"]
        self.state["next_validation_issue_id"] += 1
        row = {"id": issue_id, "validation_run_id": int(validation_run_id), "issue_code": issue_code, "severity": severity, "message": message, "field_ref": field_ref, "details_json": json.loads(details_json), "created_at": self._now()}
        self.state["validation_issues"][issue_id] = row
        return FakeCursor(rowcount=1, one={**row, "details_json": json.dumps(row["details_json"], ensure_ascii=False)})

    def _get_validation_run(self, run_id: int):
        row = self.state["validation_runs"].get(int(run_id))
        if row is None:
            return FakeCursor(rowcount=0, one=None)
        return FakeCursor(rowcount=1, one={**row, "summary_json": json.dumps(row["summary_json"], ensure_ascii=False), "score_breakdown_json": json.dumps(row["score_breakdown_json"], ensure_ascii=False), "gate_decisions_json": json.dumps(row["gate_decisions_json"], ensure_ascii=False)})

    def _get_latest_validation_run(self, params):
        target_type, target_id = params
        rows = [row for row in self.state["validation_runs"].values() if row["target_type"] == target_type and int(row["target_id"]) == int(target_id)]
        if not rows:
            return FakeCursor(rowcount=0, one=None)
        rows.sort(key=lambda item: (item["created_at"], item["id"]), reverse=True)
        row = rows[0]
        return FakeCursor(rowcount=1, one={**row, "summary_json": json.dumps(row["summary_json"], ensure_ascii=False), "score_breakdown_json": json.dumps(row["score_breakdown_json"], ensure_ascii=False), "gate_decisions_json": json.dumps(row["gate_decisions_json"], ensure_ascii=False)})

    def _list_validation_runs(self, params):
        target_type, target_id = params
        rows = [row for row in self.state["validation_runs"].values() if row["target_type"] == target_type and int(row["target_id"]) == int(target_id)]
        rows.sort(key=lambda item: (item["created_at"], item["id"]), reverse=True)
        payload = [{**row, "summary_json": json.dumps(row["summary_json"], ensure_ascii=False), "score_breakdown_json": json.dumps(row["score_breakdown_json"], ensure_ascii=False), "gate_decisions_json": json.dumps(row["gate_decisions_json"], ensure_ascii=False)} for row in rows]
        return FakeCursor(rowcount=len(payload), rows=payload)

    def _list_validation_issues(self, validation_run_id: int):
        rows = [row for row in self.state["validation_issues"].values() if int(row["validation_run_id"]) == int(validation_run_id)]
        rows.sort(key=lambda item: (item["created_at"], item["id"]))
        payload = [{**row, "details_json": json.dumps(row["details_json"], ensure_ascii=False)} for row in rows]
        return FakeCursor(rowcount=len(payload), rows=payload)

    def _insert_rate_limit_event(self, params):
        action, subject_key = params
        self.state["auth_rate_limit_events"].append(
            {
                "action": str(action),
                "subject_key": str(subject_key),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        return FakeCursor(rowcount=1)

    def _count_rate_limit_events(self, params):
        action, subject_key = params
        total = sum(
            1
            for row in self.state["auth_rate_limit_events"]
            if row["action"] == str(action) and row["subject_key"] == str(subject_key)
        )
        return FakeCursor(rowcount=1, one={"total": total})

    def _delete_rate_limit_events(self, params):
        action, subject_key, _window_seconds = params
        threshold = datetime.now(timezone.utc) - timedelta(seconds=int(_window_seconds or 0))
        before = len(self.state["auth_rate_limit_events"])
        self.state["auth_rate_limit_events"] = [
            row
            for row in self.state["auth_rate_limit_events"]
            if not (
                row["action"] == str(action)
                and row["subject_key"] == str(subject_key)
                and datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00")).astimezone(timezone.utc) < threshold
            )
        ]
        return FakeCursor(rowcount=before - len(self.state["auth_rate_limit_events"]))


class FakeAdminMetricsPostgresBackend:
    def __init__(
        self,
        *,
        has_metric_events_table: bool = True,
        metric_columns: set[str] | None = None,
    ):
        self._state = {
            "metric_events": [],
            "next_id": 1,
            "clock": 0,
            "has_metric_events_table": has_metric_events_table,
            "metric_columns": set(
                metric_columns if metric_columns is not None else {
                    "id",
                    "created_at",
                    "username",
                    "server_code",
                    "event_type",
                    "path",
                    "method",
                    "status_code",
                    "duration_ms",
                    "request_bytes",
                    "response_bytes",
                    "resource_units",
                    "meta_json",
                }
            ),
        }

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

    @staticmethod
    def _percentile(values, quantile):
        ordered = sorted(int(item) for item in values if item is not None)
        if not ordered:
            return None
        if len(ordered) == 1:
            return ordered[0]
        index = (len(ordered) - 1) * quantile
        lower = int(index)
        upper = min(lower + 1, len(ordered) - 1)
        weight = index - lower
        return int(round((1 - weight) * ordered[lower] + weight * ordered[upper]))

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None

    def execute(self, query: str, params=()):
        normalized = " ".join(query.split())

        if normalized == "SELECT to_regclass(%s) AS regclass":
            present = bool(self.state["has_metric_events_table"])
            return FakeCursor(rowcount=1, one={"regclass": params[0] if present else None})
        if normalized == "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'metric_events'":
            return FakeCursor(
                rowcount=len(self.state["metric_columns"]),
                rows=[{"column_name": column_name} for column_name in sorted(self.state["metric_columns"])],
            )
        if normalized.startswith("CREATE TABLE IF NOT EXISTS metric_events"):
            return FakeCursor(rowcount=0)
        if normalized.startswith("CREATE INDEX IF NOT EXISTS idx_metric_events_"):
            return FakeCursor(rowcount=0)
        if normalized == "ALTER TABLE metric_events ADD COLUMN IF NOT EXISTS server_code TEXT":
            self.state["metric_columns"].add("server_code")
            return FakeCursor(rowcount=0)
        if normalized == "ALTER TABLE metric_events ADD COLUMN IF NOT EXISTS meta_json JSONB NOT NULL DEFAULT '{}'::jsonb":
            self.state["metric_columns"].add("meta_json")
            return FakeCursor(rowcount=0)
        if normalized.startswith("INSERT INTO metric_events "):
            return self._insert_event(params)
        if normalized.startswith("SELECT COUNT(*) AS request_count, SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) AS error_count, COALESCE(SUM(CASE WHEN event_type = 'api_request' THEN 1 ELSE 0 END), 0) AS api_requests_total,"):
            return self._performance_totals(params)
        if normalized.startswith("SELECT BTRIM(path) AS path, COUNT(*) AS count, SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) AS error_count, COALESCE(AVG(duration_ms), 0) AS avg_ms,"):
            return self._performance_endpoint_rows(params)
        if normalized == "SELECT COUNT(*) AS total FROM metric_events WHERE event_type = 'api_request' AND username = %s AND created_at >= NOW() - INTERVAL '1 day'":
            return self._count_user_api_requests_last_24h(params)
        if "COUNT(*) AS total_events" in normalized and "FROM metric_events" in normalized:
            return self._totals()
        if normalized.startswith("SELECT path, COUNT(*) AS count FROM metric_events"):
            return self._top_endpoints()
        if normalized.startswith("SELECT created_at, username, server_code, event_type, path, method, status_code, duration_ms, request_bytes, response_bytes, resource_units, meta_json FROM metric_events"):
            return self._recent_events(normalized, params)
        if normalized.startswith("SELECT username, MAX(server_code) AS server_code,"):
            return self._user_metrics()
        if normalized.startswith("WITH scoped_events AS ( SELECT event_type, meta_json FROM metric_events WHERE event_type IN"):
            return self._ai_exam_stats()
        if normalized.startswith("SELECT created_at, username, server_code, event_type, path, status_code, meta_json FROM metric_events WHERE event_type IN"):
            return self._latest_event(params)

        raise AssertionError(f"Unsupported fake admin metrics query: {normalized}")

    def _now(self) -> str:
        self.state["clock"] += 1
        current = datetime.now(timezone.utc) + timedelta(seconds=self.state["clock"])
        return current.isoformat()

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
        scoring_events = [
            item
            for item in self.state["metric_events"]
            if item["event_type"] in {"ai_exam_scoring", "exam_import_score_failures", "exam_import_row_score_error"}
        ]
        scoring_ms_values: list[int] = []
        for item in scoring_events:
            if item["event_type"] != "ai_exam_scoring":
                continue
            raw_scoring_ms = (item.get("meta_json") or {}).get("scoring_ms")
            try:
                if raw_scoring_ms is None:
                    continue
                scoring_ms_values.append(int(raw_scoring_ms))
            except (TypeError, ValueError):
                continue
        row = {
            "ai_exam_scoring_total": sum(1 for item in scoring_events if item["event_type"] == "ai_exam_scoring"),
            "ai_exam_scoring_rows": sum(int((item.get("meta_json") or {}).get("rows_scored") or 0) for item in scoring_events if item["event_type"] == "ai_exam_scoring"),
            "ai_exam_scoring_answers": sum(int((item.get("meta_json") or {}).get("answer_count") or 0) for item in scoring_events if item["event_type"] == "ai_exam_scoring"),
            "ai_exam_heuristic_total": sum(int((item.get("meta_json") or {}).get("heuristic_count") or 0) for item in scoring_events if item["event_type"] == "ai_exam_scoring"),
            "ai_exam_cache_total": sum(int((item.get("meta_json") or {}).get("cache_hit_count") or 0) for item in scoring_events if item["event_type"] == "ai_exam_scoring"),
            "ai_exam_llm_total": sum(int((item.get("meta_json") or {}).get("llm_count") or 0) for item in scoring_events if item["event_type"] == "ai_exam_scoring"),
            "ai_exam_llm_calls_total": sum(int((item.get("meta_json") or {}).get("llm_calls") or 0) for item in scoring_events if item["event_type"] == "ai_exam_scoring"),
            "ai_exam_failure_total": sum(1 for item in scoring_events if item["event_type"] != "ai_exam_scoring"),
            "ai_exam_invalid_batch_items_total": sum(int((item.get("meta_json") or {}).get("invalid_batch_item_count") or 0) for item in scoring_events if item["event_type"] == "ai_exam_scoring"),
            "ai_exam_retry_batch_items_total": sum(int((item.get("meta_json") or {}).get("retry_batch_items") or 0) for item in scoring_events if item["event_type"] == "ai_exam_scoring"),
            "ai_exam_retry_batch_calls_total": sum(int((item.get("meta_json") or {}).get("retry_batch_calls") or 0) for item in scoring_events if item["event_type"] == "ai_exam_scoring"),
            "ai_exam_retry_single_items_total": sum(int((item.get("meta_json") or {}).get("retry_single_items") or 0) for item in scoring_events if item["event_type"] == "ai_exam_scoring"),
            "ai_exam_retry_single_calls_total": sum(int((item.get("meta_json") or {}).get("retry_single_calls") or 0) for item in scoring_events if item["event_type"] == "ai_exam_scoring"),
            "ai_exam_scoring_ms_p50": self._percentile(scoring_ms_values, 0.5),
            "ai_exam_scoring_ms_p95": self._percentile(scoring_ms_values, 0.95),
        }
        return FakeCursor(rowcount=1, one=row)

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

    def _count_user_api_requests_last_24h(self, params):
        username = str(params[0] or "").strip().lower()
        threshold = datetime.now(timezone.utc) - timedelta(days=1)
        total = 0
        for item in self.state["metric_events"]:
            if item["event_type"] != "api_request":
                continue
            if str(item["username"] or "").strip().lower() != username:
                continue
            created_at = datetime.fromisoformat(str(item["created_at"]).replace("Z", "+00:00"))
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if created_at.astimezone(timezone.utc) >= threshold:
                total += 1
        return FakeCursor(rowcount=1, one={"total": total})

    def _performance_totals(self, params):
        threshold = datetime.now(timezone.utc) - timedelta(minutes=int(params[0]))
        events = []
        for item in self.state["metric_events"]:
            if item["event_type"] != "api_request":
                continue
            created_at = datetime.fromisoformat(str(item["created_at"]).replace("Z", "+00:00"))
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if created_at.astimezone(timezone.utc) >= threshold:
                events.append(item)
        request_count = len(events)
        error_count = sum(1 for item in events if int(item.get("status_code") or 0) >= 400)
        avg_duration_ms = (
            sum(int(item.get("duration_ms") or 0) for item in events if item.get("duration_ms") is not None) / request_count
            if request_count
            else 0
        )
        return FakeCursor(
            rowcount=1,
            one={
                "request_count": request_count,
                "error_count": error_count,
                "api_requests_total": request_count,
                "avg_duration_ms": avg_duration_ms,
                "p50_duration_ms": self._percentile([int(item["duration_ms"]) for item in events if item.get("duration_ms") is not None], 0.5),
                "p95_duration_ms": self._percentile([int(item["duration_ms"]) for item in events if item.get("duration_ms") is not None], 0.95),
                "request_bytes": sum(int(item.get("request_bytes") or 0) for item in events),
                "response_bytes": sum(int(item.get("response_bytes") or 0) for item in events),
                "resource_units": sum(int(item.get("resource_units") or 0) for item in events),
            },
        )

    def _performance_endpoint_rows(self, params):
        threshold = datetime.now(timezone.utc) - timedelta(minutes=int(params[0]))
        endpoint_limit = int(params[1])
        grouped: dict[str, dict[str, object]] = {}
        for item in self.state["metric_events"]:
            if item["event_type"] != "api_request" or not item.get("path"):
                continue
            created_at = datetime.fromisoformat(str(item["created_at"]).replace("Z", "+00:00"))
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if created_at.astimezone(timezone.utc) < threshold:
                continue
            path = str(item["path"] or "").strip()
            if not path:
                continue
            entry = grouped.setdefault(
                path,
                {"path": path, "count": 0, "error_count": 0, "durations": []},
            )
            entry["count"] = int(entry["count"]) + 1
            entry["error_count"] = int(entry["error_count"]) + (1 if int(item.get("status_code") or 0) >= 400 else 0)
            if item.get("duration_ms") is not None:
                durations = entry["durations"]
                assert isinstance(durations, list)
                durations.append(int(item["duration_ms"]))
        rows = []
        for entry in sorted(grouped.values(), key=lambda item: (-int(item["count"]), str(item["path"])) )[:endpoint_limit]:
            durations = [int(item) for item in entry["durations"]]
            rows.append(
                {
                    "path": entry["path"],
                    "count": int(entry["count"]),
                    "error_count": int(entry["error_count"]),
                    "avg_ms": (sum(durations) / len(durations)) if durations else 0,
                    "p50_ms": self._percentile(durations, 0.5),
                    "p95_ms": self._percentile(durations, 0.95),
                }
            )
        return FakeCursor(rowcount=len(rows), rows=rows)


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
        if normalized.startswith("SELECT id, source_row, submitted_at, full_name, discord_tag, passport, exam_format, payload_json, answer_count, import_key, question_g_score, exam_scores_json, average_score FROM exam_answers"):
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
                self._ensure_unique_source_row(int(source_row), row_id=int(row_id))
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
                self._ensure_unique_source_row(int(source_row), row_id=int(row_id))
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
        if normalized.startswith("SELECT source_row, submitted_at, full_name, discord_tag, passport, exam_format, answer_count, average_score, COALESCE(average_score_answer_count, 0) AS average_score_answer_count, needs_rescore, imported_at FROM exam_answers WHERE source_row > 0 ORDER BY source_row DESC LIMIT %s OFFSET %s"):
            return self._list_entries(int(params[0]), int(params[1]))
        if normalized.startswith("SELECT source_row, submitted_at, full_name, discord_tag, passport, exam_format, answer_count, average_score, average_score_answer_count, imported_at FROM exam_answers WHERE source_row > 0 AND average_score IS NULL ORDER BY source_row ASC LIMIT %s"):
            rows = [row for row in self.state["rows"] if row["source_row"] > 0 and row["average_score"] is None]
            rows.sort(key=lambda item: item["source_row"])
            rows = rows[: int(params[0])]
            return FakeCursor(rowcount=len(rows), rows=[self._summary_row(row) for row in rows])
        if normalized.startswith("SELECT source_row, submitted_at, full_name, discord_tag, passport, exam_format, answer_count, average_score, average_score_answer_count, imported_at FROM exam_answers WHERE source_row > 0 AND (average_score IS NULL OR needs_rescore = 1) ORDER BY source_row ASC LIMIT %s") or normalized.startswith("SELECT source_row, submitted_at, full_name, discord_tag, passport, exam_format, answer_count, average_score, average_score_answer_count, imported_at FROM exam_answers WHERE source_row > 0 AND (average_score IS NULL OR needs_rescore IS TRUE) ORDER BY source_row ASC LIMIT %s"):
            rows = [row for row in self.state["rows"] if row["source_row"] > 0 and (row["average_score"] is None or bool(row["needs_rescore"]))]
            rows.sort(key=lambda item: item["source_row"])
            rows = rows[: int(params[0])]
            return FakeCursor(rowcount=len(rows), rows=[self._summary_row(row) for row in rows])
        if normalized.startswith("SELECT COUNT(*) AS total FROM exam_answers WHERE source_row > 0 AND average_score IS NULL"):
            total = sum(1 for row in self.state["rows"] if row["source_row"] > 0 and row["average_score"] is None)
            return FakeCursor(rowcount=1, one={"total": total})
        if normalized.startswith("SELECT COUNT(*) AS total FROM exam_answers WHERE source_row > 0 AND (average_score IS NULL OR needs_rescore = 1)") or normalized.startswith("SELECT COUNT(*) AS total FROM exam_answers WHERE source_row > 0 AND (average_score IS NULL OR needs_rescore IS TRUE)"):
            total = sum(
                1
                for row in self.state["rows"]
                if row["source_row"] > 0 and (row["average_score"] is None or bool(row["needs_rescore"]))
            )
            return FakeCursor(rowcount=1, one={"total": total})
        if normalized.startswith("SELECT COUNT(*) AS total FROM exam_answers WHERE source_row > 0"):
            total = sum(1 for row in self.state["rows"] if row["source_row"] > 0)
            return FakeCursor(rowcount=1, one={"total": total})
        if normalized.startswith("SELECT source_row, submitted_at, full_name, discord_tag, passport, exam_format, answer_count, average_score, COALESCE(average_score_answer_count, 0) AS average_score_answer_count, needs_rescore, imported_at, exam_scores_json FROM exam_answers WHERE source_row > 0 AND exam_scores_json IS NOT NULL"):
            rows = [row for row in self.state["rows"] if row["source_row"] > 0 and row["exam_scores_json"] not in (None, "")]
            rows.sort(key=lambda item: item["source_row"])
            rows = rows[: int(params[0])]
            return FakeCursor(rowcount=len(rows), rows=[{**self._summary_row(row), "exam_scores_json": row["exam_scores_json"]} for row in rows])
        if normalized.startswith("SELECT source_row, submitted_at, full_name, discord_tag, passport, exam_format, answer_count, imported_at, updated_at, question_g_score, question_g_rationale, question_g_scored_at, exam_scores_json, exam_scores_scored_at, average_score, average_score_answer_count, average_score_scored_at, needs_rescore, payload_json FROM exam_answers WHERE source_row = %s"):
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
        if normalized.startswith("UPDATE exam_answers SET question_g_score = NULL, question_g_rationale = NULL, question_g_scored_at = NULL, exam_scores_json = NULL, exam_scores_scored_at = NULL, average_score = NULL, average_score_answer_count = NULL, average_score_scored_at = NULL, needs_rescore = %s, updated_at = NOW() WHERE source_row = %s"):
            return self._reset_scores_for_row(params)
        if normalized.startswith("UPDATE exam_answers SET question_g_score = NULL, question_g_rationale = NULL, question_g_scored_at = NULL, exam_scores_json = NULL, exam_scores_scored_at = NULL, average_score = NULL, average_score_answer_count = NULL, average_score_scored_at = NULL, needs_rescore = %s, updated_at = NOW() WHERE source_row > 0 AND "):
            return self._reset_scores_by_user(normalized, params)

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

    def _ensure_unique_source_row(self, source_row: int, *, row_id: int | None = None) -> None:
        source_row = int(source_row)
        duplicate = next(
            (
                row
                for row in self.state["rows"]
                if row["source_row"] == source_row and (row_id is None or row["id"] != row_id)
            ),
            None,
        )
        if duplicate is not None:
            raise RuntimeError(f'duplicate key value violates unique constraint "exam_answers_source_row_key": {source_row}')

    def _insert_row(self, params):
        source_row, submitted_at, full_name, discord_tag, passport, exam_format, payload_json, answer_count, needs_rescore, import_key = params
        self._ensure_unique_source_row(int(source_row))
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
        self._ensure_unique_source_row(int(source_row), row_id=int(row_id))
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
        self._ensure_unique_source_row(int(source_row), row_id=int(row_id))
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

    def _list_entries(self, limit: int, offset: int = 0):
        rows = [row for row in self.state["rows"] if row["source_row"] > 0]
        rows.sort(key=lambda item: item["source_row"], reverse=True)
        safe_offset = max(0, int(offset or 0))
        rows = rows[safe_offset : safe_offset + limit]
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

    def _reset_scores_by_user(self, normalized_query: str, params):
        if not params:
            return FakeCursor(rowcount=0)
        needs_rescore = bool(params[0])
        filter_values = list(params[1:])
        where_part = normalized_query.split("WHERE source_row > 0 AND ", 1)[1]
        filter_clauses = [part.strip() for part in where_part.split(" AND ") if part.strip()]
        matched_rows = []
        for row in self.state["rows"]:
            if row["source_row"] <= 0:
                continue
            value_index = 0
            is_match = True
            for clause in filter_clauses:
                if clause == "full_name = %s":
                    is_match = is_match and str(row["full_name"]) == str(filter_values[value_index])
                    value_index += 1
                elif clause == "discord_tag = %s":
                    is_match = is_match and str(row["discord_tag"]) == str(filter_values[value_index])
                    value_index += 1
                elif clause == "passport = %s":
                    is_match = is_match and str(row["passport"]) == str(filter_values[value_index])
                    value_index += 1
            if is_match:
                matched_rows.append(row)
        for row in matched_rows:
            row["question_g_score"] = None
            row["question_g_rationale"] = None
            row["question_g_scored_at"] = None
            row["exam_scores_json"] = None
            row["exam_scores_scored_at"] = None
            row["average_score"] = None
            row["average_score_answer_count"] = None
            row["average_score_scored_at"] = None
            row["needs_rescore"] = needs_rescore
            row["updated_at"] = self._now()
        return FakeCursor(rowcount=len(matched_rows))

    def _reset_scores_for_row(self, params):
        needs_rescore, source_row = params
        row = self._find_by_source_row(int(source_row))
        if row is None:
            return FakeCursor(rowcount=0)
        row["question_g_score"] = None
        row["question_g_rationale"] = None
        row["question_g_scored_at"] = None
        row["exam_scores_json"] = None
        row["exam_scores_scored_at"] = None
        row["average_score"] = None
        row["average_score_answer_count"] = None
        row["average_score_scored_at"] = None
        row["needs_rescore"] = bool(needs_rescore)
        row["updated_at"] = self._now()
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
            store = UserStore(root / "app.db", root / "users.json", repository=UserRepository(PostgresBackend()))

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
            store = UserStore(root / "custom.db", root / "users.json", repository=UserRepository(PostgresBackend()))
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
            store = UserStore(root / "reset.db", root / "users.json", repository=UserRepository(PostgresBackend()))
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
            store = ExamAnswersStore(root / "exam_answers.db", backend=FakeExamAnswersPostgresBackend())
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
            store = ExamAnswersStore(root / "exam_answers.db", backend=FakeExamAnswersPostgresBackend())
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

    def test_exam_answers_store_releases_source_row_before_inserting_new_shifted_entry(self):
        tmpdir = make_temp_dir()
        try:
            root = Path(tmpdir)
            store = ExamAnswersStore(root / "exam_answers.db", backend=FakeExamAnswersPostgresBackend())
            original_row = {
                "source_row": 7,
                "submitted_at": "2026-04-08 12:00:00",
                "full_name": "Existing User",
                "discord_tag": "existing",
                "passport": "700001",
                "exam_format": "remote",
                "payload": {
                    "submitted_at": "2026-04-08 12:00:00",
                    "full_name": "Existing User",
                    "discord_tag": "existing",
                    "passport": "700001",
                    "exam_format": "remote",
                    "Question F": "Answer F",
                    "Question G": "Answer G",
                },
                "answer_count": 2,
            }
            store.import_rows([original_row])

            shifted_rows = [
                {
                    "source_row": 7,
                    "submitted_at": "2026-04-09 09:00:00",
                    "full_name": "New User",
                    "discord_tag": "new",
                    "passport": "700002",
                    "exam_format": "remote",
                    "payload": {
                        "submitted_at": "2026-04-09 09:00:00",
                        "full_name": "New User",
                        "discord_tag": "new",
                        "passport": "700002",
                        "exam_format": "remote",
                        "Question F": "Other F",
                        "Question G": "Other G",
                    },
                    "answer_count": 2,
                },
                {
                    "source_row": 8,
                    "submitted_at": "2026-04-08 12:00:00",
                    "full_name": "Existing User",
                    "discord_tag": "existing",
                    "passport": "700001",
                    "exam_format": "remote",
                    "payload": {
                        "submitted_at": "2026-04-08 12:00:00",
                        "full_name": "Existing User",
                        "discord_tag": "existing",
                        "passport": "700001",
                        "exam_format": "remote",
                        "Question F": "Answer F",
                        "Question G": "Answer G",
                    },
                    "answer_count": 2,
                },
            ]

            result = store.import_rows(shifted_rows)

            self.assertEqual(result["inserted_count"], 1)
            self.assertEqual(result["updated_count"], 1)
            self.assertIsNotNone(store.get_entry(7))
            self.assertIsNotNone(store.get_entry(8))
            self.assertEqual(store.get_entry(7)["full_name"], "New User")
            self.assertEqual(store.get_entry(8)["full_name"], "Existing User")
        finally:
            del store
            gc.collect()
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_exam_answers_store_keeps_reference_answers_in_reserved_slot(self):
        tmpdir = make_temp_dir()
        try:
            root = Path(tmpdir)
            store = ExamAnswersStore(root / "exam_answers.db", backend=FakeExamAnswersPostgresBackend())
            result = store.import_rows(
                [
                    {
                        "source_row": 2,
                        "submitted_at": "2026-04-08 12:00:00",
                        "full_name": "Candidate User",
                        "discord_tag": "candidate",
                        "passport": "700010",
                        "exam_format": "remote",
                        "payload": {
                            "submitted_at": "2026-04-08 12:00:00",
                            "full_name": "Candidate User",
                            "discord_tag": "candidate",
                            "passport": "700010",
                            "format": "remote",
                            "Question F": "Answer F",
                        },
                        "answer_count": 1,
                    },
                    {
                        "source_row": 9,
                        "submitted_at": "",
                        "full_name": "эталонные ответы",
                        "discord_tag": "",
                        "passport": "",
                        "exam_format": "эталонные ответы",
                        "payload": {
                            "submitted_at": "",
                            "full_name": "эталонные ответы",
                            "discord_tag": "эталонные ответы",
                            "passport": "",
                            "format": "эталонные ответы",
                            "Question F": "Reference F",
                        },
                        "answer_count": 1,
                    },
                ]
            )

            self.assertEqual(result["inserted_count"], 1)
            self.assertEqual(result["updated_count"], 0)
            self.assertEqual(result["total_rows"], 1)
            self.assertIsNotNone(store.get_entry(2))
            self.assertIsNone(store.get_entry(9))
            self.assertEqual(len(store.list_entries(limit=10)), 1)
            self.assertEqual(len(store.list_entries_needing_scores(limit=10)), 1)

            reference_entry = store.get_reference_entry()
            self.assertIsNotNone(reference_entry)
            self.assertEqual(reference_entry["source_row"], 0)
            self.assertEqual(reference_entry["full_name"], "эталонные ответы")
            self.assertFalse(reference_entry["needs_rescore"])
        finally:
            del store
            gc.collect()
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_exam_answers_store_migrates_legacy_reference_row_to_reserved_slot(self):
        tmpdir = make_temp_dir()
        try:
            root = Path(tmpdir)
            backend = FakeExamAnswersPostgresBackend()
            store = ExamAnswersStore(root / "exam_answers.db", backend=backend)
            legacy_conn = FakeExamAnswersConnection(backend._state)
            legacy_payload = {
                "submitted_at": "",
                "full_name": "эталонные ответы",
                "discord_tag": "эталонные ответы",
                "passport": "",
                "format": "эталонные ответы",
                "Question F": "Reference F",
            }
            legacy_conn._insert_row(
                (
                    9,
                    "",
                    "эталонные ответы",
                    "",
                    "",
                    "эталонные ответы",
                    json.dumps(legacy_payload, ensure_ascii=False),
                    1,
                    True,
                    "legacy-reference",
                )
            )
            backend._state["rows"][0]["exam_scores_json"] = json.dumps(
                [{"column": "F", "score": 50, "rationale": "legacy"}],
                ensure_ascii=False,
            )
            backend._state["rows"][0]["average_score"] = 50.0

            result = store.import_rows(
                [
                    {
                        "source_row": 2,
                        "submitted_at": "2026-04-09 09:00:00",
                        "full_name": "Candidate User",
                        "discord_tag": "candidate",
                        "passport": "700011",
                        "exam_format": "remote",
                        "payload": {
                            "submitted_at": "2026-04-09 09:00:00",
                            "full_name": "Candidate User",
                            "discord_tag": "candidate",
                            "passport": "700011",
                            "format": "remote",
                            "Question F": "Answer F",
                        },
                        "answer_count": 1,
                    }
                ]
            )

            self.assertEqual(result["inserted_count"], 1)
            self.assertEqual(result["total_rows"], 1)
            self.assertIsNone(store.get_entry(9))
            reference_entry = store.get_reference_entry()
            self.assertIsNotNone(reference_entry)
            self.assertEqual(reference_entry["source_row"], 0)
            self.assertEqual(reference_entry["full_name"], "эталонные ответы")
            self.assertFalse(reference_entry["needs_rescore"])
            self.assertEqual(reference_entry["exam_scores"], [])
            self.assertIsNone(reference_entry["average_score"])
        finally:
            del store
            gc.collect()
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_exam_answers_store_frees_legacy_reference_row_before_inserting_new_candidate(self):
        tmpdir = make_temp_dir()
        try:
            root = Path(tmpdir)
            backend = FakeExamAnswersPostgresBackend()
            store = ExamAnswersStore(root / "exam_answers.db", backend=backend)
            legacy_conn = FakeExamAnswersConnection(backend._state)
            legacy_payload = {
                "submitted_at": "",
                "full_name": "эталонные ответы",
                "discord_tag": "эталонные ответы",
                "passport": "",
                "format": "эталонные ответы",
                "Question F": "Reference F",
            }
            legacy_conn._insert_row(
                (
                    9,
                    "",
                    "эталонные ответы",
                    "эталонные ответы",
                    "",
                    "эталонные ответы",
                    json.dumps(legacy_payload, ensure_ascii=False),
                    1,
                    True,
                    "legacy-reference",
                )
            )

            result = store.import_rows(
                [
                    {
                        "source_row": 9,
                        "submitted_at": "2026-04-10 10:00:00",
                        "full_name": "New Candidate",
                        "discord_tag": "candidate",
                        "passport": "700012",
                        "exam_format": "remote",
                        "payload": {
                            "submitted_at": "2026-04-10 10:00:00",
                            "full_name": "New Candidate",
                            "discord_tag": "candidate",
                            "passport": "700012",
                            "format": "remote",
                            "Question F": "Candidate F",
                        },
                        "answer_count": 1,
                    },
                    {
                        "source_row": 10,
                        "submitted_at": "",
                        "full_name": "эталонные ответы",
                        "discord_tag": "эталонные ответы",
                        "passport": "",
                        "exam_format": "эталонные ответы",
                        "payload": legacy_payload,
                        "answer_count": 1,
                    },
                ]
            )

            self.assertEqual(result["inserted_count"], 1)
            self.assertEqual(result["total_rows"], 1)
            self.assertEqual(store.get_entry(9)["full_name"], "New Candidate")
            self.assertIsNone(store.get_entry(10))
            reference_entry = store.get_reference_entry()
            self.assertIsNotNone(reference_entry)
            self.assertEqual(reference_entry["source_row"], 0)
            self.assertEqual(reference_entry["full_name"], "эталонные ответы")
        finally:
            del store
            gc.collect()
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_exam_answers_store_preserves_scores_when_identity_fields_change_but_answers_match(self):
        tmpdir = make_temp_dir()
        try:
            root = Path(tmpdir)
            store = ExamAnswersStore(root / "exam_answers.db", backend=FakeExamAnswersPostgresBackend())
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

    def test_exam_answers_store_preserves_scores_when_timestamp_changes_but_answers_match(self):
        tmpdir = make_temp_dir()
        try:
            root = Path(tmpdir)
            store = ExamAnswersStore(root / "exam_answers.db", backend=FakeExamAnswersPostgresBackend())
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
                "source_row": 5,
                "submitted_at": "2026-04-08 12:05:00",
                "full_name": "Student One Updated",
                "discord_tag": "student1_new",
                "passport": "999999",
                "exam_format": "remote",
                "payload": {
                    "submitted_at": "2026-04-08 12:05:00",
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
            rescored = store.get_entry(5)

            self.assertEqual(result["inserted_count"], 0)
            self.assertEqual(result["updated_count"], 1)
            self.assertIsNone(store.get_entry(2))
            self.assertIsNotNone(rescored)
            self.assertEqual(rescored["full_name"], "Student One Updated")
            self.assertEqual(rescored["average_score"], 90.0)
            self.assertEqual(rescored["average_score_answer_count"], 2)
            self.assertEqual(rescored["needs_rescore"], 0)
        finally:
            del store
            gc.collect()
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_exam_answers_store_preserves_scores_when_payload_order_changes_but_answers_match(self):
        tmpdir = make_temp_dir()
        try:
            root = Path(tmpdir)
            store = ExamAnswersStore(root / "exam_answers.db", backend=FakeExamAnswersPostgresBackend())
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
            reordered = {
                "source_row": 2,
                "submitted_at": "2026-04-08 12:00:00",
                "full_name": "Student One",
                "discord_tag": "student1",
                "passport": "111111",
                "exam_format": "remote",
                "payload": {
                    "Question G": "Answer G",
                    "exam_format": "remote",
                    "passport": "111111",
                    "Question F": "Answer F",
                    "submitted_at": "2026-04-08 12:00:00",
                    "discord_tag": "student1",
                    "full_name": "Student One",
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

            result = store.import_rows([reordered])
            rescored = store.get_entry(2)

            self.assertEqual(result["inserted_count"], 0)
            self.assertEqual(result["updated_count"], 1)
            self.assertIsNotNone(rescored)
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

    def test_postgres_read_queries_close_connections(self):
        backend = PostgresBackend()
        repository = UserRepository(backend)
        store = UserStore(Path("ignored.db"), Path("ignored.json"), repository=repository)
        try:
            initial_closed = backend._state["closed_connections"]
            store._pg_fetchone("SELECT 1")
            after_fetchone = backend._state["closed_connections"]
            store._pg_fetchall("SELECT 1")
            after_fetchall = backend._state["closed_connections"]
            store._pg_execute("INSERT INTO servers (code, title) VALUES (%s, %s) ON CONFLICT (code) DO NOTHING", ("demo", "Demo"))
            after_execute = backend._state["closed_connections"]
        finally:
            repository.close()

        self.assertGreater(after_fetchone, initial_closed)
        self.assertGreater(after_fetchall, after_fetchone)
        self.assertGreater(after_execute, after_fetchall)

    def test_postgres_fetchone_can_commit_write_transactions(self):
        backend = PostgresBackend()
        repository = UserRepository(backend)
        store = UserStore(Path("ignored.db"), Path("ignored.json"), repository=repository)
        try:
            initial_commits = backend._state["commit_calls"]
            row = store._pg_fetchone("SELECT 1", commit=True)
        finally:
            repository.close()

        self.assertEqual(row["?column?"], 1)
        self.assertGreater(backend._state["commit_calls"], initial_commits)


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
        store = AdminMetricsStore(root / "admin_metrics.db", backend=FakeAdminMetricsPostgresBackend())

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
        store = AdminMetricsStore(root / "admin_metrics.db", backend=FakeAdminMetricsPostgresBackend())

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

    def test_postgres_admin_metrics_store_keeps_full_history_for_ai_exam_totals(self):
        store = self.make_store()

        self.assertTrue(
            store.log_event(
                event_type="ai_exam_scoring",
                username="alpha",
                server_code="blackberry",
                path="/api/exam-import/score",
                method="POST",
                status_code=200,
                meta={"rows_scored": 1, "answer_count": 4, "scoring_ms": 120},
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
                meta={"rows_scored": 2, "answer_count": 8, "scoring_ms": 180},
            )
        )
        store.backend._state["metric_events"][0]["created_at"] = "2026-03-01T00:00:00+00:00"

        overview = store.get_overview(users=[])

        self.assertEqual(overview["totals"]["ai_exam_scoring_total"], 2)
        self.assertEqual(overview["totals"]["ai_exam_scoring_rows"], 3)
        self.assertEqual(overview["totals"]["ai_exam_scoring_answers"], 12)

    def test_postgres_admin_metrics_store_trims_and_deduplicates_endpoint_paths(self):
        store = self.make_store()

        self.assertTrue(
            store.log_event(
                event_type="api_request",
                username="alpha",
                server_code="blackberry",
                path="  /api/test  ",
                method="POST",
                status_code=200,
                duration_ms=100,
            )
        )
        self.assertTrue(
            store.log_event(
                event_type="api_request",
                username="alpha",
                server_code="blackberry",
                path="/api/test",
                method="POST",
                status_code=500,
                duration_ms=200,
            )
        )
        self.assertTrue(
            store.log_event(
                event_type="api_request",
                username="alpha",
                server_code="blackberry",
                path="   ",
                method="POST",
                status_code=200,
                duration_ms=300,
            )
        )

        overview = store.get_performance_overview(window_minutes=60, top_endpoints=10)

        self.assertEqual(len(overview["endpoint_overview"]), 1)
        self.assertEqual(overview["endpoint_overview"][0]["path"], "/api/test")
        self.assertEqual(overview["endpoint_overview"][0]["count"], 2)
        self.assertEqual(overview["endpoint_overview"][0]["error_count"], 1)


class PostgresAdminMetricsStoreSchemaMigrationTests(unittest.TestCase):
    def test_store_initialization_fails_for_old_metric_events_schema_without_required_columns(self):
        tmpdir = make_temp_dir()
        self.addCleanup(shutil.rmtree, tmpdir, True)
        root = Path(tmpdir)
        backend = FakeAdminMetricsPostgresBackend(
            metric_columns={
                "id",
                "created_at",
                "username",
                "event_type",
                "path",
                "method",
                "status_code",
                "duration_ms",
                "request_bytes",
                "response_bytes",
                "resource_units",
            }
        )

        with self.assertRaises(DatabaseSchemaError) as exc_info:
            AdminMetricsStore(root / "admin_metrics.db", backend=backend)

        message = str(exc_info.exception)
        self.assertIn("metric_events schema is missing required columns", message)
        self.assertIn("server_code", message)
        self.assertIn("meta_json", message)

    def test_store_initialization_skips_metric_events_migration_when_table_absent(self):
        tmpdir = make_temp_dir()
        self.addCleanup(shutil.rmtree, tmpdir, True)
        root = Path(tmpdir)
        backend = FakeAdminMetricsPostgresBackend(
            has_metric_events_table=False,
            metric_columns=set(),
        )

        AdminMetricsStore(root / "admin_metrics.db", backend=backend)

        self.assertNotIn("server_code", backend._state["metric_columns"])
        self.assertNotIn("meta_json", backend._state["metric_columns"])


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
        self.assertEqual(updated_result["inserted_count"], 0)
        self.assertEqual(updated_result["updated_count"], 1)
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

    def test_postgres_exam_answers_store_needs_scores_targets_new_rows_only_by_default(self):
        store = self.make_store()
        store.import_rows(
            [
                {
                    "source_row": 2,
                    "submitted_at": "2026-04-08 12:00:00",
                    "full_name": "Needs Score",
                    "discord_tag": "needs-score",
                    "passport": "123123",
                    "exam_format": "remote",
                    "payload": {"Question F": "Answer"},
                    "answer_count": 1,
                }
            ]
        )
        store.save_exam_scores(2, [{"column": "F", "score": 1, "rationale": INVALID_BATCH_RATIONALE}])

        self.assertEqual(store.count_entries_needing_scores(), 0)
        self.assertEqual(len(store.list_entries_needing_scores(limit=10)), 0)
        self.assertEqual(store.count_entries_needing_scores(include_rescore=True), 1)
        self.assertEqual(len(store.list_entries_needing_scores(limit=10, include_rescore=True)), 1)

    def test_postgres_exam_answers_store_can_reset_scores_for_specific_user(self):
        store = self.make_store()
        store.import_rows(
            [
                {
                    "source_row": 2,
                    "submitted_at": "2026-04-08 12:00:00",
                    "full_name": "Target User",
                    "discord_tag": "target#1",
                    "passport": "456456",
                    "exam_format": "remote",
                    "payload": {"Question F": "Answer A"},
                    "answer_count": 1,
                },
                {
                    "source_row": 3,
                    "submitted_at": "2026-04-08 12:05:00",
                    "full_name": "Other User",
                    "discord_tag": "other#1",
                    "passport": "789789",
                    "exam_format": "remote",
                    "payload": {"Question F": "Answer B"},
                    "answer_count": 1,
                },
            ]
        )
        store.save_exam_scores(2, [{"column": "F", "score": 91, "rationale": "ok"}])
        store.save_exam_scores(3, [{"column": "F", "score": 93, "rationale": "ok"}])

        reset_count = store.reset_scores_for_user(discord_tag="target#1")
        self.assertEqual(reset_count, 1)

        target = store.get_entry(2)
        other = store.get_entry(3)
        self.assertIsNotNone(target)
        self.assertIsNone(target["average_score"])
        self.assertEqual(target["exam_scores"], [])
        self.assertTrue(bool(target["needs_rescore"]))
        self.assertIsNotNone(other)
        self.assertEqual(other["average_score"], 93.0)

    def test_postgres_exam_answers_store_inserts_new_attempt_when_same_row_is_reused_later(self):
        store = self.make_store()

        first = {
            "source_row": 2,
            "submitted_at": "2026-04-08 12:00:00",
            "full_name": "First User",
            "discord_tag": "first",
            "passport": "123456",
            "exam_format": "remote",
            "payload": {"name": "First User", "Question F": "Answer F"},
            "answer_count": 1,
        }
        replacement = {
            "source_row": 2,
            "submitted_at": "2026-04-09 09:00:00",
            "full_name": "Second User",
            "discord_tag": "second",
            "passport": "654321",
            "exam_format": "remote",
            "payload": {"name": "Second User", "Question F": "Other F"},
            "answer_count": 1,
        }

        first_result = store.import_rows([first])
        replacement_result = store.import_rows([replacement])

        self.assertEqual(first_result["inserted_count"], 1)
        self.assertEqual(replacement_result["inserted_count"], 1)
        self.assertEqual(replacement_result["updated_count"], 0)
        self.assertEqual(store.count(), 1)
        self.assertEqual(store.get_entry(2)["full_name"], "Second User")

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

    def test_postgres_exam_answers_store_preserves_scores_when_timestamp_changes_but_answers_match(self):
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
            "source_row": 5,
            "submitted_at": "2026-04-08 12:05:00",
            "full_name": "Student One Updated",
            "discord_tag": "student1_new",
            "passport": "999999",
            "exam_format": "remote",
            "payload": {
                "submitted_at": "2026-04-08 12:05:00",
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
        rescored = store.get_entry(5)

        self.assertEqual(result["inserted_count"], 0)
        self.assertEqual(result["updated_count"], 1)
        self.assertIsNone(store.get_entry(2))
        self.assertIsNotNone(rescored)
        self.assertEqual(rescored["average_score"], 90.0)
        self.assertEqual(rescored["average_score_answer_count"], 2)
        self.assertEqual(rescored["needs_rescore"], 0)


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


class ValidationDomainTests(unittest.TestCase):
    def setUp(self):
        self.backend = PostgresBackend()
        self.validation_repo = __import__('ogp_web.storage.validation_repository', fromlist=['ValidationRepository']).ValidationRepository(self.backend)
        self.validation_service = __import__('ogp_web.services.validation_service', fromlist=['ValidationService']).ValidationService(self.validation_repo)
        self.backend._state["users"]["validator"] = {"id": 1, "username": "validator", "email": "validator@example.com"}
        self.backend._state["cases"][1] = {"id": 1, "server_id": "blackberry", "owner_user_id": 1}
        self.backend._state["case_documents"][1] = {"id": 1, "case_id": 1, "server_id": "blackberry", "document_type": "complaint"}
        self.backend._state["document_versions"][1] = {"id": 1, "document_id": 1, "version_number": 1, "content_json": {"bbcode": "no citations"}, "created_by": 1, "generation_snapshot_id": None, "created_at": "2026-01-01T00:00:00+00:00"}

    def test_validation_scoring_and_immutability(self):
        self.backend._state['validation_requirements'][1] = {
            'id': 1, 'server_scope': 'server', 'server_id': 'blackberry', 'target_type': 'document_version', 'target_subtype': 'complaint',
            'field_key': 'bbcode', 'rule_json': {'expected_type': 'str'}, 'is_required': True, 'is_active': True, 'created_at': '', 'updated_at': ''
        }
        first = self.validation_service.run_validation(target_type='document_version', target_id=1)
        second = self.validation_service.run_validation(target_type='document_version', target_id=1)
        self.assertNotEqual(first.run['id'], second.run['id'])
        self.assertGreaterEqual(second.run['risk_score'], 0)
        self.assertLessEqual(second.run['coverage_score'], 100)

    def test_gate_warn_vs_hard_block(self):
        self.backend._state['readiness_gates'][1] = {
            'id': 1, 'server_scope': 'server', 'server_id': 'blackberry', 'target_type': 'document_version', 'target_subtype': 'complaint',
            'gate_code': 'coverage_gate', 'enforcement_mode': 'warn', 'threshold_json': {'min_coverage_score': 101}, 'is_active': True, 'created_at': '', 'updated_at': ''
        }
        self.validation_service.run_validation(target_type='document_version', target_id=1)
        allowed, messages = self.validation_service.assert_action_allowed(target_type='document_version', target_id=1, action='export')
        self.assertTrue(allowed)
        self.assertTrue(any('warn' in item for item in messages))
        self.backend._state['readiness_gates'][1]['enforcement_mode'] = 'hard_block'
        self.validation_service.run_validation(target_type='document_version', target_id=1)
        allowed2, _ = self.validation_service.assert_action_allowed(target_type='document_version', target_id=1, action='publish')
        self.assertFalse(allowed2)

    def test_law_qa_validation_binding(self):
        qa_run = self.validation_repo.create_law_qa_run(
            server_id='blackberry', user_id=1, question='Q?', answer_text='A', used_sources=[], selected_norms=[], metadata={}
        )
        result = self.validation_service.run_validation(target_type='law_qa_run', target_id=int(qa_run['id']))
        self.assertEqual(result.run['target_type'], 'law_qa_run')
        self.assertEqual(result.run['target_id'], int(qa_run['id']))

    def test_new_version_requires_new_validation(self):
        self.validation_service.run_validation(target_type='document_version', target_id=1)
        self.backend.connect().execute("INSERT INTO document_versions (document_id, version_number, content_json, created_by, generation_snapshot_id) VALUES (%s, %s, %s::jsonb, %s, %s)", (1, 2, json.dumps({'bbcode': 'v2'}), 1, None))
        allowed, _ = self.validation_service.assert_action_allowed(target_type='document_version', target_id=2, action='export')
        self.assertFalse(allowed)

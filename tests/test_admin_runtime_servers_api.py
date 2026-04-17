from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from urllib.parse import urlsplit
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

os.environ.setdefault("OGP_WEB_SECRET", "test-secret")
os.environ.setdefault("OGP_DB_BACKEND", "postgres")
os.environ.setdefault("OGP_SKIP_DEFAULT_APP_INIT", "1")

from fastapi.testclient import TestClient

from ogp_web.app import create_app
from ogp_web.dependencies import (
    get_admin_dashboard_service,
    get_canonical_law_document_versions_store,
    get_content_workflow_service,
    get_law_source_sets_store,
    get_runtime_law_sets_store,
    get_runtime_servers_store,
    get_server_effective_law_projections_store,
)
import ogp_web.routes.admin as admin_route
from ogp_web.rate_limit import reset_for_testing as reset_rate_limit
import ogp_web.services.admin_runtime_servers_service as admin_runtime_servers_service
from ogp_web.services.law_version_service import ResolvedLawVersion
from ogp_web.storage.admin_metrics_store import AdminMetricsStore
from ogp_web.storage.exam_answers_store import ExamAnswersStore
from ogp_web.storage.user_repository import UserRepository
from ogp_web.storage.user_store import UserStore
from tests.temp_helpers import make_temporary_directory
from tests.second_server_fixtures import orange_published_pack
from tests.test_web_storage import (
    FakeAdminMetricsPostgresBackend,
    FakeExamAnswersPostgresBackend,
    FakeExamImportTasksPostgresBackend,
    PostgresBackend,
)
from ogp_web.services.exam_import_tasks import ExamImportTaskRegistry


class _FakeRuntimeServersStore:
    def __init__(self):
        self.rows = {
            "blackberry": {
                "code": "blackberry",
                "title": "BlackBerry",
                "is_active": True,
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        }

    class _Record:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    @staticmethod
    def to_payload(record):
        return dict(record.__dict__)

    def list_servers(self):
        return [self._Record(**value) for _, value in sorted(self.rows.items())]

    def get_server(self, *, code: str):
        row = self.rows.get(code)
        return self._Record(**row) if row else None

    def create_server(self, *, code: str, title: str):
        if code in self.rows:
            raise ValueError("server_code_already_exists")
        row = {"code": code, "title": title, "is_active": False, "created_at": "2026-04-14T00:00:00+00:00"}
        self.rows[code] = row
        return self._Record(**row)

    def update_server(self, *, code: str, title: str):
        if code not in self.rows:
            raise KeyError("server_not_found")
        self.rows[code]["title"] = title
        return self._Record(**self.rows[code])

    def set_active(self, *, code: str, is_active: bool):
        if code not in self.rows:
            raise KeyError("server_not_found")
        self.rows[code]["is_active"] = bool(is_active)
        return self._Record(**self.rows[code])




class _FakeContentWorkflowService:
    class _Repository:
        def __init__(self, service: "_FakeContentWorkflowService"):
            self._service = service

        def get_content_item_by_identity(self, *, server_scope: str, server_id: str | None, content_type: str, content_key: str):
            return self._service._find_item(
                server_scope=server_scope,
                server_id=server_id,
                content_type=content_type,
                content_key=content_key,
            )

    def __init__(self):
        self.calls: list[dict[str, object]] = []
        self.repository = self._Repository(self)
        self._next_item_id = 10
        self._next_version_id = 100
        self._next_change_request_id = 1000
        self.items = [
            {
                "id": 1,
                "server_scope": "global",
                "server_id": None,
                "content_type": "features",
                "content_key": "complaint_intake",
                "title": "Оформление жалобы",
                "status": "published",
                "current_published_version_id": 11,
                "metadata_json": {},
            },
            {
                "id": 2,
                "server_scope": "server",
                "server_id": "blackberry",
                "content_type": "features",
                "content_key": "complaint_intake",
                "title": "Оформление жалобы",
                "status": "published",
                "current_published_version_id": 21,
                "metadata_json": {"workspace": "server-centric"},
            },
            {
                "id": 3,
                "server_scope": "global",
                "server_id": None,
                "content_type": "templates",
                "content_key": "complaint_template_v1",
                "title": "Жалоба",
                "status": "published",
                "current_published_version_id": 31,
                "metadata_json": {},
            },
        ]
        self.versions = {
            1: [
                {"id": 11, "payload_json": {"feature_code": "complaint_intake", "title": "Оформление жалобы", "enabled": True, "rollout": "global", "owner": "ops", "notes": "", "status": "published", "order": 10, "hidden": False}},
            ],
            2: [
                {"id": 21, "payload_json": {"feature_code": "complaint_intake", "title": "Оформление жалобы", "enabled": True, "rollout": "blackberry", "owner": "ops", "notes": "server override", "status": "published", "order": 1, "hidden": False}},
            ],
            3: [
                {"id": 31, "payload_json": {"template_code": "complaint_template_v1", "title": "Жалоба", "body": "[b]{{document_title}}[/b]\n{{result}}", "format": "bbcode", "status": "published", "notes": ""}},
            ],
        }
        self.change_requests = {
            1: [],
            2: [],
            3: [],
        }

    def _find_item(self, *, server_scope: str, server_id: str | None, content_type: str, content_key: str):
        normalized_server_scope = str(server_scope or "").strip().lower()
        normalized_server_id = str(server_id or "").strip().lower() or None
        normalized_content_type = str(content_type or "").strip().lower()
        normalized_content_key = str(content_key or "").strip().lower()
        for item in self.items:
            if str(item.get("server_scope") or "").strip().lower() != normalized_server_scope:
                continue
            if (str(item.get("server_id") or "").strip().lower() or None) != normalized_server_id:
                continue
            if str(item.get("content_type") or "").strip().lower() != normalized_content_type:
                continue
            if str(item.get("content_key") or "").strip().lower() != normalized_content_key:
                continue
            return dict(item)
        return None

    def list_content_items(self, *, server_scope: str, server_id: str | None, content_type: str | None = None, include_legacy_fallback: bool = False):
        self.calls.append(
            {
                "kind": "list_content_items",
                "server_scope": server_scope,
                "server_id": server_id,
                "content_type": content_type,
                "include_legacy_fallback": include_legacy_fallback,
            }
        )
        items = []
        for item in self.items:
            if str(item.get("server_scope") or "").strip().lower() != str(server_scope or "").strip().lower():
                continue
            if (str(item.get("server_id") or "").strip().lower() or None) != (str(server_id or "").strip().lower() or None):
                continue
            if content_type and str(item.get("content_type") or "").strip().lower() != str(content_type or "").strip().lower():
                continue
            items.append(dict(item))
        if not items and str(content_type or "").strip().lower() == "procedures":
            items.append(
                {
                    "id": 42,
                    "server_scope": server_scope,
                    "server_id": server_id,
                    "content_type": "procedures",
                    "content_key": "complaint_law_index",
                    "title": "Complaint law index",
                    "status": "draft",
                    "current_published_version_id": None,
                    "metadata_json": {},
                }
            )
        return {
            "items": items,
            "legacy_fallback": [],
        }

    def get_content_item(self, *, content_item_id: int, server_scope: str, server_id: str | None):
        self.calls.append(
            {
                "kind": "get_content_item",
                "content_item_id": content_item_id,
                "server_scope": server_scope,
                "server_id": server_id,
            }
        )
        for item in self.items:
            if int(item.get("id") or 0) != int(content_item_id):
                continue
            if str(item.get("server_scope") or "").strip().lower() != str(server_scope or "").strip().lower():
                continue
            if (str(item.get("server_id") or "").strip().lower() or None) != (str(server_id or "").strip().lower() or None):
                continue
            return dict(item)
        raise KeyError("content_item_not_found")

    def create_content_item(self, *, server_scope: str, server_id: str | None, content_type: str, content_key: str, title: str, metadata_json: dict | None = None, actor_user_id: int, request_id: str):
        self.calls.append(
            {
                "kind": "create_content_item",
                "server_scope": server_scope,
                "server_id": server_id,
                "content_type": content_type,
                "content_key": content_key,
                "actor_user_id": actor_user_id,
                "request_id": request_id,
            }
        )
        item = {
            "id": self._next_item_id,
            "server_scope": server_scope,
            "server_id": server_id,
            "content_type": content_type,
            "content_key": content_key,
            "title": title,
            "status": "draft",
            "current_published_version_id": None,
            "metadata_json": dict(metadata_json or {}),
        }
        self._next_item_id += 1
        self.items.append(item)
        self.versions[item["id"]] = []
        self.change_requests[item["id"]] = []
        return dict(item)

    def list_versions(self, *, content_item_id: int, server_scope: str, server_id: str | None):
        self.calls.append(
            {
                "kind": "list_versions",
                "content_item_id": content_item_id,
                "server_scope": server_scope,
                "server_id": server_id,
            }
        )
        _ = server_scope
        _ = server_id
        return [dict(row) for row in self.versions.get(int(content_item_id), [])]

    def list_change_requests(self, *, content_item_id: int, server_scope: str, server_id: str | None):
        self.calls.append(
            {
                "kind": "list_change_requests",
                "content_item_id": content_item_id,
                "server_scope": server_scope,
                "server_id": server_id,
            }
        )
        return [dict(row) for row in self.change_requests.get(int(content_item_id), [])]

    def create_draft_version(self, *, content_item_id: int, payload_json: dict, schema_version: int, actor_user_id: int, request_id: str, server_scope: str, server_id: str | None, comment: str = ""):
        self.calls.append(
            {
                "kind": "create_draft_version",
                "content_item_id": content_item_id,
                "schema_version": schema_version,
                "actor_user_id": actor_user_id,
                "request_id": request_id,
                "server_scope": server_scope,
                "server_id": server_id,
                "comment": comment,
            }
        )
        version = {
            "id": self._next_version_id,
            "payload_json": dict(payload_json),
        }
        self._next_version_id += 1
        self.versions.setdefault(int(content_item_id), []).append(version)
        change_request = {
            "id": self._next_change_request_id,
            "status": "draft",
            "candidate_version_id": int(version["id"]),
        }
        self._next_change_request_id += 1
        self.change_requests.setdefault(int(content_item_id), []).insert(0, change_request)
        for item in self.items:
            if int(item.get("id") or 0) == int(content_item_id):
                item["status"] = "draft"
                break
        return {"version": dict(version), "change_request": dict(change_request)}

    def submit_change_request(self, *, change_request_id: int, actor_user_id: int, request_id: str, server_scope: str, server_id: str | None):
        self.calls.append(
            {
                "kind": "submit_change_request",
                "change_request_id": change_request_id,
                "actor_user_id": actor_user_id,
                "request_id": request_id,
                "server_scope": server_scope,
                "server_id": server_id,
            }
        )
        return self._mutate_change_request(change_request_id=change_request_id, new_status="in_review", item_status="in_review")

    def review_change_request(self, *, change_request_id: int, reviewer_user_id: int, decision: str, comment: str, diff_json: dict, request_id: str, server_scope: str, server_id: str | None):
        self.calls.append(
            {
                "kind": "review_change_request",
                "change_request_id": change_request_id,
                "reviewer_user_id": reviewer_user_id,
                "decision": decision,
                "comment": comment,
                "diff_json": dict(diff_json or {}),
                "request_id": request_id,
                "server_scope": server_scope,
                "server_id": server_id,
            }
        )
        new_status = "approved" if decision == "approve" else "request_changes"
        item_status = "approved" if decision == "approve" else "draft"
        return self._mutate_change_request(change_request_id=change_request_id, new_status=new_status, item_status=item_status)

    def publish_change_request(self, *, change_request_id: int, actor_user_id: int, request_id: str, summary_json: dict, server_scope: str, server_id: str | None):
        self.calls.append(
            {
                "kind": "publish_change_request",
                "change_request_id": change_request_id,
                "actor_user_id": actor_user_id,
                "request_id": request_id,
                "summary_json": dict(summary_json or {}),
                "server_scope": server_scope,
                "server_id": server_id,
            }
        )
        for item in self.items:
            for change_request in self.change_requests.get(int(item["id"]), []):
                if int(change_request.get("id") or 0) != int(change_request_id):
                    continue
                item["current_published_version_id"] = int(change_request.get("candidate_version_id") or 0) or None
                item["status"] = "published"
                change_request["status"] = "published"
                return {"change_request": dict(change_request), "publish_batch": {"id": 501, "change_request_id": change_request_id}}
        raise KeyError("change_request_not_found")

    def _mutate_change_request(self, *, change_request_id: int, new_status: str, item_status: str):
        for item in self.items:
            for change_request in self.change_requests.get(int(item["id"]), []):
                if int(change_request.get("id") or 0) != int(change_request_id):
                    continue
                change_request["status"] = new_status
                item["status"] = item_status
                return {"change_request": dict(change_request)}
        raise KeyError("change_request_not_found")

    def list_audit_trail(self, *, server_scope: str, server_id: str | None, entity_type: str = "", entity_id: str = "", limit: int = 100):
        self.calls.append(
            {
                "kind": "list_audit_trail",
                "server_scope": server_scope,
                "server_id": server_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "limit": limit,
            }
        )
        return [
            {
                "id": 1,
                "entity_type": entity_type or "law",
                "entity_id": entity_id or "42",
                "action": "update",
            }
        ]

    def validate_change_request(self, *, change_request_id: int, server_scope: str, server_id: str | None):
        self.calls.append(
            {
                "kind": "validate_change_request",
                "change_request_id": change_request_id,
                "server_scope": server_scope,
                "server_id": server_id,
            }
        )
        return {
            "ok": True,
            "errors": [],
            "content_type": "templates",
            "change_request": {"id": change_request_id, "status": "draft"},
            "version": {"id": 7},
        }


class _FakeContentWorkflowServiceError:
    def __init__(self, error: Exception):
        self.error = error

    def list_audit_trail(self, **kwargs):
        raise self.error


class _FakeRuntimeLawSetsStore:
    def __init__(self):
        self.law_sets = {
            1: {
                "id": 1,
                "server_code": "blackberry",
                "name": "Default",
                "is_active": True,
                "is_published": True,
                "item_count": 1,
            }
        }
        self.bindings = {
            "blackberry": [
                {
                    "law_set_id": 1,
                    "item_id": 1,
                    "law_code": "uk",
                    "priority": 100,
                    "effective_from": "",
                }
            ]
        }
        self.law_set_details = {
            1: {
                "law_set": dict(self.law_sets[1]),
                "items": [
                    {
                        "id": 1,
                        "law_set_id": 1,
                        "law_code": "uk",
                        "effective_from": "",
                        "priority": 100,
                        "source_id": 1,
                        "source_name": "UK source",
                        "source_url": "https://example.com/laws/uk",
                    }
                ],
            }
        }

    def list_law_sets(self, *, server_code: str):
        return [row for row in self.law_sets.values() if row["server_code"] == server_code]

    def create_law_set(self, *, server_code: str, name: str):
        next_id = max(self.law_sets.keys(), default=0) + 1
        row = {"id": next_id, "server_code": server_code, "name": name, "is_active": True, "is_published": False}
        self.law_sets[next_id] = {**row, "item_count": 0}
        return row

    def replace_law_set_items(self, *, law_set_id: int, items):
        self.law_sets[law_set_id]["item_count"] = len(items)
        self.law_set_details[law_set_id] = {
            "law_set": dict(self.law_sets[law_set_id]),
            "items": list(items),
        }
        return list(items)

    def get_law_set_detail(self, *, law_set_id: int):
        detail = self.law_set_details.get(int(law_set_id))
        if detail is None:
            raise KeyError("law_set_not_found")
        return {
            "law_set": dict(detail["law_set"]),
            "items": [dict(item) for item in detail["items"]],
        }

    def list_server_law_bindings(self, *, server_code: str):
        return list(self.bindings.get(server_code, []))

    def add_server_law_binding(self, *, server_code: str, law_code: str, source_id: int, effective_from: str = "", priority: int = 100, law_set_id=None):
        item = {
            "law_set_id": int(law_set_id or 1),
            "item_id": len(self.bindings.get(server_code, [])) + 1,
            "law_code": law_code,
            "priority": priority,
            "effective_from": effective_from,
            "source_id": source_id,
        }
        self.bindings.setdefault(server_code, []).append(item)
        return item

    def publish_law_set(self, *, law_set_id: int):
        row = self.law_sets[law_set_id]
        for item in self.law_sets.values():
            if item["server_code"] == row["server_code"]:
                item["is_published"] = False
        row["is_published"] = True
        row["is_active"] = True
        return {k: row[k] for k in ("id", "server_code", "name", "is_active", "is_published")}


class _NoActiveLawSetStore(_FakeRuntimeLawSetsStore):
    def __init__(self):
        super().__init__()
        self.law_sets = {}
        self.law_set_details = {}
        self.bindings = {
            "blackberry": [
                {
                    "law_set_id": 999,
                    "item_id": 1,
                    "law_code": "uk",
                    "priority": 100,
                    "effective_from": "",
                }
            ]
        }


class _FakeProjectionRun:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeProjectionsStore:
    def __init__(self):
        self._runs = {
            "orange": [
                _FakeProjectionRun(
                    id=4,
                    server_code="orange",
                    trigger_mode="manual",
                    status="approved",
                    summary_json={
                        "decision_status": "approved",
                        "materialization": {"law_set_id": 2},
                        "activation": {"law_version_id": 88},
                    },
                    created_at="2026-04-16T06:00:00+00:00",
                )
            ],
            "blackberry": [
                _FakeProjectionRun(
                    id=8,
                    server_code="blackberry",
                    trigger_mode="manual",
                    status="preview",
                    summary_json={
                        "selected_count": 1,
                        "candidate_count": 1,
                        "input_fingerprint": "bb-fp-1",
                    },
                    created_at="2026-04-16T07:00:00+00:00",
                ),
                _FakeProjectionRun(
                    id=7,
                    server_code="blackberry",
                    trigger_mode="manual",
                    status="preview",
                    summary_json={
                        "selected_count": 1,
                        "candidate_count": 1,
                        "input_fingerprint": "bb-fp-0",
                    },
                    created_at="2026-04-16T05:00:00+00:00",
                ),
            ],
        }
        self._items = {
            8: [
                type(
                    "_ProjectionItem",
                    (),
                    {
                        "id": 81,
                        "projection_run_id": 8,
                        "canonical_law_document_id": 21,
                        "canonical_identity_key": "uk",
                        "normalized_url": "https://example.com/laws/uk",
                        "selected_document_version_id": 101,
                        "selected_source_set_key": "legacy-blackberry-default",
                        "selected_revision": 2,
                        "precedence_rank": 1,
                        "contributor_count": 1,
                        "status": "candidate",
                        "provenance_json": {},
                        "created_at": "2026-04-16T07:00:00+00:00",
                    },
                )()
            ],
            7: [
                type(
                    "_ProjectionItem",
                    (),
                    {
                        "id": 71,
                        "projection_run_id": 7,
                        "canonical_law_document_id": 21,
                        "canonical_identity_key": "uk",
                        "normalized_url": "https://example.com/laws/uk",
                        "selected_document_version_id": 100,
                        "selected_source_set_key": "legacy-blackberry-default",
                        "selected_revision": 1,
                        "precedence_rank": 1,
                        "contributor_count": 1,
                        "status": "candidate",
                        "provenance_json": {},
                        "created_at": "2026-04-16T05:00:00+00:00",
                    },
                )()
            ],
        }
        self._next_run_id = 9
        self._next_item_id = 90

    def list_runs(self, *, server_code: str):
        return list(self._runs.get(server_code, []))

    def get_run(self, *, run_id: int):
        for items in self._runs.values():
            for row in items:
                if int(row.id) == int(run_id):
                    return row
        return None

    def list_items(self, *, projection_run_id: int):
        return list(self._items.get(int(projection_run_id), []))

    def create_projection_run(self, *, server_code: str, trigger_mode: str = "manual", status: str = "preview", summary_json=None):
        row = _FakeProjectionRun(
            id=self._next_run_id,
            server_code=server_code,
            trigger_mode=trigger_mode,
            status=status,
            summary_json=dict(summary_json or {}),
            created_at=f"2026-04-16T08:0{self._next_run_id - 9}:00+00:00",
        )
        self._next_run_id += 1
        self._runs.setdefault(server_code, []).insert(0, row)
        self._items.setdefault(int(row.id), [])
        return row

    def create_projection_item(
        self,
        *,
        projection_run_id: int,
        canonical_law_document_id: int,
        canonical_identity_key: str,
        normalized_url: str,
        selected_document_version_id: int,
        selected_source_set_key: str,
        selected_revision: int,
        precedence_rank: int,
        contributor_count: int,
        status: str = "candidate",
        provenance_json=None,
    ):
        item = type(
            "_ProjectionItem",
            (),
            {
                "id": self._next_item_id,
                "projection_run_id": int(projection_run_id),
                "canonical_law_document_id": int(canonical_law_document_id),
                "canonical_identity_key": canonical_identity_key,
                "normalized_url": normalized_url,
                "selected_document_version_id": int(selected_document_version_id),
                "selected_source_set_key": selected_source_set_key,
                "selected_revision": int(selected_revision),
                "precedence_rank": int(precedence_rank),
                "contributor_count": int(contributor_count),
                "status": status,
                "provenance_json": dict(provenance_json or {}),
                "created_at": "2026-04-16T08:10:00+00:00",
            },
        )()
        self._next_item_id += 1
        self._items.setdefault(int(projection_run_id), []).append(item)
        self._items[int(projection_run_id)].sort(key=lambda row: (int(row.precedence_rank), str(row.canonical_identity_key)))
        return item

    def update_run_status(self, *, run_id: int, status: str, summary_json=None):
        run = self.get_run(run_id=run_id)
        if run is None:
            raise KeyError("server_effective_law_projection_run_not_found")
        run.status = status
        run.summary_json = dict(summary_json or {})
        return run


class _FakeCanonicalLawDocumentVersionsStore:
    class _Version:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    def __init__(self):
        self.rows = {
            100: self._Version(
                id=100,
                canonical_law_document_id=21,
                canonical_identity_key="uk",
                display_title="УК",
                source_discovery_run_id=10,
                discovered_law_link_id=1000,
                source_set_key="legacy-blackberry-default",
                source_set_revision_id=1,
                revision=1,
                normalized_url="https://example.com/laws/uk",
                source_container_url="https://example.com/laws",
                fetch_status="fetched",
                parse_status="parsed",
                content_checksum="v1",
                raw_title="УК v1",
                parsed_title="Уголовный кодекс v1",
                body_text="Старый текст закона для blackberry.",
                metadata_json={},
                created_at="2026-04-16T05:00:00+00:00",
                updated_at="2026-04-16T05:00:00+00:00",
            ),
            101: self._Version(
                id=101,
                canonical_law_document_id=21,
                canonical_identity_key="uk",
                display_title="УК",
                source_discovery_run_id=11,
                discovered_law_link_id=1001,
                source_set_key="legacy-blackberry-default",
                source_set_revision_id=2,
                revision=2,
                normalized_url="https://example.com/laws/uk",
                source_container_url="https://example.com/laws",
                fetch_status="fetched",
                parse_status="parsed",
                content_checksum="v2",
                raw_title="УК v2",
                parsed_title="Уголовный кодекс v2",
                body_text="Актуальный текст закона для blackberry с содержимым.",
                metadata_json={},
                created_at="2026-04-16T07:00:00+00:00",
                updated_at="2026-04-16T07:00:00+00:00",
            ),
        }

    def get_version(self, *, version_id: int):
        return self.rows.get(int(version_id))

    def list_parsed_versions_for_source_sets(self, *, source_set_keys):
        normalized = {str(item or "").strip().lower() for item in source_set_keys}
        return [row for row in self.rows.values() if str(row.source_set_key or "").strip().lower() in normalized]


class _FakeLawSourceSetsStore:
    def list_bindings(self, *, server_code: str):
        if server_code == "orange":
            return [
                type(
                    "_Binding",
                    (),
                    {
                        "id": 12,
                        "server_code": server_code,
                        "source_set_key": "legacy-orange-default",
                        "priority": 100,
                        "is_active": True,
                        "include_law_keys": [],
                        "exclude_law_keys": [],
                        "pin_policy_json": {},
                        "metadata_json": {},
                        "created_at": "2026-04-16T04:00:00+00:00",
                        "updated_at": "2026-04-16T04:00:00+00:00",
                    },
                )()
            ]
        if server_code != "blackberry":
            return []
        return [
            type(
                "_Binding",
                (),
                {
                    "id": 11,
                    "server_code": server_code,
                    "source_set_key": "legacy-blackberry-default",
                    "priority": 100,
                    "is_active": True,
                    "include_law_keys": [],
                    "exclude_law_keys": [],
                    "pin_policy_json": {},
                    "metadata_json": {},
                    "created_at": "2026-04-16T04:00:00+00:00",
                    "updated_at": "2026-04-16T04:00:00+00:00",
                },
            )()
        ]


class _City2SourceSetsStore(_FakeLawSourceSetsStore):
    def list_bindings(self, *, server_code: str):
        if server_code == "city2":
            return [
                type(
                    "_Binding",
                    (),
                    {
                        "id": 21,
                        "server_code": server_code,
                        "source_set_key": "city2-default",
                        "priority": 100,
                        "is_active": True,
                        "include_law_keys": [],
                        "exclude_law_keys": [],
                        "pin_policy_json": {},
                        "metadata_json": {},
                        "created_at": "2026-04-16T04:00:00+00:00",
                        "updated_at": "2026-04-16T04:00:00+00:00",
                    },
                )()
            ]
        return super().list_bindings(server_code=server_code)


class _FakeAdminDashboardService:
    def get_dashboard(self, *, username: str, server_id: str):
        _ = username
        return {
            "release": {"warning_signals": []},
            "generation_law_qa": {},
            "jobs": {"dlq_count": 0},
            "validation": {},
            "content": {"recent_audit_activity": [{"entity_type": "content_item", "entity_id": "42", "action": "publish", "created_at": "2026-04-16T10:00:00+00:00"}], "publish_batches": []},
            "integrity": {"status": "ok"},
            "synthetic": {"failed_scenarios": []},
        }


class AdminRuntimeServersApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = make_temporary_directory()
        root = Path(self.tmpdir.name)
        self.user_store = UserStore(
            root / "app.db",
            root / "users.json",
            repository=UserRepository(PostgresBackend()),
        )
        self.exam_store = ExamAnswersStore(root / "exam_answers.db", backend=FakeExamAnswersPostgresBackend())
        self.admin_store = AdminMetricsStore(root / "admin_metrics.db", backend=FakeAdminMetricsPostgresBackend())
        self.task_registry = ExamImportTaskRegistry(
            root / "exam_import_tasks.db",
            backend=FakeExamImportTasksPostgresBackend(),
        )
        app = create_app(self.user_store, self.exam_store, self.admin_store, self.task_registry)
        self.runtime_store = _FakeRuntimeServersStore()
        self.runtime_law_sets_store = _FakeRuntimeLawSetsStore()
        self.projections_store = _FakeProjectionsStore()
        self.source_sets_store = _FakeLawSourceSetsStore()
        self.versions_store = _FakeCanonicalLawDocumentVersionsStore()
        self.workflow_service = _FakeContentWorkflowService()
        app.dependency_overrides[get_runtime_servers_store] = lambda: self.runtime_store
        app.dependency_overrides[get_runtime_law_sets_store] = lambda: self.runtime_law_sets_store
        app.dependency_overrides[get_server_effective_law_projections_store] = lambda: self.projections_store
        app.dependency_overrides[get_law_source_sets_store] = lambda: self.source_sets_store
        app.dependency_overrides[get_canonical_law_document_versions_store] = lambda: self.versions_store
        app.dependency_overrides[get_admin_dashboard_service] = lambda: _FakeAdminDashboardService()
        app.dependency_overrides[get_content_workflow_service] = lambda: self.workflow_service
        self.client = TestClient(app, base_url="https://testserver")
        reset_rate_limit(self.client.app.state.rate_limiter)
        self._register_and_login_admin("12345", "admin@example.com")

    def tearDown(self):
        reset_rate_limit(self.client.app.state.rate_limiter)
        self.client.close()
        self.client.app.state.rate_limiter.repository.close()
        self.user_store.repository.close()
        self.tmpdir.cleanup()

    def _register_and_login_admin(self, username: str, email: str):
        response = self.client.post(
            "/api/auth/register",
            json={"username": username, "email": email, "password": "Password123!"},
        )
        self.assertEqual(response.status_code, 200)
        verify_url = response.json()["verification_url"]
        split = urlsplit(verify_url)
        self.client.get(f"{split.path}?{split.query}")
        login = self.client.post("/api/auth/login", json={"username": username, "password": "Password123!"})
        self.assertEqual(login.status_code, 200)

    def test_runtime_servers_crud_endpoints(self):
        self.runtime_store.rows["orange"] = {
            "code": "orange",
            "title": "Orange City",
            "is_active": True,
            "created_at": "2026-04-16T00:00:00+00:00",
        }
        listed = self.client.get("/api/admin/runtime-servers")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["count"], 2)
        blackberry = next(item for item in listed.json()["items"] if item["code"] == "blackberry")
        orange = next(item for item in listed.json()["items"] if item["code"] == "orange")
        self.assertEqual(blackberry["onboarding"]["highest_completed_state"], "workflow-ready")
        self.assertEqual(blackberry["onboarding"]["binding_source"], "source_set_bindings")
        self.assertEqual(orange["projection_bridge"]["run_id"], 4)
        self.assertEqual(orange["projection_bridge"]["law_set_id"], 2)
        self.assertEqual(orange["projection_bridge"]["law_version_id"], 88)
        self.assertIsNone(orange["projection_bridge"]["matches_active_law_version"])

        created = self.client.post("/api/admin/runtime-servers", json={"code": "city2", "title": "City 2"})
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["item"]["code"], "city2")
        self.assertFalse(created.json()["item"]["is_active"])
        self.assertEqual(created.json()["item"]["onboarding"]["highest_completed_state"], "not-ready")
        self.assertEqual(created.json()["item"]["onboarding"]["resolution_mode"], "neutral_fallback")
        self.assertFalse(created.json()["item"]["onboarding"]["resolution"]["is_runtime_addressable"])
        self.assertIsNone(created.json()["item"]["projection_bridge"])

        updated = self.client.put("/api/admin/runtime-servers/city2", json={"code": "city2", "title": "City 2 RU"})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["item"]["title"], "City 2 RU")

        deactivated = self.client.post("/api/admin/runtime-servers/city2/deactivate")
        self.assertEqual(deactivated.status_code, 200)
        self.assertFalse(deactivated.json()["item"]["is_active"])

        activated = self.client.post("/api/admin/runtime-servers/city2/activate")
        self.assertEqual(activated.status_code, 200)
        self.assertTrue(activated.json()["item"]["is_active"])

    def test_runtime_servers_onboarding_does_not_require_active_law_set_for_workflow_ready(self):
        self.client.app.dependency_overrides[get_runtime_law_sets_store] = lambda: _NoActiveLawSetStore()

        response = self.client.get("/api/admin/runtime-servers")

        self.assertEqual(response.status_code, 200)
        blackberry = next(item for item in response.json()["items"] if item["code"] == "blackberry")
        self.assertEqual(blackberry["onboarding"]["highest_completed_state"], "workflow-ready")
        self.assertNotIn("law set", blackberry["onboarding"]["states"]["workflow-ready"]["detail"])
        self.assertEqual(blackberry["onboarding"]["binding_source"], "source_set_bindings")

    def test_runtime_server_health_treats_law_set_as_observational_shell_check(self):
        self.client.app.dependency_overrides[get_runtime_law_sets_store] = lambda: _NoActiveLawSetStore()

        with patch.object(
            admin_runtime_servers_service,
            "resolve_active_law_version",
            return_value=ResolvedLawVersion(
                id=77,
                server_code="blackberry",
                generated_at_utc="2026-04-14T00:00:00+00:00",
                effective_from="2026-04-14",
                effective_to="",
                fingerprint="test-fingerprint",
                chunk_count=12,
            ),
        ):
            response = self.client.get("/api/admin/runtime-servers/blackberry/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["checks"]["law_set"]["ok"])
        self.assertTrue(payload["summary"]["is_ready"])
        self.assertEqual(payload["summary"]["ready_count"], payload["summary"]["total_count"])
        self.assertEqual(payload["summary"]["observational_checks"], ["law_set"])
        self.assertTrue(payload["checks"]["law_set"]["observational_only"])
        self.assertEqual(payload["checks"]["law_set"]["detail"], "law_set_missing")
        self.assertEqual(payload["checks"]["bindings"]["binding_source"], "source_set_bindings")
        self.assertTrue(payload["checks"]["bindings"]["canonical_ready"])
        self.assertEqual(payload["runtime_provenance"]["mode"], "legacy_runtime_shell")
        self.assertTrue(payload["runtime_provenance"]["law_set_observational_only"])
        self.assertEqual(payload["runtime_provenance"]["shell_stage"], "active_without_projection")
        self.assertEqual(payload["runtime_alignment"]["status"], "legacy_only")
        self.assertTrue(payload["runtime_alignment"]["law_set_observational_only"])
        self.assertEqual(payload["runtime_alignment"]["shell_stage"], "active_without_projection")
        self.assertIsNone(payload["runtime_alignment"]["active_law_set_id"])
        self.assertEqual(payload["runtime_alignment"]["active_law_version_id"], 77)

    def test_runtime_server_update_rejects_code_mismatch(self):
        response = self.client.put("/api/admin/runtime-servers/city2", json={"code": "city3", "title": "Wrong"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("server_code_mismatch", response.json().get("detail", []))

    def test_runtime_server_health_and_setup_flow(self):
        self.client.app.dependency_overrides[get_law_source_sets_store] = lambda: _City2SourceSetsStore()
        created = self.client.post("/api/admin/runtime-servers", json={"code": "city2", "title": "City 2"})
        self.assertEqual(created.status_code, 200)

        created_law_set = self.client.post(
            "/api/admin/runtime-servers/city2/law-sets",
            json={"name": "City 2 Draft", "is_active": True, "items": [{"law_code": "city2_law", "priority": 10}]},
        )
        self.assertEqual(created_law_set.status_code, 200)
        law_set_id = created_law_set.json()["law_set"]["id"]

        published = self.client.post(f"/api/admin/law-sets/{law_set_id}/publish")
        self.assertEqual(published.status_code, 200)

        binding = self.client.post(
            "/api/admin/runtime-servers/city2/law-bindings",
            json={"law_code": "city2_law", "source_id": 1, "priority": 25, "law_set_id": law_set_id},
        )
        self.assertEqual(binding.status_code, 200)

        deactivated = self.client.post("/api/admin/runtime-servers/city2/deactivate")
        self.assertEqual(deactivated.status_code, 200)

        with patch.object(
            admin_runtime_servers_service,
            "resolve_active_law_version",
            return_value=ResolvedLawVersion(
                id=77,
                server_code="city2",
                generated_at_utc="2026-04-14T00:00:00+00:00",
                effective_from="2026-04-14",
                effective_to="",
                fingerprint="test-fingerprint",
                chunk_count=12,
            ),
        ):
            health_before = self.client.get("/api/admin/runtime-servers/city2/health")
            self.assertEqual(health_before.status_code, 200)
            payload_before = health_before.json()
            self.assertEqual(payload_before["summary"]["ready_count"], 3)
            self.assertFalse(payload_before["checks"]["activation"]["ok"])
            self.assertTrue(payload_before["checks"]["health"]["ok"])
            self.assertFalse(payload_before["checks"]["config_resolution"]["ok"])
            self.assertEqual(payload_before["checks"]["bindings"]["binding_source"], "source_set_bindings")
            self.assertEqual(payload_before["onboarding"]["highest_completed_state"], "not-ready")
            self.assertEqual(payload_before["onboarding"]["resolution_mode"], "neutral_fallback")
            self.assertTrue(payload_before["onboarding"]["requires_explicit_runtime_pack"])
            self.assertFalse(payload_before["onboarding"]["resolution"]["is_runtime_addressable"])

            activated = self.client.post("/api/admin/runtime-servers/city2/activate")
            self.assertEqual(activated.status_code, 200)

            health_after = self.client.get("/api/admin/runtime-servers/city2/health")
            self.assertEqual(health_after.status_code, 200)
            payload_after = health_after.json()
            self.assertFalse(payload_after["summary"]["is_ready"])
            self.assertEqual(payload_after["summary"]["ready_count"], payload_after["summary"]["total_count"] - 1)
            self.assertEqual(payload_after["checks"]["health"]["active_law_version_id"], 77)
            self.assertFalse(payload_after["checks"]["config_resolution"]["ok"])
            self.assertEqual(payload_after["onboarding"]["highest_completed_state"], "not-ready")
            self.assertEqual(payload_after["onboarding"]["next_required_state"], "bootstrap-ready")

    def test_runtime_server_workspace_endpoint_returns_server_centric_summary(self):
        with patch.object(
            admin_runtime_servers_service,
            "resolve_active_law_version",
            return_value=ResolvedLawVersion(
                id=91,
                server_code="blackberry",
                generated_at_utc="2026-04-16T00:00:00+00:00",
                effective_from="2026-04-16",
                effective_to="",
                fingerprint="bb-workspace-fp",
                chunk_count=6,
            ),
        ):
            response = self.client.get("/api/admin/runtime-servers/blackberry/workspace")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["server"]["code"], "blackberry")
        self.assertIn(payload["readiness"]["overall_status"], {"not_configured", "partial", "ready", "error"})
        self.assertEqual(payload["readiness"]["blocks"]["laws"]["status"], "ready")
        self.assertEqual(payload["health"]["checks"]["bindings"]["binding_source"], "source_set_bindings")
        self.assertTrue(payload["health"]["checks"]["bindings"]["canonical_ready"])
        self.assertEqual(payload["health"]["checks"]["bindings"]["source_set_binding_count"], 1)
        self.assertEqual(payload["health"]["checks"]["bindings"]["runtime_binding_count"], 1)
        self.assertFalse(payload["health"]["checks"]["bindings"]["uses_runtime_bindings_fallback"])
        self.assertIn("laws", payload["overview"])
        self.assertIn("features", payload["overview"])
        self.assertIn("templates", payload["overview"])
        self.assertIn("users", payload["overview"])
        self.assertIn("access", payload["overview"])
        self.assertEqual(payload["overview"]["laws"]["binding_count"], 1)
        self.assertEqual(payload["overview"]["laws"]["runtime_config_posture"]["status"], "bootstrap_transition")
        self.assertEqual(payload["overview"]["laws"]["runtime_config_debt"]["status"], "medium")
        self.assertEqual(payload["overview"]["laws"]["runtime_resolution_policy"]["status"], "transitional_bootstrap")
        self.assertEqual(payload["overview"]["laws"]["runtime_provenance"]["mode"], "legacy_runtime_shell")
        self.assertEqual(payload["overview"]["laws"]["runtime_alignment"]["status"], "legacy_only")
        self.assertEqual(payload["overview"]["laws"]["runtime_item_parity"]["status"], "aligned")
        self.assertEqual(payload["overview"]["laws"]["runtime_version_parity"]["status"], "legacy_only")
        self.assertEqual(payload["overview"]["laws"]["projection_bridge_lifecycle"]["status"], "preview_only")
        self.assertEqual(payload["overview"]["laws"]["projection_bridge_readiness"]["status"], "action_required")
        self.assertIn("activation_pending", payload["overview"]["laws"]["projection_bridge_readiness"]["blockers"])
        self.assertEqual(payload["overview"]["laws"]["promotion_candidate"]["status"], "blocked")
        self.assertEqual(payload["overview"]["laws"]["promotion_delta"]["status"], "attention")
        self.assertEqual(payload["overview"]["laws"]["promotion_blockers"]["status"], "blocked")
        self.assertEqual(payload["overview"]["laws"]["promotion_review_signal"]["status"], "deferred")
        self.assertEqual(payload["overview"]["laws"]["activation_gap"]["status"], "open")
        self.assertEqual(payload["overview"]["laws"]["runtime_shell_debt"]["status"], "high")
        self.assertEqual(payload["overview"]["laws"]["runtime_convergence"]["status"], "blocked")
        self.assertEqual(payload["overview"]["laws"]["cutover_readiness"]["status"], "needs_activation_alignment")
        self.assertEqual(payload["overview"]["laws"]["runtime_cutover_mode"]["status"], "compatibility_mode")
        self.assertEqual(payload["overview"]["laws"]["runtime_bridge_policy"]["status"], "keep_compatibility")
        self.assertEqual(payload["overview"]["laws"]["runtime_operating_mode"]["status"], "compatibility_runtime")
        self.assertEqual(payload["overview"]["laws"]["runtime_policy_violations"]["status"], "clear")
        self.assertEqual(payload["overview"]["laws"]["cutover_guardrails"]["status"], "compatibility_guardrails")
        self.assertEqual(payload["overview"]["laws"]["runtime_policy_enforcement"]["status"], "compatibility_hold")
        self.assertEqual(payload["overview"]["laws"]["policy_breach_summary"]["status"], "clear")
        self.assertEqual(payload["overview"]["laws"]["runtime_risk_register"]["status"], "high")
        self.assertEqual(payload["overview"]["laws"]["runtime_governance_contract"]["status"], "compatibility_contract")
        self.assertEqual(payload["overview"]["laws"]["legacy_path_allowance"]["status"], "compatibility_allowed")
        self.assertEqual(payload["overview"]["laws"]["compatibility_exit_scorecard"]["status"], "not_ready")
        self.assertEqual(payload["overview"]["laws"]["runtime_breach_categories"]["status"], "attention")
        self.assertEqual(payload["overview"]["laws"]["legacy_path_controls"]["status"], "compatibility_controls")
        self.assertEqual(payload["overview"]["laws"]["projection_runtime_gate"]["status"], "guarded")
        self.assertEqual(payload["overview"]["laws"]["compatibility_shrink_decision"]["status"], "hold_compatibility")
        self.assertEqual(payload["overview"]["laws"]["runtime_exception_register"]["status"], "open")
        self.assertEqual(payload["overview"]["laws"]["compatibility_path_matrix"]["status"], "compatibility_matrix")
        self.assertEqual(payload["overview"]["laws"]["next_shrink_step"]["status"], "hold")
        self.assertEqual(payload["overview"]["laws"]["shrink_sequence"]["status"], "queued")
        self.assertEqual(payload["overview"]["laws"]["bridge_shrink_checklist"]["status"], "blocked")
        self.assertEqual(payload["overview"]["laws"]["cutover_blockers_breakdown"]["status"], "blocked")
        self.assertEqual(payload["health"]["onboarding"]["resolution_mode"], "bootstrap_pack")
        issue_ids = {item.get("issue_id") for item in payload["issues"]["items"] if item.get("issue_id")}
        self.assertIn("laws_runtime_provenance", issue_ids)
        self.assertIn("laws_runtime_version_parity", issue_ids)
        self.assertIn("laws_projection_bridge_lifecycle", issue_ids)
        self.assertIn("laws_projection_bridge_readiness", issue_ids)
        self.assertIn("laws_promotion_candidate", issue_ids)
        self.assertIn("laws_promotion_blockers", issue_ids)
        self.assertNotIn("laws_promotion_review_signal", issue_ids)
        self.assertIn("laws_activation_gap", issue_ids)
        self.assertIn("laws_runtime_shell_debt", issue_ids)
        self.assertIn("laws_runtime_convergence", issue_ids)
        self.assertIn("laws_cutover_readiness", issue_ids)
        self.assertIn("laws_runtime_cutover_mode", issue_ids)
        self.assertIn("runtime_bridge_policy", issue_ids)
        self.assertIn("runtime_operating_mode", issue_ids)
        self.assertIn("laws_cutover_guardrails", issue_ids)
        self.assertIn("runtime_policy_enforcement", issue_ids)
        self.assertIn("runtime_risk_register", issue_ids)
        self.assertIn("runtime_governance_contract", issue_ids)
        self.assertIn("legacy_path_allowance", issue_ids)
        self.assertIn("compatibility_exit_scorecard", issue_ids)
        self.assertIn("runtime_breach_categories", issue_ids)
        self.assertIn("legacy_path_controls", issue_ids)
        self.assertIn("projection_runtime_gate", issue_ids)
        self.assertIn("compatibility_shrink_decision", issue_ids)
        self.assertIn("runtime_exception_register", issue_ids)
        self.assertIn("compatibility_path_matrix", issue_ids)
        self.assertIn("next_shrink_step", issue_ids)
        self.assertIn("shrink_sequence", issue_ids)
        self.assertIn("laws_bridge_shrink_checklist", issue_ids)
        self.assertIn("laws_cutover_blockers_breakdown", issue_ids)
        self.assertIn("runtime_config_debt", issue_ids)
        self.assertIn("runtime_resolution_policy", issue_ids)
        self.assertEqual(payload["readiness"]["counters"]["stale_changes"], 1)
        self.assertIsInstance(payload["activity"], list)

    def test_runtime_server_activity_endpoint_returns_items(self):
        response = self.client.get("/api/admin/runtime-servers/blackberry/activity")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["server_code"], "blackberry")
        self.assertIn("items", payload)

    def test_runtime_server_audit_endpoint_returns_unified_items(self):
        response = self.client.get("/api/admin/runtime-servers/blackberry/audit")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["server_code"], "blackberry")
        self.assertGreaterEqual(payload["count"], 1)
        self.assertTrue(any(item["kind"] in {"workflow_audit", "law_projection", "content_audit"} for item in payload["items"]))

    def test_runtime_server_issues_endpoint_and_recheck_action_are_operator_safe(self):
        issues = self.client.get("/api/admin/runtime-servers/blackberry/issues")
        self.assertEqual(issues.status_code, 200)
        issues_payload = issues.json()
        self.assertTrue(issues_payload["ok"])
        self.assertGreaterEqual(issues_payload["count"], 1)
        issue_ids = {item["issue_id"] for item in issues_payload["items"]}
        self.assertIn("laws_runtime_health", issue_ids)
        self.assertNotIn("laws_bindings_runtime_fallback", issue_ids)

        recheck = self.client.post("/api/admin/runtime-servers/blackberry/issues/laws_runtime_health/recheck")
        self.assertEqual(recheck.status_code, 200)
        recheck_payload = recheck.json()
        self.assertTrue(recheck_payload["ok"])
        self.assertEqual(recheck_payload["issue_id"], "laws_runtime_health")
        self.assertEqual(recheck_payload["action"], "recheck")

    def test_runtime_server_issues_endpoint_marks_neutral_fallback_as_warning(self):
        created = self.client.post(
            "/api/admin/runtime-servers",
            json={"code": "city2", "title": "City 2"},
        )
        self.assertEqual(created.status_code, 200)

        issues = self.client.get("/api/admin/runtime-servers/city2/issues")
        self.assertEqual(issues.status_code, 200)
        payload = issues.json()
        issue_ids = {item["issue_id"] for item in payload["items"]}
        self.assertIn("runtime_config_fallback", issue_ids)
        self.assertIn("runtime_config_debt", issue_ids)
        self.assertIn("runtime_resolution_policy", issue_ids)

    def test_runtime_server_issues_endpoint_flags_legacy_runtime_bindings_fallback(self):
        created = self.client.post("/api/admin/runtime-servers", json={"code": "city2", "title": "City 2"})
        self.assertEqual(created.status_code, 200)

        created_law_set = self.client.post(
            "/api/admin/runtime-servers/city2/law-sets",
            json={"name": "City 2 Draft", "is_active": True, "items": [{"law_code": "city2_law", "priority": 10}]},
        )
        self.assertEqual(created_law_set.status_code, 200)
        law_set_id = created_law_set.json()["law_set"]["id"]
        published = self.client.post(f"/api/admin/law-sets/{law_set_id}/publish")
        self.assertEqual(published.status_code, 200)
        binding = self.client.post(
            "/api/admin/runtime-servers/city2/law-bindings",
            json={"law_code": "city2_law", "source_id": 1, "priority": 25, "law_set_id": law_set_id},
        )
        self.assertEqual(binding.status_code, 200)

        issues = self.client.get("/api/admin/runtime-servers/city2/issues")
        self.assertEqual(issues.status_code, 200)
        issue_ids = {item["issue_id"] for item in issues.json()["items"]}
        self.assertIn("laws_bindings_runtime_fallback", issue_ids)

    def test_runtime_server_workspace_marks_laws_block_partial_when_only_runtime_bindings_exist(self):
        created = self.client.post("/api/admin/runtime-servers", json={"code": "city2", "title": "City 2"})
        self.assertEqual(created.status_code, 200)

        created_law_set = self.client.post(
            "/api/admin/runtime-servers/city2/law-sets",
            json={"name": "City 2 Draft", "is_active": True, "items": [{"law_code": "city2_law", "priority": 10}]},
        )
        self.assertEqual(created_law_set.status_code, 200)
        law_set_id = created_law_set.json()["law_set"]["id"]
        published = self.client.post(f"/api/admin/law-sets/{law_set_id}/publish")
        self.assertEqual(published.status_code, 200)
        binding = self.client.post(
            "/api/admin/runtime-servers/city2/law-bindings",
            json={"law_code": "city2_law", "source_id": 1, "priority": 25, "law_set_id": law_set_id},
        )
        self.assertEqual(binding.status_code, 200)

        with patch.object(
            admin_runtime_servers_service,
            "resolve_active_law_version",
            return_value=ResolvedLawVersion(
                id=77,
                server_code="city2",
                generated_at_utc="2026-04-14T00:00:00+00:00",
                effective_from="2026-04-14",
                effective_to="",
                fingerprint="city2-runtime-fp",
                chunk_count=12,
            ),
        ):
            response = self.client.get("/api/admin/runtime-servers/city2/workspace")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["overview"]["laws"]["health"]["active_law_version_id"], 77)
        self.assertEqual(payload["health"]["checks"]["bindings"]["binding_source"], "runtime_bindings")
        self.assertFalse(payload["health"]["checks"]["bindings"]["ok"])
        self.assertEqual(payload["health"]["checks"]["bindings"]["count"], 0)
        self.assertEqual(payload["health"]["checks"]["bindings"]["detail"], "source_set_bindings:0")
        self.assertFalse(payload["health"]["checks"]["bindings"]["canonical_ready"])
        self.assertEqual(payload["health"]["checks"]["bindings"]["runtime_binding_count"], 1)
        self.assertEqual(payload["health"]["checks"]["bindings"]["source_set_binding_count"], 0)
        self.assertTrue(payload["health"]["checks"]["bindings"]["uses_runtime_bindings_fallback"])
        self.assertFalse(payload["health"]["summary"]["is_ready"])
        self.assertIn("runtime_bindings", payload["health"]["summary"]["observational_checks"])
        self.assertEqual(payload["readiness"]["blocks"]["laws"]["status"], "partial")

    def test_runtime_server_issues_endpoint_exposes_runtime_provenance_warning_for_legacy_shell(self):
        with patch.object(
            admin_runtime_servers_service,
            "resolve_active_law_version",
            return_value=ResolvedLawVersion(
                id=91,
                server_code="blackberry",
                generated_at_utc="2026-04-16T00:00:00+00:00",
                effective_from="2026-04-16",
                effective_to="",
                fingerprint="bb-runtime-provenance-fp",
                chunk_count=6,
            ),
        ):
            issues = self.client.get("/api/admin/runtime-servers/blackberry/issues")
            self.assertEqual(issues.status_code, 200)
            payload = issues.json()
            issue_ids = {item["issue_id"] for item in payload["items"]}
            self.assertIn("laws_runtime_provenance", issue_ids)
            self.assertIn("laws_runtime_version_parity", issue_ids)
            self.assertIn("laws_projection_bridge_lifecycle", issue_ids)
            self.assertIn("laws_projection_bridge_readiness", issue_ids)
            self.assertIn("laws_promotion_candidate", issue_ids)
            self.assertIn("laws_promotion_blockers", issue_ids)
            self.assertIn("laws_activation_gap", issue_ids)
            self.assertIn("laws_runtime_shell_debt", issue_ids)
            self.assertIn("laws_runtime_convergence", issue_ids)
            self.assertIn("laws_cutover_readiness", issue_ids)
            self.assertIn("laws_runtime_cutover_mode", issue_ids)
            self.assertIn("runtime_bridge_policy", issue_ids)
            self.assertIn("runtime_operating_mode", issue_ids)
            self.assertIn("laws_cutover_guardrails", issue_ids)
            self.assertIn("runtime_policy_enforcement", issue_ids)
            self.assertIn("runtime_risk_register", issue_ids)
            self.assertIn("runtime_governance_contract", issue_ids)
            self.assertIn("legacy_path_allowance", issue_ids)
            self.assertIn("compatibility_exit_scorecard", issue_ids)
            self.assertIn("runtime_breach_categories", issue_ids)
            self.assertIn("legacy_path_controls", issue_ids)
            self.assertIn("projection_runtime_gate", issue_ids)
            self.assertIn("compatibility_shrink_decision", issue_ids)
            self.assertIn("runtime_exception_register", issue_ids)
            self.assertIn("compatibility_path_matrix", issue_ids)
            self.assertIn("next_shrink_step", issue_ids)
            self.assertIn("shrink_sequence", issue_ids)
            self.assertIn("laws_bridge_shrink_checklist", issue_ids)
            self.assertIn("laws_cutover_blockers_breakdown", issue_ids)
            self.assertIn("runtime_config_debt", issue_ids)
            self.assertIn("runtime_resolution_policy", issue_ids)

            recheck = self.client.post("/api/admin/runtime-servers/blackberry/issues/laws_runtime_provenance/recheck")
            self.assertEqual(recheck.status_code, 200)
            recheck_payload = recheck.json()
            self.assertTrue(recheck_payload["ok"])
            self.assertEqual(recheck_payload["issue_id"], "laws_runtime_provenance")
            self.assertEqual(recheck_payload["action"], "recheck")

            parity_recheck = self.client.post("/api/admin/runtime-servers/blackberry/issues/laws_runtime_version_parity/recheck")
            self.assertEqual(parity_recheck.status_code, 200)
            parity_recheck_payload = parity_recheck.json()
            self.assertTrue(parity_recheck_payload["ok"])
            self.assertEqual(parity_recheck_payload["issue_id"], "laws_runtime_version_parity")
            self.assertEqual(parity_recheck_payload["action"], "recheck")

            lifecycle_recheck = self.client.post("/api/admin/runtime-servers/blackberry/issues/laws_projection_bridge_lifecycle/recheck")
            self.assertEqual(lifecycle_recheck.status_code, 200)
            lifecycle_recheck_payload = lifecycle_recheck.json()
            self.assertTrue(lifecycle_recheck_payload["ok"])
            self.assertEqual(lifecycle_recheck_payload["issue_id"], "laws_projection_bridge_lifecycle")
            self.assertEqual(lifecycle_recheck_payload["action"], "recheck")

            readiness_recheck = self.client.post("/api/admin/runtime-servers/blackberry/issues/laws_projection_bridge_readiness/recheck")
            self.assertEqual(readiness_recheck.status_code, 200)
            readiness_recheck_payload = readiness_recheck.json()
            self.assertTrue(readiness_recheck_payload["ok"])
            self.assertEqual(readiness_recheck_payload["issue_id"], "laws_projection_bridge_readiness")
            self.assertEqual(readiness_recheck_payload["action"], "recheck")

            candidate_recheck = self.client.post("/api/admin/runtime-servers/blackberry/issues/laws_promotion_candidate/recheck")
            self.assertEqual(candidate_recheck.status_code, 200)
            candidate_recheck_payload = candidate_recheck.json()
            self.assertTrue(candidate_recheck_payload["ok"])
            self.assertEqual(candidate_recheck_payload["issue_id"], "laws_promotion_candidate")
            self.assertEqual(candidate_recheck_payload["action"], "recheck")
            delta_recheck = self.client.post("/api/admin/runtime-servers/blackberry/issues/laws_promotion_delta/recheck")
            self.assertEqual(delta_recheck.status_code, 200)
            delta_recheck_payload = delta_recheck.json()
            self.assertTrue(delta_recheck_payload["ok"])
            self.assertEqual(delta_recheck_payload["issue_id"], "laws_promotion_delta")
            self.assertEqual(delta_recheck_payload["action"], "recheck")
            blockers_recheck = self.client.post("/api/admin/runtime-servers/blackberry/issues/laws_promotion_blockers/recheck")
            self.assertEqual(blockers_recheck.status_code, 200)
            blockers_recheck_payload = blockers_recheck.json()
            self.assertTrue(blockers_recheck_payload["ok"])
            self.assertEqual(blockers_recheck_payload["issue_id"], "laws_promotion_blockers")
            self.assertEqual(blockers_recheck_payload["action"], "recheck")
            activation_gap_recheck = self.client.post("/api/admin/runtime-servers/blackberry/issues/laws_activation_gap/recheck")
            self.assertEqual(activation_gap_recheck.status_code, 200)
            activation_gap_recheck_payload = activation_gap_recheck.json()
            self.assertTrue(activation_gap_recheck_payload["ok"])
            self.assertEqual(activation_gap_recheck_payload["issue_id"], "laws_activation_gap")
            self.assertEqual(activation_gap_recheck_payload["action"], "recheck")
            shell_debt_recheck = self.client.post("/api/admin/runtime-servers/blackberry/issues/laws_runtime_shell_debt/recheck")
            self.assertEqual(shell_debt_recheck.status_code, 200)
            shell_debt_recheck_payload = shell_debt_recheck.json()
            self.assertTrue(shell_debt_recheck_payload["ok"])
            self.assertEqual(shell_debt_recheck_payload["issue_id"], "laws_runtime_shell_debt")
            self.assertEqual(shell_debt_recheck_payload["action"], "recheck")
            convergence_recheck = self.client.post("/api/admin/runtime-servers/blackberry/issues/laws_runtime_convergence/recheck")
            self.assertEqual(convergence_recheck.status_code, 200)
            convergence_recheck_payload = convergence_recheck.json()
            self.assertTrue(convergence_recheck_payload["ok"])
            self.assertEqual(convergence_recheck_payload["issue_id"], "laws_runtime_convergence")
            self.assertEqual(convergence_recheck_payload["action"], "recheck")
            cutover_recheck = self.client.post("/api/admin/runtime-servers/blackberry/issues/laws_cutover_readiness/recheck")
            self.assertEqual(cutover_recheck.status_code, 200)
            cutover_recheck_payload = cutover_recheck.json()
            self.assertTrue(cutover_recheck_payload["ok"])
            self.assertEqual(cutover_recheck_payload["issue_id"], "laws_cutover_readiness")
            self.assertEqual(cutover_recheck_payload["action"], "recheck")
            bridge_policy_recheck = self.client.post("/api/admin/runtime-servers/blackberry/issues/runtime_bridge_policy/recheck")
            self.assertEqual(bridge_policy_recheck.status_code, 200)
            bridge_policy_recheck_payload = bridge_policy_recheck.json()
            self.assertTrue(bridge_policy_recheck_payload["ok"])
            self.assertEqual(bridge_policy_recheck_payload["issue_id"], "runtime_bridge_policy")
            self.assertEqual(bridge_policy_recheck_payload["action"], "recheck")
            operating_mode_recheck = self.client.post("/api/admin/runtime-servers/blackberry/issues/runtime_operating_mode/recheck")
            self.assertEqual(operating_mode_recheck.status_code, 200)
            operating_mode_recheck_payload = operating_mode_recheck.json()
            self.assertTrue(operating_mode_recheck_payload["ok"])
            self.assertEqual(operating_mode_recheck_payload["issue_id"], "runtime_operating_mode")
            self.assertEqual(operating_mode_recheck_payload["action"], "recheck")
            guardrails_recheck = self.client.post("/api/admin/runtime-servers/blackberry/issues/laws_cutover_guardrails/recheck")
            self.assertEqual(guardrails_recheck.status_code, 200)
            guardrails_recheck_payload = guardrails_recheck.json()
            self.assertTrue(guardrails_recheck_payload["ok"])
            self.assertEqual(guardrails_recheck_payload["issue_id"], "laws_cutover_guardrails")
            self.assertEqual(guardrails_recheck_payload["action"], "recheck")
            enforcement_recheck = self.client.post("/api/admin/runtime-servers/blackberry/issues/runtime_policy_enforcement/recheck")
            self.assertEqual(enforcement_recheck.status_code, 200)
            enforcement_recheck_payload = enforcement_recheck.json()
            self.assertTrue(enforcement_recheck_payload["ok"])
            self.assertEqual(enforcement_recheck_payload["issue_id"], "runtime_policy_enforcement")
            self.assertEqual(enforcement_recheck_payload["action"], "recheck")
            risk_register_recheck = self.client.post("/api/admin/runtime-servers/blackberry/issues/runtime_risk_register/recheck")
            self.assertEqual(risk_register_recheck.status_code, 200)
            risk_register_recheck_payload = risk_register_recheck.json()
            self.assertTrue(risk_register_recheck_payload["ok"])
            self.assertEqual(risk_register_recheck_payload["issue_id"], "runtime_risk_register")
            self.assertEqual(risk_register_recheck_payload["action"], "recheck")
            governance_contract_recheck = self.client.post("/api/admin/runtime-servers/blackberry/issues/runtime_governance_contract/recheck")
            self.assertEqual(governance_contract_recheck.status_code, 200)
            self.assertEqual(governance_contract_recheck.json()["issue_id"], "runtime_governance_contract")
            legacy_allowance_recheck = self.client.post("/api/admin/runtime-servers/blackberry/issues/legacy_path_allowance/recheck")
            self.assertEqual(legacy_allowance_recheck.status_code, 200)
            self.assertEqual(legacy_allowance_recheck.json()["issue_id"], "legacy_path_allowance")
            exit_scorecard_recheck = self.client.post("/api/admin/runtime-servers/blackberry/issues/compatibility_exit_scorecard/recheck")
            self.assertEqual(exit_scorecard_recheck.status_code, 200)
            self.assertEqual(exit_scorecard_recheck.json()["issue_id"], "compatibility_exit_scorecard")
            breach_categories_recheck = self.client.post("/api/admin/runtime-servers/blackberry/issues/runtime_breach_categories/recheck")
            self.assertEqual(breach_categories_recheck.status_code, 200)
            self.assertEqual(breach_categories_recheck.json()["issue_id"], "runtime_breach_categories")
            legacy_controls_recheck = self.client.post("/api/admin/runtime-servers/blackberry/issues/legacy_path_controls/recheck")
            self.assertEqual(legacy_controls_recheck.status_code, 200)
            self.assertEqual(legacy_controls_recheck.json()["issue_id"], "legacy_path_controls")
            projection_gate_recheck = self.client.post("/api/admin/runtime-servers/blackberry/issues/projection_runtime_gate/recheck")
            self.assertEqual(projection_gate_recheck.status_code, 200)
            self.assertEqual(projection_gate_recheck.json()["issue_id"], "projection_runtime_gate")
            shrink_decision_recheck = self.client.post("/api/admin/runtime-servers/blackberry/issues/compatibility_shrink_decision/recheck")
            self.assertEqual(shrink_decision_recheck.status_code, 200)
            self.assertEqual(shrink_decision_recheck.json()["issue_id"], "compatibility_shrink_decision")
            exception_register_recheck = self.client.post("/api/admin/runtime-servers/blackberry/issues/runtime_exception_register/recheck")
            self.assertEqual(exception_register_recheck.status_code, 200)
            self.assertEqual(exception_register_recheck.json()["issue_id"], "runtime_exception_register")
            path_matrix_recheck = self.client.post("/api/admin/runtime-servers/blackberry/issues/compatibility_path_matrix/recheck")
            self.assertEqual(path_matrix_recheck.status_code, 200)
            self.assertEqual(path_matrix_recheck.json()["issue_id"], "compatibility_path_matrix")
            next_shrink_recheck = self.client.post("/api/admin/runtime-servers/blackberry/issues/next_shrink_step/recheck")
            self.assertEqual(next_shrink_recheck.status_code, 200)
            self.assertEqual(next_shrink_recheck.json()["issue_id"], "next_shrink_step")
            shrink_sequence_recheck = self.client.post("/api/admin/runtime-servers/blackberry/issues/shrink_sequence/recheck")
            self.assertEqual(shrink_sequence_recheck.status_code, 200)
            self.assertEqual(shrink_sequence_recheck.json()["issue_id"], "shrink_sequence")
            checklist_recheck = self.client.post("/api/admin/runtime-servers/blackberry/issues/laws_bridge_shrink_checklist/recheck")
            self.assertEqual(checklist_recheck.status_code, 200)
            checklist_recheck_payload = checklist_recheck.json()
            self.assertTrue(checklist_recheck_payload["ok"])
            self.assertEqual(checklist_recheck_payload["issue_id"], "laws_bridge_shrink_checklist")
            self.assertEqual(checklist_recheck_payload["action"], "recheck")
            breakdown_recheck = self.client.post("/api/admin/runtime-servers/blackberry/issues/laws_cutover_blockers_breakdown/recheck")
            self.assertEqual(breakdown_recheck.status_code, 200)
            breakdown_recheck_payload = breakdown_recheck.json()
            self.assertTrue(breakdown_recheck_payload["ok"])
            self.assertEqual(breakdown_recheck_payload["issue_id"], "laws_cutover_blockers_breakdown")
            self.assertEqual(breakdown_recheck_payload["action"], "recheck")
    def test_runtime_server_issues_endpoint_exposes_runtime_item_parity_warning_for_drift(self):
        self.runtime_law_sets_store.law_set_details[1]["items"] = [
            {
                "id": 1,
                "law_set_id": 1,
                "law_code": "koap",
                "effective_from": "",
                "priority": 100,
                "source_id": 1,
                "source_name": "KoAP source",
                "source_url": "https://example.com/laws/koap",
            }
        ]
        with patch.object(
            admin_runtime_servers_service,
            "resolve_active_law_version",
            return_value=ResolvedLawVersion(
                id=91,
                server_code="blackberry",
                generated_at_utc="2026-04-16T00:00:00+00:00",
                effective_from="2026-04-16",
                effective_to="",
                fingerprint="bb-runtime-item-parity-fp",
                chunk_count=6,
            ),
        ):
            workspace = self.client.get("/api/admin/runtime-servers/blackberry/workspace")
            self.assertEqual(workspace.status_code, 200)
            workspace_payload = workspace.json()
            workspace_parity = workspace_payload["overview"]["laws"]["runtime_item_parity"]
            self.assertEqual(workspace_parity["status"], "drift")
            self.assertEqual(workspace_parity["runtime_only_sample"], ["koap"])
            self.assertEqual(workspace_parity["projection_only_sample"], ["uk"])
            self.assertIn("runtime_only: koap", workspace_parity["drift_summary"])
            self.assertIn("projection_only: uk", workspace_parity["drift_summary"])

            summary = self.client.get("/api/admin/runtime-servers/blackberry/laws/summary")
            self.assertEqual(summary.status_code, 200)
            summary_parity = summary.json()["runtime_item_parity"]
            self.assertEqual(summary_parity["status"], "drift")
            self.assertEqual(summary_parity["runtime_only_sample"], ["koap"])
            self.assertEqual(summary_parity["projection_only_sample"], ["uk"])

            diff = self.client.get("/api/admin/runtime-servers/blackberry/laws/diff")
            self.assertEqual(diff.status_code, 200)
            diff_parity = diff.json()["runtime_item_parity"]
            self.assertEqual(diff_parity["status"], "drift")
            self.assertEqual(diff_parity["runtime_only_sample"], ["koap"])
            self.assertEqual(diff_parity["projection_only_sample"], ["uk"])

            issues = self.client.get("/api/admin/runtime-servers/blackberry/issues")
            self.assertEqual(issues.status_code, 200)
            payload = issues.json()
            issue_ids = {item["issue_id"] for item in payload["items"]}
            self.assertIn("laws_runtime_item_parity", issue_ids)
            parity_issue = next(item for item in payload["items"] if item["issue_id"] == "laws_runtime_item_parity")
            self.assertIn("runtime_only: koap", parity_issue["detail"])
            self.assertIn("projection_only: uk", parity_issue["detail"])

            recheck = self.client.post("/api/admin/runtime-servers/blackberry/issues/laws_runtime_item_parity/recheck")
            self.assertEqual(recheck.status_code, 200)
            recheck_payload = recheck.json()
            self.assertTrue(recheck_payload["ok"])
            self.assertEqual(recheck_payload["issue_id"], "laws_runtime_item_parity")
            self.assertEqual(recheck_payload["action"], "recheck")

    def test_runtime_server_access_endpoints_support_roles_permissions_assign_and_revoke(self):
        self.user_store.register("moderator1", "moderator1@example.com", "Password123!")
        self.user_store.set_selected_server_code("moderator1", "blackberry")

        roles = self.client.get("/api/admin/roles")
        permissions = self.client.get("/api/admin/permissions")
        self.assertEqual(roles.status_code, 200)
        self.assertEqual(permissions.status_code, 200)
        self.assertTrue(any(item["code"] == "tester" for item in roles.json()["items"]))
        self.assertTrue(any(item["code"] == "manage_servers" for item in permissions.json()["items"]))

        before_summary = self.client.get("/api/admin/runtime-servers/blackberry/access-summary")
        self.assertEqual(before_summary.status_code, 200)
        before_item = next(item for item in before_summary.json()["items"] if item["username"] == "moderator1")
        self.assertEqual(before_item["assignments"], [])

        assigned = self.client.post(
            "/api/admin/users/moderator1/role-assignments",
            json={"role_code": "tester", "server_code": "blackberry"},
        )
        self.assertEqual(assigned.status_code, 200)
        self.assertEqual(assigned.json()["assignment"]["role_code"], "tester")
        self.assertEqual(assigned.json()["assignment"]["scope"], "server")

        assignments = self.client.get("/api/admin/users/moderator1/role-assignments?server_code=blackberry")
        self.assertEqual(assignments.status_code, 200)
        self.assertEqual(assignments.json()["count"], 1)
        self.assertEqual(assignments.json()["items"][0]["assignment_id"], "tester:blackberry")

        after_summary = self.client.get("/api/admin/runtime-servers/blackberry/access-summary")
        self.assertEqual(after_summary.status_code, 200)
        after_item = next(item for item in after_summary.json()["items"] if item["username"] == "moderator1")
        self.assertIn("court_claims", after_item["permissions"])
        self.assertTrue(after_item["is_tester"])

        revoked = self.client.post("/api/admin/users/moderator1/role-assignments/tester:blackberry/revoke")
        self.assertEqual(revoked.status_code, 200)
        self.assertEqual(revoked.json()["assignment"]["assignment_id"], "tester:blackberry")

        final_summary = self.client.get("/api/admin/runtime-servers/blackberry/access-summary")
        self.assertEqual(final_summary.status_code, 200)
        final_item = next(item for item in final_summary.json()["items"] if item["username"] == "moderator1")
        self.assertEqual(final_item["assignments"], [])
        self.assertFalse(final_item["is_tester"])

    def test_runtime_server_laws_workspace_endpoints_return_summary_effective_and_diff(self):
        with patch.object(
            admin_runtime_servers_service,
            "resolve_active_law_version",
            return_value=ResolvedLawVersion(
                id=91,
                server_code="blackberry",
                generated_at_utc="2026-04-16T00:00:00+00:00",
                effective_from="2026-04-16",
                effective_to="",
                fingerprint="bb-laws-fp",
                chunk_count=6,
            ),
        ):
            summary = self.client.get("/api/admin/runtime-servers/blackberry/laws/summary")
            effective = self.client.get("/api/admin/runtime-servers/blackberry/laws/effective")
            diff = self.client.get("/api/admin/runtime-servers/blackberry/laws/diff")

        self.assertEqual(summary.status_code, 200)
        self.assertEqual(effective.status_code, 200)
        self.assertEqual(diff.status_code, 200)
        self.assertEqual(summary.json()["binding_count"], 1)
        self.assertEqual(summary.json()["binding_source"], "source_set_bindings")
        self.assertTrue(summary.json()["canonical_binding_ready"])
        self.assertEqual(summary.json()["runtime_provenance"]["mode"], "legacy_runtime_shell")
        self.assertEqual(summary.json()["runtime_alignment"]["status"], "legacy_only")
        self.assertEqual(summary.json()["runtime_item_parity"]["status"], "aligned")
        self.assertEqual(summary.json()["runtime_version_parity"]["status"], "legacy_only")
        self.assertTrue(summary.json()["runtime_version_parity"]["law_set_observational_only"])
        self.assertEqual(summary.json()["runtime_version_parity"]["shell_stage"], "active_without_projection")
        self.assertNotIn("active_law_set=", summary.json()["runtime_version_parity"]["drift_summary"])
        self.assertEqual(summary.json()["projection_bridge_lifecycle"]["status"], "preview_only")
        self.assertTrue(summary.json()["projection_bridge_lifecycle"]["law_set_observational_only"])
        self.assertEqual(summary.json()["projection_bridge_lifecycle"]["shell_stage"], "active_without_projection")
        self.assertEqual(summary.json()["projection_bridge_readiness"]["status"], "action_required")
        self.assertIn("activation_pending", summary.json()["projection_bridge_readiness"]["blockers"])
        self.assertEqual(summary.json()["promotion_candidate"]["status"], "blocked")
        self.assertEqual(summary.json()["promotion_delta"]["status"], "attention")
        self.assertEqual(summary.json()["promotion_blockers"]["status"], "blocked")
        self.assertEqual(summary.json()["promotion_review_signal"]["status"], "deferred")
        self.assertEqual(summary.json()["activation_gap"]["status"], "open")
        self.assertEqual(summary.json()["runtime_shell_debt"]["status"], "high")
        self.assertEqual(summary.json()["runtime_convergence"]["status"], "blocked")
        self.assertEqual(summary.json()["cutover_readiness"]["status"], "needs_activation_alignment")
        self.assertEqual(summary.json()["runtime_bridge_policy"]["status"], "keep_compatibility")
        self.assertEqual(summary.json()["runtime_operating_mode"]["status"], "compatibility_runtime")
        self.assertEqual(summary.json()["runtime_policy_violations"]["status"], "clear")
        self.assertEqual(summary.json()["cutover_guardrails"]["status"], "compatibility_guardrails")
        self.assertEqual(summary.json()["runtime_policy_enforcement"]["status"], "compatibility_hold")
        self.assertEqual(summary.json()["policy_breach_summary"]["status"], "clear")
        self.assertEqual(summary.json()["runtime_risk_register"]["status"], "high")
        self.assertEqual(summary.json()["runtime_governance_contract"]["status"], "compatibility_contract")
        self.assertEqual(summary.json()["legacy_path_allowance"]["status"], "compatibility_allowed")
        self.assertEqual(summary.json()["compatibility_exit_scorecard"]["status"], "not_ready")
        self.assertEqual(summary.json()["runtime_breach_categories"]["status"], "attention")
        self.assertEqual(summary.json()["legacy_path_controls"]["status"], "compatibility_controls")
        self.assertEqual(summary.json()["projection_runtime_gate"]["status"], "guarded")
        self.assertEqual(summary.json()["compatibility_shrink_decision"]["status"], "hold_compatibility")
        self.assertEqual(summary.json()["runtime_exception_register"]["status"], "open")
        self.assertEqual(summary.json()["compatibility_path_matrix"]["status"], "compatibility_matrix")
        self.assertEqual(summary.json()["next_shrink_step"]["status"], "hold")
        self.assertEqual(summary.json()["shrink_sequence"]["status"], "queued")
        self.assertEqual(summary.json()["bridge_shrink_checklist"]["status"], "blocked")
        self.assertEqual(summary.json()["cutover_blockers_breakdown"]["status"], "blocked")
        self.assertEqual(effective.json()["count"], 1)
        self.assertEqual(effective.json()["items"][0]["title"], "Уголовный кодекс v2")
        self.assertEqual(diff.json()["runtime_alignment"]["status"], "legacy_only")
        self.assertEqual(diff.json()["runtime_item_parity"]["status"], "aligned")
        self.assertEqual(diff.json()["binding_count"], 1)
        self.assertEqual(diff.json()["binding_source"], "source_set_bindings")
        self.assertTrue(diff.json()["canonical_binding_ready"])
        self.assertEqual(diff.json()["runtime_version_parity"]["status"], "legacy_only")
        self.assertTrue(diff.json()["runtime_version_parity"]["law_set_observational_only"])
        self.assertEqual(diff.json()["runtime_version_parity"]["shell_stage"], "active_without_projection")
        self.assertNotIn("active_law_set=", diff.json()["runtime_version_parity"]["drift_summary"])
        self.assertEqual(diff.json()["projection_bridge_lifecycle"]["status"], "preview_only")
        self.assertTrue(diff.json()["projection_bridge_lifecycle"]["law_set_observational_only"])
        self.assertEqual(diff.json()["projection_bridge_lifecycle"]["shell_stage"], "active_without_projection")
        self.assertEqual(diff.json()["projection_bridge_readiness"]["status"], "action_required")
        self.assertEqual(diff.json()["promotion_candidate"]["status"], "blocked")
        self.assertEqual(diff.json()["promotion_delta"]["status"], "attention")
        self.assertEqual(diff.json()["promotion_blockers"]["status"], "blocked")
        self.assertEqual(diff.json()["promotion_review_signal"]["status"], "deferred")
        self.assertEqual(diff.json()["activation_gap"]["status"], "open")
        self.assertEqual(diff.json()["runtime_shell_debt"]["status"], "high")
        self.assertEqual(diff.json()["runtime_convergence"]["status"], "blocked")
        self.assertEqual(diff.json()["cutover_readiness"]["status"], "needs_activation_alignment")
        self.assertEqual(diff.json()["runtime_bridge_policy"]["status"], "keep_compatibility")
        self.assertEqual(diff.json()["runtime_operating_mode"]["status"], "compatibility_runtime")
        self.assertEqual(diff.json()["runtime_policy_violations"]["status"], "clear")
        self.assertEqual(diff.json()["cutover_guardrails"]["status"], "compatibility_guardrails")
        self.assertEqual(diff.json()["runtime_policy_enforcement"]["status"], "compatibility_hold")
        self.assertEqual(diff.json()["policy_breach_summary"]["status"], "clear")
        self.assertEqual(diff.json()["runtime_risk_register"]["status"], "high")
        self.assertEqual(diff.json()["runtime_governance_contract"]["status"], "compatibility_contract")
        self.assertEqual(diff.json()["legacy_path_allowance"]["status"], "compatibility_allowed")
        self.assertEqual(diff.json()["compatibility_exit_scorecard"]["status"], "not_ready")
        self.assertEqual(diff.json()["runtime_breach_categories"]["status"], "attention")
        self.assertEqual(diff.json()["legacy_path_controls"]["status"], "compatibility_controls")
        self.assertEqual(diff.json()["projection_runtime_gate"]["status"], "guarded")
        self.assertEqual(diff.json()["compatibility_shrink_decision"]["status"], "hold_compatibility")
        self.assertEqual(diff.json()["runtime_exception_register"]["status"], "open")
        self.assertEqual(diff.json()["compatibility_path_matrix"]["status"], "compatibility_matrix")
        self.assertEqual(diff.json()["next_shrink_step"]["status"], "hold")
        self.assertEqual(diff.json()["shrink_sequence"]["status"], "queued")
        self.assertEqual(diff.json()["bridge_shrink_checklist"]["status"], "blocked")
        self.assertEqual(diff.json()["cutover_blockers_breakdown"]["status"], "blocked")
        self.assertEqual(diff.json()["summary"]["changed"], 1)
        self.assertEqual(diff.json()["summary"]["added"], 0)

    def test_runtime_server_laws_refresh_preview_and_recheck_are_safe_and_operator_facing(self):
        refresh = self.client.post("/api/admin/runtime-servers/blackberry/laws/refresh-preview")
        self.assertEqual(refresh.status_code, 200)
        refresh_payload = refresh.json()
        self.assertTrue(refresh_payload["ok"])
        self.assertIn("run", refresh_payload)
        self.assertIn("diff", refresh_payload)
        self.assertGreaterEqual(refresh_payload["count"], 1)

        recheck = self.client.post("/api/admin/runtime-servers/blackberry/laws/recheck")
        self.assertEqual(recheck.status_code, 200)
        recheck_payload = recheck.json()
        self.assertTrue(recheck_payload["ok"])
        self.assertEqual(recheck_payload["summary"]["with_content"], 1)
        self.assertEqual(recheck_payload["summary"]["missing_content"], 0)

    def test_runtime_server_features_endpoints_support_effective_list_create_and_workflow(self):
        listed = self.client.get("/api/admin/runtime-servers/blackberry/features")
        self.assertEqual(listed.status_code, 200)
        list_payload = listed.json()
        self.assertTrue(list_payload["ok"])
        self.assertEqual(list_payload["counts"]["effective"], 1)
        self.assertEqual(list_payload["effective_items"][0]["source_scope"], "server")

        created = self.client.post(
            "/api/admin/runtime-servers/blackberry/features",
            json={
                "title": "Проверка теста",
                "key": "law_qa_retrieval",
                "status": "draft",
                "feature_flag": "law_qa_retrieval",
                "config": {
                    "feature_code": "law_qa_retrieval",
                    "enabled": True,
                    "rollout": "server_override",
                    "owner": "ops",
                    "notes": "server feature override",
                    "order": 2,
                },
            },
        )
        self.assertEqual(created.status_code, 200)
        create_payload = created.json()
        self.assertTrue(create_payload["ok"])
        change_request_id = int(create_payload["change_request"]["id"])

        workflow = self.client.post(
            "/api/admin/runtime-servers/blackberry/features/law_qa_retrieval/workflow",
            json={"action": "submit_for_review", "change_request_id": change_request_id},
        )
        self.assertEqual(workflow.status_code, 200)
        workflow_payload = workflow.json()
        self.assertEqual(workflow_payload["result"]["change_request"]["status"], "in_review")

    def test_runtime_server_templates_endpoints_support_effective_list_preview_placeholders_and_reset(self):
        listed = self.client.get("/api/admin/runtime-servers/blackberry/templates")
        self.assertEqual(listed.status_code, 200)
        list_payload = listed.json()
        self.assertTrue(list_payload["ok"])
        self.assertEqual(list_payload["counts"]["effective"], 1)
        self.assertEqual(list_payload["effective_items"][0]["source_scope"], "global")

        created = self.client.post(
            "/api/admin/runtime-servers/blackberry/templates",
            json={
                "title": "Жалоба",
                "key": "complaint_template_v1",
                "status": "draft",
                "output_format": "bbcode",
                "config": {
                    "template_code": "complaint_template_v1",
                    "title": "Жалоба",
                    "body": "[b]{{document_title}}[/b]\\n{{result}}\\n{{server_code}}",
                    "format": "bbcode",
                    "status": "draft",
                    "notes": "server template override",
                },
            },
        )
        self.assertEqual(created.status_code, 200)
        create_payload = created.json()
        self.assertTrue(create_payload["ok"])
        change_request_id = int(create_payload["change_request"]["id"])

        preview = self.client.post(
            "/api/admin/runtime-servers/blackberry/templates/complaint_template_v1/preview",
            json={"sample_json": {"document_title": "Жалоба", "result": "Готово", "server_title": "BlackBerry"}},
        )
        self.assertEqual(preview.status_code, 200)
        preview_payload = preview.json()
        self.assertIn("Готово", preview_payload["preview"])
        self.assertIn("blackberry", preview_payload["preview"])

        placeholders = self.client.get("/api/admin/runtime-servers/blackberry/templates/complaint_template_v1/placeholders")
        self.assertEqual(placeholders.status_code, 200)
        placeholders_payload = placeholders.json()
        self.assertGreaterEqual(placeholders_payload["count"], 6)

        workflow = self.client.post(
            "/api/admin/runtime-servers/blackberry/templates/complaint_template_v1/workflow",
            json={"action": "submit_for_review", "change_request_id": change_request_id},
        )
        self.assertEqual(workflow.status_code, 200)
        self.assertEqual(workflow.json()["result"]["change_request"]["status"], "in_review")

        reset = self.client.post("/api/admin/runtime-servers/blackberry/templates/complaint_template_v1/reset-to-default")
        self.assertEqual(reset.status_code, 200)
        reset_payload = reset.json()
        self.assertTrue(reset_payload["ok"])
        self.assertEqual(reset_payload["reset_source_scope"], "global")

    def test_second_server_published_pack_health_endpoint_reports_release_candidate_state(self):
        self.runtime_store.rows["orange"] = {
            "code": "orange",
            "title": "Orange City",
            "is_active": True,
            "created_at": "2026-04-16T00:00:00+00:00",
        }
        self.runtime_law_sets_store.law_sets[2] = {
            "id": 2,
            "server_code": "orange",
            "name": "Orange RC",
            "is_active": True,
            "is_published": True,
            "item_count": 1,
        }
        self.runtime_law_sets_store.bindings["orange"] = [
            {
                "law_set_id": 2,
                "item_id": 1,
                "law_code": "orange_code",
                "priority": 100,
                "effective_from": "",
                "source_name": "Orange Main",
                "source_url": "https://example.com/orange/law",
            }
        ]

        with patch(
            "ogp_web.server_config.registry._load_effective_pack_from_db",
            side_effect=lambda *, server_code, at_timestamp=None: orange_published_pack() if server_code == "orange" else None,
        ), patch.object(
            admin_runtime_servers_service,
            "resolve_active_law_version",
            return_value=ResolvedLawVersion(
                id=88,
                server_code="orange",
                generated_at_utc="2026-04-16T00:00:00+00:00",
                effective_from="2026-04-16",
                effective_to="",
                fingerprint="orange-fp",
                chunk_count=9,
            ),
        ):
            self.client.app.dependency_overrides[get_law_source_sets_store] = lambda: _FakeLawSourceSetsStore()
            response = self.client.get("/api/admin/runtime-servers/orange/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["summary"]["is_ready"])
        self.assertEqual(payload["onboarding"]["resolution_mode"], "published_pack")
        self.assertFalse(payload["onboarding"]["uses_transitional_fallback"])
        self.assertFalse(payload["onboarding"]["requires_explicit_runtime_pack"])
        self.assertTrue(payload["onboarding"]["resolution"]["is_runtime_addressable"])
        self.assertTrue(payload["checks"]["config_resolution"]["ok"])
        self.assertEqual(payload["runtime_provenance"]["mode"], "projection_backed")
        self.assertTrue(payload["runtime_provenance"]["is_projection_backed"])
        self.assertEqual(payload["runtime_alignment"]["status"], "aligned")
        self.assertTrue(payload["runtime_alignment"]["matches_active_law_version"])
        with patch(
            "ogp_web.server_config.registry._load_effective_pack_from_db",
            side_effect=lambda *, server_code, at_timestamp=None: orange_published_pack() if server_code == "orange" else None,
        ), patch.object(
            admin_runtime_servers_service,
            "resolve_active_law_version",
            return_value=ResolvedLawVersion(
                id=88,
                server_code="orange",
                generated_at_utc="2026-04-16T00:00:00+00:00",
                effective_from="2026-04-16",
                effective_to="",
                fingerprint="orange-fp",
                chunk_count=9,
            ),
        ):
            self.client.app.dependency_overrides[get_law_source_sets_store] = lambda: _FakeLawSourceSetsStore()
            workspace = self.client.get("/api/admin/runtime-servers/orange/workspace")
        self.assertEqual(workspace.status_code, 200)
        self.assertEqual(workspace.json()["overview"]["laws"]["runtime_version_parity"]["status"], "aligned")
        self.assertTrue(workspace.json()["overview"]["laws"]["runtime_version_parity"]["law_set_observational_only"])
        self.assertEqual(workspace.json()["overview"]["laws"]["runtime_version_parity"]["shell_stage"], "activated")
        self.assertEqual(workspace.json()["overview"]["laws"]["runtime_config_posture"]["status"], "declared_ready")
        self.assertEqual(workspace.json()["overview"]["laws"]["runtime_config_debt"]["status"], "low")
        self.assertEqual(workspace.json()["overview"]["laws"]["runtime_resolution_policy"]["status"], "declared_runtime")
        self.assertEqual(workspace.json()["overview"]["laws"]["projection_bridge_lifecycle"]["status"], "activated")
        self.assertTrue(workspace.json()["overview"]["laws"]["projection_bridge_lifecycle"]["law_set_observational_only"])
        self.assertEqual(workspace.json()["overview"]["laws"]["projection_bridge_lifecycle"]["shell_stage"], "activated")
        self.assertEqual(workspace.json()["overview"]["laws"]["projection_bridge_readiness"]["status"], "ready")
        self.assertEqual(workspace.json()["overview"]["laws"]["promotion_candidate"]["status"], "ready")
        self.assertEqual(workspace.json()["overview"]["laws"]["promotion_delta"]["status"], "stable")
        self.assertEqual(workspace.json()["overview"]["laws"]["promotion_blockers"]["status"], "clear")
        self.assertEqual(workspace.json()["overview"]["laws"]["promotion_review_signal"]["status"], "stable")
        self.assertEqual(workspace.json()["overview"]["laws"]["activation_gap"]["status"], "closed")
        self.assertEqual(workspace.json()["overview"]["laws"]["runtime_shell_debt"]["status"], "low")
        self.assertEqual(workspace.json()["overview"]["laws"]["runtime_convergence"]["status"], "converged")
        self.assertEqual(workspace.json()["overview"]["laws"]["cutover_readiness"]["status"], "ready_for_cutover")
        self.assertEqual(workspace.json()["overview"]["laws"]["runtime_cutover_mode"]["status"], "projection_preferred")
        self.assertEqual(workspace.json()["overview"]["laws"]["runtime_bridge_policy"]["status"], "prefer_projection_runtime")
        self.assertEqual(workspace.json()["overview"]["laws"]["runtime_operating_mode"]["status"], "projection_runtime")
        self.assertEqual(workspace.json()["overview"]["laws"]["runtime_policy_violations"]["status"], "clear")
        self.assertEqual(workspace.json()["overview"]["laws"]["cutover_guardrails"]["status"], "enforced")
        self.assertEqual(workspace.json()["overview"]["laws"]["runtime_policy_enforcement"]["status"], "enforced")
        self.assertEqual(workspace.json()["overview"]["laws"]["policy_breach_summary"]["status"], "clear")
        self.assertEqual(workspace.json()["overview"]["laws"]["runtime_risk_register"]["status"], "low")
        self.assertEqual(workspace.json()["overview"]["laws"]["runtime_governance_contract"]["status"], "projection_contract")
        self.assertEqual(workspace.json()["overview"]["laws"]["legacy_path_allowance"]["status"], "denied")
        self.assertEqual(workspace.json()["overview"]["laws"]["compatibility_exit_scorecard"]["status"], "ready_to_exit")
        self.assertEqual(workspace.json()["overview"]["laws"]["runtime_breach_categories"]["status"], "clear")
        self.assertEqual(workspace.json()["overview"]["laws"]["legacy_path_controls"]["status"], "projection_controls")
        self.assertEqual(workspace.json()["overview"]["laws"]["projection_runtime_gate"]["status"], "open")
        self.assertEqual(workspace.json()["overview"]["laws"]["compatibility_shrink_decision"]["status"], "shrink_now")
        self.assertEqual(workspace.json()["overview"]["laws"]["runtime_exception_register"]["status"], "clear")
        self.assertEqual(workspace.json()["overview"]["laws"]["compatibility_path_matrix"]["status"], "projection_matrix")
        self.assertEqual(workspace.json()["overview"]["laws"]["next_shrink_step"]["status"], "observe")
        self.assertEqual(workspace.json()["overview"]["laws"]["shrink_sequence"]["status"], "complete")
        self.assertEqual(workspace.json()["overview"]["laws"]["bridge_shrink_checklist"]["status"], "ready")
        self.assertEqual(workspace.json()["overview"]["laws"]["cutover_blockers_breakdown"]["status"], "clear")
        self.assertEqual(payload["onboarding"]["highest_completed_state"], "rollout-ready")
        self.assertEqual(payload["checks"]["health"]["active_law_version_id"], 88)
        self.assertEqual(payload["projection_bridge"]["run_id"], 4)
        self.assertEqual(payload["projection_bridge"]["law_set_id"], 2)
        self.assertEqual(payload["projection_bridge"]["law_version_id"], 88)
        self.assertTrue(payload["projection_bridge"]["matches_active_law_version"])

    def test_catalog_audit_accepts_entity_filters(self):
        fake_workflow = _FakeContentWorkflowService()
        self.client.app.dependency_overrides[get_content_workflow_service] = lambda: fake_workflow

        response = self.client.get("/api/admin/catalog/audit", params={"entity_type": " LaW ", "entity_id": " 42 ", "limit": 5})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["filters"], {"entity_type": "law", "entity_id": "42", "limit": 5})
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(fake_workflow.calls[-1]["entity_type"], "law")
        self.assertEqual(fake_workflow.calls[-1]["entity_id"], "42")
        self.assertEqual(fake_workflow.calls[-1]["limit"], 5)

    def test_catalog_audit_returns_default_filters_when_not_passed(self):
        fake_workflow = _FakeContentWorkflowService()
        self.client.app.dependency_overrides[get_content_workflow_service] = lambda: fake_workflow

        response = self.client.get("/api/admin/catalog/audit")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["filters"], {"entity_type": "", "entity_id": "", "limit": 100})
        self.assertEqual(fake_workflow.calls[-1]["entity_type"], "")
        self.assertEqual(fake_workflow.calls[-1]["entity_id"], "")
        self.assertEqual(fake_workflow.calls[-1]["limit"], 100)

    def test_platform_blueprint_status_returns_default_stage(self):
        previous = os.environ.get("OGP_ADMIN_PLATFORM_STAGE")
        os.environ.pop("OGP_ADMIN_PLATFORM_STAGE", None)
        try:
            response = self.client.get("/api/admin/platform-blueprint/status")
        finally:
            if previous is None:
                os.environ.pop("OGP_ADMIN_PLATFORM_STAGE", None)
            else:
                os.environ["OGP_ADMIN_PLATFORM_STAGE"] = previous

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get("ok"))
        self.assertEqual(payload["stage"]["stage_code"], "phase_a_foundation")
        self.assertIn("Phase A", payload["stage"]["stage_label"])

    def test_platform_blueprint_status_accepts_known_stage_from_env(self):
        previous = os.environ.get("OGP_ADMIN_PLATFORM_STAGE")
        os.environ["OGP_ADMIN_PLATFORM_STAGE"] = "phase_c_quality_center"
        try:
            response = self.client.get("/api/admin/platform-blueprint/status")
        finally:
            if previous is None:
                os.environ.pop("OGP_ADMIN_PLATFORM_STAGE", None)
            else:
                os.environ["OGP_ADMIN_PLATFORM_STAGE"] = previous

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["stage"]["stage_code"], "phase_c_quality_center")
        self.assertIn("Phase C", payload["stage"]["stage_label"])

    def test_platform_blueprint_status_falls_back_for_unknown_stage(self):
        previous = os.environ.get("OGP_ADMIN_PLATFORM_STAGE")
        os.environ["OGP_ADMIN_PLATFORM_STAGE"] = "phase_z_unknown"
        try:
            response = self.client.get("/api/admin/platform-blueprint/status")
        finally:
            if previous is None:
                os.environ.pop("OGP_ADMIN_PLATFORM_STAGE", None)
            else:
                os.environ["OGP_ADMIN_PLATFORM_STAGE"] = previous

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["stage"]["stage_code"], "phase_a_foundation")
        self.assertIn("Phase A", payload["stage"]["stage_label"])

    def test_catalog_audit_maps_value_error_to_400_with_error_code_header(self):
        fake_workflow = _FakeContentWorkflowServiceError(ValueError("bad_filter"))
        self.client.app.dependency_overrides[get_content_workflow_service] = lambda: fake_workflow

        response = self.client.get("/api/admin/catalog/audit", params={"entity_type": "laws"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("bad_filter", response.json().get("detail", []))
        self.assertEqual(response.headers.get("x-error-code"), "admin_catalog_audit_bad_request")

    def test_catalog_audit_maps_permission_error_to_404_with_error_code_header(self):
        fake_workflow = _FakeContentWorkflowServiceError(PermissionError("forbidden_scope"))
        self.client.app.dependency_overrides[get_content_workflow_service] = lambda: fake_workflow

        response = self.client.get("/api/admin/catalog/audit", params={"entity_type": "laws"})

        self.assertEqual(response.status_code, 404)
        self.assertIn("forbidden_scope", response.json().get("detail", []))
        self.assertEqual(response.headers.get("x-error-code"), "admin_catalog_audit_not_found")

    def test_change_request_validate_endpoint_returns_validation_payload(self):
        fake_workflow = _FakeContentWorkflowService()
        self.client.app.dependency_overrides[get_content_workflow_service] = lambda: fake_workflow

        response = self.client.get("/api/admin/change-requests/17/validate")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["result"]["ok"])
        self.assertEqual(payload["result"]["change_request"]["id"], 17)
        self.assertEqual(fake_workflow.calls[-1]["kind"], "validate_change_request")
        self.assertEqual(fake_workflow.calls[-1]["change_request_id"], 17)

    def test_catalog_list_accepts_legacy_laws_alias_and_normalizes_to_procedures(self):
        fake_workflow = _FakeContentWorkflowService()
        self.client.app.dependency_overrides[get_content_workflow_service] = lambda: fake_workflow

        response = self.client.get("/api/admin/catalog/laws")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["entity_type"], "laws")
        self.assertEqual(payload["items"][0]["content_type"], "procedures")
        first_call = fake_workflow.calls[0]
        self.assertEqual(first_call["kind"], "list_content_items")
        self.assertEqual(first_call["content_type"], "procedures")

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
    get_canonical_law_document_versions_store,
    get_content_workflow_service,
    get_law_source_sets_store,
    get_runtime_law_sets_store,
    get_server_effective_law_projections_store,
)
from ogp_web.rate_limit import reset_for_testing as reset_rate_limit
from ogp_web.services.exam_import_tasks import ExamImportTaskRegistry
from ogp_web.storage.admin_metrics_store import AdminMetricsStore
from ogp_web.storage.exam_answers_store import ExamAnswersStore
from ogp_web.storage.user_repository import UserRepository
from ogp_web.storage.user_store import UserStore
from tests.temp_helpers import make_temporary_directory
from tests.test_web_storage import (
    FakeAdminMetricsPostgresBackend,
    FakeExamAnswersPostgresBackend,
    FakeExamImportTasksPostgresBackend,
    PostgresBackend,
)


class _FakeBinding:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeVersion:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeSourceSetsStore:
    def list_bindings(self, *, server_code: str):
        if server_code != "orange":
            return []
        return [
            _FakeBinding(
                id=1,
                server_code="orange",
                source_set_key="orange-priority",
                priority=10,
                is_active=True,
                include_law_keys=(),
                exclude_law_keys=(),
                pin_policy_json={},
                metadata_json={},
            ),
            _FakeBinding(
                id=2,
                server_code="orange",
                source_set_key="orange-core",
                priority=20,
                is_active=True,
                include_law_keys=(),
                exclude_law_keys=(),
                pin_policy_json={},
                metadata_json={},
            ),
        ]


class _FakeVersionsStore:
    def __init__(self):
        self._versions = {
            8: _FakeVersion(
                id=8,
                canonical_law_document_id=1,
                canonical_identity_key="url_seed:law-a",
                display_title="Law A",
                source_discovery_run_id=12,
                discovered_law_link_id=102,
                source_set_key="orange-priority",
                source_set_revision_id=4,
                revision=4,
                normalized_url="https://example.com/law/a",
                source_container_url="https://example.com/container/2",
                fetch_status="fetched",
                parse_status="parsed",
                content_checksum="def",
                raw_title="Law A",
                parsed_title="Law A",
                body_text="Law A body updated",
                metadata_json={},
                created_at="2026-04-16T05:10:00+00:00",
                updated_at="2026-04-16T05:10:00+00:00",
            ),
            9: _FakeVersion(
                id=9,
                canonical_law_document_id=2,
                canonical_identity_key="url_seed:law-b",
                display_title="Law B",
                source_discovery_run_id=13,
                discovered_law_link_id=103,
                source_set_key="orange-core",
                source_set_revision_id=3,
                revision=3,
                normalized_url="https://example.com/law/b",
                source_container_url="https://example.com/container/1",
                fetch_status="fetched",
                parse_status="parsed",
                content_checksum="ghi",
                raw_title="Law B",
                parsed_title="Law B",
                body_text="Law B body",
                metadata_json={},
                created_at="2026-04-16T05:20:00+00:00",
                updated_at="2026-04-16T05:20:00+00:00",
            ),
        }

    def list_parsed_versions_for_source_sets(self, *, source_set_keys):
        return [self._versions[8], self._versions[9]]

    def get_version(self, *, version_id: int):
        return self._versions.get(int(version_id))


class _FakeRun:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeItem:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeProjectionsStore:
    def __init__(self):
        self.runs = []
        self.items = []

    def list_runs(self, *, server_code: str):
        return [item for item in self.runs if item.server_code == server_code]

    def get_run(self, *, run_id: int):
        return next((item for item in self.runs if int(item.id) == int(run_id)), None)

    def list_items(self, *, projection_run_id: int):
        return [item for item in self.items if int(item.projection_run_id) == int(projection_run_id)]

    def create_projection_run(self, **kwargs):
        item = _FakeRun(
            id=len(self.runs) + 1,
            server_code=kwargs["server_code"],
            trigger_mode=kwargs["trigger_mode"],
            status=kwargs["status"],
            summary_json=dict(kwargs.get("summary_json") or {}),
            created_at="2026-04-16T06:00:00+00:00",
        )
        self.runs.insert(0, item)
        return item

    def create_projection_item(self, **kwargs):
        item = _FakeItem(
            id=len(self.items) + 1,
            projection_run_id=kwargs["projection_run_id"],
            canonical_law_document_id=kwargs["canonical_law_document_id"],
            canonical_identity_key=kwargs["canonical_identity_key"],
            normalized_url=kwargs["normalized_url"],
            selected_document_version_id=kwargs["selected_document_version_id"],
            selected_source_set_key=kwargs["selected_source_set_key"],
            selected_revision=kwargs["selected_revision"],
            precedence_rank=kwargs["precedence_rank"],
            contributor_count=kwargs["contributor_count"],
            status=kwargs["status"],
            provenance_json=dict(kwargs.get("provenance_json") or {}),
            created_at="2026-04-16T06:01:00+00:00",
        )
        self.items.append(item)
        return item

    def update_run_status(self, *, run_id: int, status: str, summary_json=None):
        item = self.get_run(run_id=run_id)
        if item is None:
            raise KeyError("server_effective_law_projection_run_not_found")
        item.status = status
        item.summary_json = dict(summary_json or {})
        return item


class _FakeSource:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeRuntimeLawSetsStore:
    def __init__(self):
        self.sources = []
        self.law_sets = []
        self.items_by_law_set = {}

    def list_sources(self):
        return list(self.sources)

    def create_source(self, *, name: str, kind: str, url: str):
        item = _FakeSource(
            id=len(self.sources) + 1,
            name=name,
            kind=kind,
            url=url,
            is_active=True,
        )
        self.sources.append(item)
        return item

    def create_law_set(self, *, server_code: str, name: str):
        item = {
            "id": len(self.law_sets) + 1,
            "server_code": server_code,
            "name": name,
            "is_active": True,
            "is_published": False,
        }
        self.law_sets.append(item)
        return dict(item)

    def replace_law_set_items(self, *, law_set_id: int, items):
        self.items_by_law_set[int(law_set_id)] = list(items)
        return list(items)

    def update_law_set(self, *, law_set_id: int, name: str, is_active: bool):
        item = next(row for row in self.law_sets if int(row["id"]) == int(law_set_id))
        item["name"] = name
        item["is_active"] = bool(is_active)
        return dict(item)

    def publish_law_set(self, *, law_set_id: int):
        item = next(row for row in self.law_sets if int(row["id"]) == int(law_set_id))
        item["is_published"] = True
        item["is_active"] = True
        return dict(item)

    def list_source_urls_for_law_set(self, *, law_set_id: int):
        item = next(row for row in self.law_sets if int(row["id"]) == int(law_set_id))
        stored_items = self.items_by_law_set.get(int(law_set_id), [])
        source_urls = []
        for law_item in stored_items:
            source = next(source for source in self.sources if int(source.id) == int(law_item["source_id"]))
            source_urls.append(str(source.url))
        return str(item["server_code"]), list(source_urls)

    def get_law_set_detail(self, *, law_set_id: int):
        item = next(row for row in self.law_sets if int(row["id"]) == int(law_set_id))
        stored_items = self.items_by_law_set.get(int(law_set_id), [])
        detail_items = []
        for index, law_item in enumerate(stored_items, start=1):
            source = next(source for source in self.sources if int(source.id) == int(law_item["source_id"]))
            detail_items.append(
                {
                    "id": index,
                    "law_set_id": int(law_set_id),
                    "law_code": law_item["law_code"],
                    "effective_from": law_item.get("effective_from", ""),
                    "priority": law_item["priority"],
                    "source_id": law_item["source_id"],
                    "source_name": source.name,
                    "source_url": source.url,
                }
            )
        return {"law_set": dict(item), "items": detail_items}


class AdminLawProjectionApiTests(unittest.TestCase):
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
        self.source_sets_store = _FakeSourceSetsStore()
        self.versions_store = _FakeVersionsStore()
        self.projections_store = _FakeProjectionsStore()
        self.runtime_law_sets_store = _FakeRuntimeLawSetsStore()
        app.dependency_overrides[get_law_source_sets_store] = lambda: self.source_sets_store
        app.dependency_overrides[get_canonical_law_document_versions_store] = lambda: self.versions_store
        app.dependency_overrides[get_server_effective_law_projections_store] = lambda: self.projections_store
        app.dependency_overrides[get_runtime_law_sets_store] = lambda: self.runtime_law_sets_store
        class _DummyWorkflowService:
            repository = object()
        app.dependency_overrides[get_content_workflow_service] = lambda: _DummyWorkflowService()
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
        split = urlsplit(response.json()["verification_url"])
        self.client.get(f"{split.path}?{split.query}")
        login = self.client.post("/api/auth/login", json={"username": username, "password": "Password123!"})
        self.assertEqual(login.status_code, 200)

    def test_admin_law_projection_preview_and_read_endpoints(self):
        preview = self.client.post(
            "/api/admin/runtime-servers/orange/law-projection-runs",
            json={"trigger_mode": "manual", "safe_rerun": True},
        )
        self.assertEqual(preview.status_code, 200)
        self.assertTrue(preview.json()["changed"])
        self.assertEqual(preview.json()["count"], 2)

        runs = self.client.get("/api/admin/runtime-servers/orange/law-projection-runs")
        self.assertEqual(runs.status_code, 200)
        self.assertEqual(runs.json()["count"], 1)

        items = self.client.get("/api/admin/law-projection-runs/1/items")
        self.assertEqual(items.status_code, 200)
        self.assertEqual(items.json()["count"], 2)
        self.assertEqual(items.json()["items"][0]["selected_source_set_key"], "orange-priority")

        approved = self.client.post("/api/admin/law-projection-runs/1/approve", json={"reason": "looks_good"})
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["run"]["status"], "approved")

        materialized = self.client.post("/api/admin/law-projection-runs/1/materialize-law-set", json={"safe_rerun": True})
        self.assertEqual(materialized.status_code, 200)
        self.assertTrue(materialized.json()["changed"])
        self.assertEqual(materialized.json()["law_set"]["server_code"], "orange")
        self.assertFalse(materialized.json()["law_set"]["is_published"])
        self.assertFalse(materialized.json()["law_set"]["is_active"])

        reused = self.client.post("/api/admin/law-projection-runs/1/materialize-law-set", json={"safe_rerun": True})
        self.assertEqual(reused.status_code, 200)
        self.assertFalse(reused.json()["changed"])
        self.assertTrue(reused.json()["reused_law_set"])

        with patch("ogp_web.services.admin_law_projection_service.import_law_snapshot", return_value=91) as fake_import:
            activated = self.client.post("/api/admin/law-projection-runs/1/activate-runtime", json={"safe_rerun": True})
        self.assertEqual(activated.status_code, 200)
        self.assertTrue(activated.json()["changed"])
        self.assertEqual(activated.json()["activation"]["law_version_id"], 91)
        self.assertEqual(fake_import.call_args.kwargs["server_code"], "orange")
        self.assertGreater(activated.json()["activation"]["chunk_count"], 0)

        with patch(
            "ogp_web.routes.admin.resolve_active_law_version",
            return_value=type(
                "_ActiveVersion",
                (),
                {
                    "id": 91,
                    "server_code": "orange",
                    "generated_at_utc": "2026-04-16T06:20:00+00:00",
                    "effective_from": "2026-04-16T06:20:00+00:00",
                    "effective_to": "",
                    "fingerprint": "runtime-fingerprint",
                    "chunk_count": 2,
                },
            )(),
        ):
            status_payload = self.client.get("/api/admin/law-projection-runs/1/status")
        self.assertEqual(status_payload.status_code, 200)
        self.assertEqual(status_payload.json()["materialization"]["law_set_id"], 1)
        self.assertEqual(status_payload.json()["activation"]["law_version_id"], 91)
        self.assertEqual(status_payload.json()["active_law_version"]["id"], 91)
        self.assertTrue(status_payload.json()["runtime_alignment"]["item_count_matches_materialization"])
        self.assertTrue(status_payload.json()["runtime_alignment"]["activation_law_version_matches_active"])

        with patch("ogp_web.services.admin_law_projection_service.import_law_snapshot") as fake_rebuild_again:
            reused_activation = self.client.post("/api/admin/law-projection-runs/1/activate-runtime", json={"safe_rerun": True})
        self.assertEqual(reused_activation.status_code, 200)
        self.assertFalse(reused_activation.json()["changed"])
        self.assertTrue(reused_activation.json()["reused_activation"])
        fake_rebuild_again.assert_not_called()

        held = self.client.post("/api/admin/law-projection-runs/1/hold", json={"reason": "manual_pause"})
        self.assertEqual(held.status_code, 200)
        self.assertEqual(held.json()["run"]["status"], "held")

    def test_admin_law_projection_missing_run(self):
        response = self.client.get("/api/admin/law-projection-runs/999/items")
        self.assertEqual(response.status_code, 404)
        self.assertIn("server_effective_law_projection_run_not_found", " ".join(response.json().get("detail") or []))
        status_response = self.client.get("/api/admin/law-projection-runs/999/status")
        self.assertEqual(status_response.status_code, 404)
        self.assertIn("server_effective_law_projection_run_not_found", " ".join(status_response.json().get("detail") or []))

    def test_admin_runtime_server_law_projection_server_scoped_apply_endpoints(self):
        preview = self.client.post(
            "/api/admin/runtime-servers/orange/law-projection-runs",
            json={"trigger_mode": "manual", "safe_rerun": True},
        )
        self.assertEqual(preview.status_code, 200)

        approved = self.client.post(
            "/api/admin/runtime-servers/orange/law-projection-runs/1/approve",
            json={"reason": "server_workspace_apply_flow"},
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["run"]["status"], "approved")

        materialized = self.client.post(
            "/api/admin/runtime-servers/orange/law-projection-runs/1/materialize-law-set",
            json={"safe_rerun": True},
        )
        self.assertEqual(materialized.status_code, 200)
        self.assertEqual(materialized.json()["law_set"]["server_code"], "orange")

        with patch("ogp_web.services.admin_law_projection_service.import_law_snapshot", return_value=91):
            activated = self.client.post(
                "/api/admin/runtime-servers/orange/law-projection-runs/1/activate-runtime",
                json={"safe_rerun": True},
            )
        self.assertEqual(activated.status_code, 200)
        self.assertEqual(activated.json()["activation"]["law_version_id"], 91)

        with patch(
            "ogp_web.routes.admin.resolve_active_law_version",
            return_value=type(
                "_ActiveVersion",
                (),
                {
                    "id": 91,
                    "server_code": "orange",
                    "generated_at_utc": "2026-04-16T06:20:00+00:00",
                    "effective_from": "2026-04-16T06:20:00+00:00",
                    "effective_to": "",
                    "fingerprint": "runtime-fingerprint",
                    "chunk_count": 2,
                },
            )(),
        ):
            status_payload = self.client.get("/api/admin/runtime-servers/orange/law-projection-runs/1/status")
        self.assertEqual(status_payload.status_code, 200)
        self.assertEqual(status_payload.json()["run"]["server_code"], "orange")
        self.assertEqual(status_payload.json()["activation"]["law_version_id"], 91)

    def test_admin_law_projection_materialize_requires_approved_run(self):
        preview = self.client.post(
            "/api/admin/runtime-servers/orange/law-projection-runs",
            json={"trigger_mode": "manual", "safe_rerun": True},
        )
        self.assertEqual(preview.status_code, 200)
        response = self.client.post("/api/admin/law-projection-runs/1/materialize-law-set", json={"safe_rerun": True})
        self.assertEqual(response.status_code, 400)
        self.assertIn("server_effective_law_projection_run_not_approved", " ".join(response.json().get("detail") or []))

    def test_admin_law_projection_activate_requires_materialized_run(self):
        preview = self.client.post(
            "/api/admin/runtime-servers/orange/law-projection-runs",
            json={"trigger_mode": "manual", "safe_rerun": True},
        )
        self.assertEqual(preview.status_code, 200)
        approved = self.client.post("/api/admin/law-projection-runs/1/approve", json={"reason": "looks_good"})
        self.assertEqual(approved.status_code, 200)
        response = self.client.post("/api/admin/law-projection-runs/1/activate-runtime", json={"safe_rerun": True})
        self.assertEqual(response.status_code, 400)
        self.assertIn("server_effective_law_projection_materialization_missing", " ".join(response.json().get("detail") or []))

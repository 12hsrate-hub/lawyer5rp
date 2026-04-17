from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.law_context_readiness_service import LawContextReadinessService
from ogp_web.services.runtime_pack_reader_service import RuntimePackSnapshot


class _DummyWorkflowService:
    repository = type("Repo", (), {"backend": object()})()


class _FakeBinding:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeSourceSetsStore:
    def __init__(self, *, bindings=None, revisions=None):
        self._bindings = list(bindings or [])
        self._revisions = dict(revisions or {})

    def list_bindings(self, *, server_code: str):
        _ = server_code
        return list(self._bindings)

    def list_revisions(self, *, source_set_key: str):
        return list(self._revisions.get(source_set_key, []))


class _FakeProjectionRun:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeProjectionsStore:
    def __init__(self, runs=None):
        self._runs = list(runs or [])

    def list_runs(self, *, server_code: str):
        _ = server_code
        return list(self._runs)


class _FakeLawAdminService:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def get_effective_sources(self, *, server_code: str):
        _ = server_code
        return self.snapshot


class LawContextReadinessServiceTests(unittest.TestCase):
    def test_projection_bridge_mode_is_ready_when_bindings_projection_and_active_version_match(self):
        service = LawContextReadinessService(
            workflow_service=_DummyWorkflowService(),
            source_sets_store=_FakeSourceSetsStore(
                bindings=[_FakeBinding(id=1, source_set_key="orange-main", is_active=True)],
                revisions={"orange-main": [type("Revision", (), {"id": 10, "status": "published"})()]},
            ),
            projections_store=_FakeProjectionsStore(
                runs=[
                    _FakeProjectionRun(
                        id=7,
                        status="approved",
                        summary_json={"activation": {"law_version_id": 88}},
                    )
                ]
            ),
        )
        service.law_admin_service = _FakeLawAdminService(
            type(
                "Snapshot",
                (),
                {
                    "source_origin": "content_workflow",
                    "source_urls": ("https://example.com/law/a",),
                    "active_law_version": {"id": 88},
                    "bundle_meta": {"fingerprint": "abc", "chunk_count": 42},
                },
            )()
        )

        readiness = service.get_readiness(server_code="orange")

        self.assertTrue(readiness.is_ready)
        self.assertEqual(readiness.mode, "projection_bridge")
        self.assertEqual(readiness.projection_run_id, 7)
        self.assertEqual(readiness.active_binding_ids, (1,))

    def test_runtime_drift_blocks_when_requested_version_differs_from_selected_server_active_version(self):
        service = LawContextReadinessService(
            workflow_service=_DummyWorkflowService(),
            source_sets_store=_FakeSourceSetsStore(),
            projections_store=_FakeProjectionsStore(),
        )
        service.law_admin_service = _FakeLawAdminService(
            type(
                "Snapshot",
                (),
                {
                    "source_origin": "content_workflow",
                    "source_urls": ("https://example.com/law/a",),
                    "active_law_version": {"id": 88},
                    "bundle_meta": {"fingerprint": "abc", "chunk_count": 42},
                },
            )()
        )

        readiness = service.get_readiness(server_code="orange", requested_law_version_id=77)

        self.assertFalse(readiness.is_ready)
        self.assertEqual(readiness.reason_code, "runtime_drift")
        self.assertFalse(readiness.matches_requested_version)

    def test_legacy_bundle_fallback_stays_ready_with_compatibility_when_bundle_exists_without_active_version(self):
        service = LawContextReadinessService(
            workflow_service=_DummyWorkflowService(),
            source_sets_store=_FakeSourceSetsStore(),
            projections_store=_FakeProjectionsStore(),
        )
        service.law_admin_service = _FakeLawAdminService(
            type(
                "Snapshot",
                (),
                {
                    "source_origin": "server_config",
                    "source_urls": ("https://example.com/law/a",),
                    "active_law_version": None,
                    "bundle_meta": {"fingerprint": "compat", "chunk_count": 13},
                },
            )()
        )

        readiness = service.get_readiness(server_code="blackberry")

        self.assertTrue(readiness.is_ready)
        self.assertEqual(readiness.status, "ready_with_compatibility")
        self.assertEqual(readiness.mode, "legacy_bundle_fallback")

    def test_runtime_pack_fallback_supplies_sources_and_provenance_when_snapshot_is_missing_them(self):
        service = LawContextReadinessService(
            workflow_service=_DummyWorkflowService(),
            source_sets_store=_FakeSourceSetsStore(),
            projections_store=_FakeProjectionsStore(),
        )
        service.law_admin_service = _FakeLawAdminService(
            type(
                "Snapshot",
                (),
                {
                    "source_origin": "server_config",
                    "source_urls": (),
                    "active_law_version": {"id": 88},
                    "bundle_meta": None,
                },
            )()
        )

        with patch(
            "ogp_web.services.law_context_readiness_service.read_runtime_pack_snapshot",
            return_value=RuntimePackSnapshot(
                server_code="orange",
                pack={"id": 9, "version": 3, "metadata": {}},
                metadata={
                    "law_qa_sources": ["https://example.com/law/runtime-pack"],
                    "law_qa_bundle_path": "law/orange.bundle.json",
                },
                resolution_mode="published_pack",
                source_label="published pack",
            ),
        ), patch(
            "ogp_web.services.law_context_readiness_service.load_law_bundle_meta",
            return_value=type("BundleMeta", (), {"fingerprint": "runtime-pack", "chunk_count": 11})(),
        ):
            readiness = service.get_readiness(server_code="orange")

        self.assertTrue(readiness.is_ready)
        self.assertEqual(readiness.mode, "legacy_effective_sources")
        self.assertEqual(readiness.source_origin, "runtime_pack")
        self.assertEqual(readiness.runtime_pack_resolution_mode, "published_pack")
        self.assertEqual(readiness.runtime_pack_version, 3)
        self.assertTrue(readiness.runtime_pack_is_published)
        payload = readiness.to_payload()
        self.assertEqual(payload["runtime_pack"]["resolution_mode"], "published_pack")
        self.assertEqual(payload["provenance_refs"]["runtime_pack_version"], 3)


if __name__ == "__main__":
    unittest.main()

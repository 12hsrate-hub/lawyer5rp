from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.provenance_service import ProvenanceService


class FakeDocumentRepository:
    def __init__(self):
        self.get_document_version_calls = 0
        self.get_latest_document_version_calls = 0

    def get_document_version(self, *, version_id: int):
        self.get_document_version_calls += 1
        if version_id != 77:
            return None
        return {
            "id": 77,
            "document_id": 12,
            "version_number": 3,
            "generation_snapshot_id": 501,
        }

    def get_latest_document_version_by_generation_snapshot_id(self, *, generation_snapshot_id: int):
        self.get_latest_document_version_calls += 1
        if generation_snapshot_id != 501:
            return None
        return {
            "id": 77,
            "document_id": 12,
            "version_number": 3,
            "generation_snapshot_id": 501,
        }


class FakeUserStore:
    def get_generation_snapshot_by_id(self, snapshot_id: int):
        if snapshot_id != 501:
            return None
        return {
            "id": 501,
            "server_code": "blackberry",
            "document_kind": "complaint",
            "created_at": "2026-04-15T00:00:00+00:00",
            "context_snapshot": {
                "ai": {"provider": "openai", "model": "gpt-5.4"},
                "content_workflow": {"procedure": "complaint_law_index", "template": "complaint_template_v1"},
                "effective_versions": {"law_version_id": 35},
            },
            "effective_config_snapshot": {
                "server_config_version": "blackberry@2026-04-15",
                "law_set_version": "laws@35",
            },
            "content_workflow_ref": {
                "procedure": "complaint_law_index@v2",
                "template": "complaint_template_v1@v3",
                "prompt_version": "complaint_prompt_v4",
            },
        }

    def get_document_version_citations(self, *, document_version_id: int, server_id: str | None = None):
        assert document_version_id == 77
        assert server_id == "blackberry"
        return [
            {"id": 901, "retrieval_run_id": 444, "source_version_id": 35},
            {"id": 902, "retrieval_run_id": 444, "source_version_id": 35},
        ]


class FakeValidationService:
    def get_latest_target_validation(self, *, target_type: str, target_id: int):
        assert target_type == "document_version"
        assert target_id == 77
        return {"id": 3001, "status": "passed"}


def test_provenance_service_builds_canonical_pilot_trace():
    service = ProvenanceService(
        document_repository=FakeDocumentRepository(),
        user_store=FakeUserStore(),
        validation_service=FakeValidationService(),
    )

    payload = service.get_document_version_trace(document_version_id=77)

    assert payload["document_version_id"] == 77
    assert payload["server_id"] == "blackberry"
    assert payload["document_kind"] == "complaint"
    assert payload["generation_snapshot_id"] == 501
    assert payload["config"]["server_config_version"] == "blackberry@2026-04-15"
    assert payload["config"]["procedure_version"] == "complaint_law_index@v2"
    assert payload["config"]["template_version"] == "complaint_template_v1@v3"
    assert payload["config"]["law_set_version"] == "laws@35"
    assert payload["config"]["law_version_id"] == 35
    assert payload["ai"]["provider"] == "openai"
    assert payload["ai"]["model_id"] == "gpt-5.4"
    assert payload["ai"]["prompt_version"] == "complaint_prompt_v4"
    assert payload["retrieval"]["retrieval_run_id"] == 444
    assert payload["retrieval"]["citation_ids"] == [901, 902]
    assert payload["validation"]["latest_run_id"] == 3001
    assert payload["validation"]["latest_status"] == "passed"


def test_provenance_service_returns_none_for_missing_version():
    service = ProvenanceService(
        document_repository=FakeDocumentRepository(),
        user_store=FakeUserStore(),
        validation_service=FakeValidationService(),
    )

    assert service.get_document_version_trace(document_version_id=999) is None


def test_provenance_service_builds_trace_from_generation_snapshot_id():
    document_repository = FakeDocumentRepository()
    service = ProvenanceService(
        document_repository=document_repository,
        user_store=FakeUserStore(),
        validation_service=FakeValidationService(),
    )

    payload = service.get_latest_trace_for_generation_snapshot(generation_snapshot_id=501)

    assert payload is not None
    assert payload["document_version_id"] == 77
    assert payload["generation_snapshot_id"] == 501
    assert document_repository.get_latest_document_version_calls == 1
    assert document_repository.get_document_version_calls == 0

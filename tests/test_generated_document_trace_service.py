from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.generated_document_trace_service import (
    build_generated_document_review_context_payload,
    parse_document_content_payload,
    resolve_generated_document_provenance_payload,
    resolve_admin_generated_document_trace_bundle,
)


class _FakeDocumentRepository:
    def __init__(self, backend):
        self.backend = backend

    def get_latest_document_version_by_generation_snapshot_id(self, *, generation_snapshot_id: int):
        if generation_snapshot_id != 501:
            return None
        return {
            "id": 77,
            "document_id": 12,
            "version_number": 3,
            "generation_snapshot_id": 501,
            "content_json": {"bbcode": "preview"},
        }


class _FakeStore:
    backend = object()

    def get_generation_snapshot_by_generated_document_id(self, *, document_id: int):
        if document_id != 100:
            return None
        return {
            "id": 100,
            "generation_snapshot_id": 501,
            "server_code": "blackberry",
            "document_kind": "complaint",
            "created_at": "2026-04-15T00:00:00+00:00",
            "context_snapshot": {"server": {"code": "blackberry"}},
        }


def test_generated_document_trace_bundle_resolves_snapshot_and_latest_version(monkeypatch):
    monkeypatch.setattr(
        "ogp_web.services.generated_document_trace_service.DocumentRepository",
        _FakeDocumentRepository,
    )
    bundle = resolve_admin_generated_document_trace_bundle(store=_FakeStore(), document_id=100)

    assert bundle is not None
    assert bundle.generation_snapshot_id == 501
    assert bundle.snapshot["document_kind"] == "complaint"
    assert bundle.version_row["id"] == 77


def test_parse_document_content_payload_normalizes_non_dict_json():
    payload = parse_document_content_payload({"content_json": "not-a-json-object"})
    assert payload == {}


def test_resolve_generated_document_provenance_payload_uses_shared_service(monkeypatch):
    class _FakeProvenanceService:
        def get_latest_trace_for_generation_snapshot(self, *, generation_snapshot_id: int):
            return {"generation_snapshot_id": generation_snapshot_id, "document_kind": "complaint"}

    monkeypatch.setattr(
        "ogp_web.services.generated_document_trace_service.build_store_provenance_service",
        lambda *, store: _FakeProvenanceService(),
    )

    payload = resolve_generated_document_provenance_payload(store=_FakeStore(), generation_snapshot_id=501)

    assert payload == {"generation_snapshot_id": 501, "document_kind": "complaint"}


def test_build_generated_document_review_context_payload_returns_normalized_bundle(monkeypatch):
    monkeypatch.setattr(
        "ogp_web.services.generated_document_trace_service.DocumentRepository",
        _FakeDocumentRepository,
    )
    bundle = resolve_admin_generated_document_trace_bundle(store=_FakeStore(), document_id=100)
    assert bundle is not None

    class _FakeValidationService:
        def __init__(self, repository):
            self.repository = repository

        def get_latest_target_validation(self, *, target_type: str, target_id: int):
            assert target_type == "document_version"
            assert target_id == 77
            return {
                "id": 91,
                "status": "pass",
                "issues": [
                    {
                        "issue_code": "ok",
                        "severity": "info",
                        "message": "fine",
                        "field_ref": "bbcode",
                    }
                ],
            }

    class _FakeArtifactRepository:
        def __init__(self, backend):
            self.backend = backend

        def list_exports_for_document_version(self, *, document_version_id: int):
            assert document_version_id == 77
            return [{"id": 5, "format": "pdf", "status": "ready", "created_at": "2026-04-15T00:00:00+00:00"}]

        def list_attachments_for_document_version(self, *, document_version_id: int):
            assert document_version_id == 77
            return [{"id": 8, "filename": "proof.pdf", "upload_status": "uploaded", "link_type": "supporting"}]

    class _FakeProvenanceService:
        def get_document_version_trace(self, *, document_version_id: int):
            assert document_version_id == 77
            return {"document_version_id": 77, "document_kind": "complaint"}

    class _FakeStoreWithCitations(_FakeStore):
        def get_document_version_citations(self, *, document_version_id: int, server_id: str | None):
            assert document_version_id == 77
            assert server_id == "blackberry"
            return [{"id": 3, "canonical_ref": "law:1", "usage_type": "quote", "quoted_text": "text"}]

    monkeypatch.setattr("ogp_web.services.generated_document_trace_service.ValidationRepository", lambda backend: backend)
    monkeypatch.setattr("ogp_web.services.generated_document_trace_service.ValidationService", _FakeValidationService)
    monkeypatch.setattr("ogp_web.services.generated_document_trace_service.ArtifactRepository", _FakeArtifactRepository)
    monkeypatch.setattr(
        "ogp_web.services.generated_document_trace_service.build_store_provenance_service",
        lambda *, store: _FakeProvenanceService(),
    )

    payload = build_generated_document_review_context_payload(store=_FakeStoreWithCitations(), bundle=bundle)

    assert payload["generated_document"]["id"] == 100
    assert payload["document_version"]["id"] == 77
    assert payload["validation_summary"]["latest_status"] == "pass"
    assert payload["citations_summary"]["count"] == 1
    assert payload["artifact_summary"]["exports_count"] == 1
    assert payload["artifact_summary"]["attachments_count"] == 1
    assert payload["provenance"]["document_version_id"] == 77

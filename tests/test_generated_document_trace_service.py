from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.generated_document_trace_service import (
    parse_document_content_payload,
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

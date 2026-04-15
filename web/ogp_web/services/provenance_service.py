from __future__ import annotations

from ogp_web.services.generation_snapshot_schema_service import (
    extract_provenance_ai,
    extract_provenance_config,
)


class ProvenanceService:
    def __init__(self, *, document_repository, user_store, validation_service):
        self.document_repository = document_repository
        self.user_store = user_store
        self.validation_service = validation_service

    def get_document_version_trace(self, *, document_version_id: int) -> dict[str, Any] | None:
        version_row = self.document_repository.get_document_version(version_id=document_version_id)
        if not version_row:
            return None

        version_payload = dict(version_row)
        snapshot_id = int(version_payload.get("generation_snapshot_id") or 0)
        snapshot = self.user_store.get_generation_snapshot_by_id(snapshot_id) if snapshot_id > 0 else None
        citations = self.user_store.get_document_version_citations(
            document_version_id=document_version_id,
            server_id=str((snapshot or {}).get("server_code") or "").strip().lower() or None,
        )
        latest_validation = self.validation_service.get_latest_target_validation(
            target_type="document_version",
            target_id=int(document_version_id),
        )

        snapshot_payload = dict(snapshot or {})

        retrieval_run_id = None
        citation_ids: list[int] = []
        law_version_id = None
        if citations:
            citation_ids = [int(item["id"]) for item in citations if int(item.get("id") or 0) > 0]
            first = dict(citations[0])
            retrieval_run_id = int(first.get("retrieval_run_id") or 0) or None
            source_version_id = int(first.get("source_version_id") or 0) or None
            law_version_id = source_version_id

        return {
            "document_version_id": int(version_payload["id"]),
            "server_id": str(snapshot_payload.get("server_code") or ""),
            "document_kind": str(snapshot_payload.get("document_kind") or ""),
            "generation_timestamp": str(snapshot_payload.get("created_at") or ""),
            "generation_snapshot_id": int(snapshot_payload.get("id") or 0) or None,
            "config": extract_provenance_config(snapshot_payload, fallback_law_version_id=law_version_id),
            "ai": extract_provenance_ai(snapshot_payload),
            "retrieval": {
                "retrieval_run_id": retrieval_run_id,
                "citation_ids": citation_ids,
                "citations_count": len(citation_ids),
            },
            "validation": {
                "latest_run_id": int((latest_validation or {}).get("id") or 0) or None,
                "latest_status": str((latest_validation or {}).get("status") or ""),
            },
        }

    def get_latest_trace_for_generation_snapshot(self, *, generation_snapshot_id: int) -> dict[str, Any] | None:
        normalized_snapshot_id = int(generation_snapshot_id or 0)
        if normalized_snapshot_id <= 0:
            return None
        version_row = self.document_repository.get_latest_document_version_by_generation_snapshot_id(
            generation_snapshot_id=normalized_snapshot_id,
        )
        if not version_row:
            return None
        return self.get_document_version_trace(document_version_id=int(version_row["id"]))

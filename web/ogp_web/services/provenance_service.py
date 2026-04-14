from __future__ import annotations

from typing import Any


class ProvenanceService:
    def __init__(self, *, document_repository, user_store, validation_service):
        self.document_repository = document_repository
        self.user_store = user_store
        self.validation_service = validation_service

    @staticmethod
    def _as_dict(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _extract_config(snapshot: dict[str, Any], workflow: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        effective_versions = ProvenanceService._as_dict(context.get("effective_versions"))
        return {
            "server_config_version": str(snapshot.get("server_config_version") or ""),
            "procedure_version": str(workflow.get("procedure") or ProvenanceService._as_dict(context.get("content_workflow")).get("procedure") or ""),
            "template_version": str(workflow.get("template") or ProvenanceService._as_dict(context.get("content_workflow")).get("template") or ""),
            "law_set_version": str(snapshot.get("law_set_version") or ""),
            "law_version_id": effective_versions.get("law_version_id"),
        }

    @staticmethod
    def _extract_ai(workflow: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        ai = ProvenanceService._as_dict(context.get("ai"))
        content_workflow = ProvenanceService._as_dict(context.get("content_workflow"))
        return {
            "provider": str(ai.get("provider") or ""),
            "model_id": str(ai.get("model") or ""),
            "prompt_version": str(workflow.get("prompt_version") or content_workflow.get("prompt_version") or ""),
        }

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
        context_snapshot = self._as_dict(snapshot_payload.get("context_snapshot"))
        effective_config = self._as_dict(snapshot_payload.get("effective_config_snapshot"))
        workflow_ref = self._as_dict(snapshot_payload.get("content_workflow_ref"))

        retrieval_run_id = None
        citation_ids: list[int] = []
        law_version_id = None
        if citations:
            citation_ids = [int(item["id"]) for item in citations if int(item.get("id") or 0) > 0]
            first = dict(citations[0])
            retrieval_run_id = int(first.get("retrieval_run_id") or 0) or None
            source_version_id = int(first.get("source_version_id") or 0) or None
            law_version_id = source_version_id

        config = self._extract_config(effective_config, workflow_ref, context_snapshot)
        if law_version_id and not config.get("law_version_id"):
            config["law_version_id"] = law_version_id

        return {
            "document_version_id": int(version_payload["id"]),
            "server_id": str(snapshot_payload.get("server_code") or ""),
            "document_kind": str(snapshot_payload.get("document_kind") or ""),
            "generation_timestamp": str(snapshot_payload.get("created_at") or ""),
            "generation_snapshot_id": int(snapshot_payload.get("id") or 0) or None,
            "config": config,
            "ai": self._extract_ai(workflow_ref, context_snapshot),
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

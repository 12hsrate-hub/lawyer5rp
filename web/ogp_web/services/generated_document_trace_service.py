from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ogp_web.services.generation_snapshot_schema_service import build_snapshot_summary, build_workflow_linkage
from ogp_web.services.provenance_service import ProvenanceService
from ogp_web.services.validation_service import ValidationService
from ogp_web.storage.artifact_repository import ArtifactRepository
from ogp_web.storage.document_repository import DocumentRepository
from ogp_web.storage.validation_repository import ValidationRepository
from ogp_web.storage.user_store import UserStore


@dataclass(frozen=True)
class GeneratedDocumentTraceBundle:
    snapshot: dict[str, Any]
    generation_snapshot_id: int
    version_row: dict[str, Any]


def parse_document_content_payload(version_row: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(str(version_row.get("content_json") or "{}"))
    except json.JSONDecodeError:
        payload = {}
    return payload if isinstance(payload, dict) else {}


def _resolve_generation_snapshot_version_row(
    *,
    store: UserStore,
    snapshot: dict[str, Any] | None,
) -> GeneratedDocumentTraceBundle | None:
    if snapshot is None:
        return None
    snapshot_payload = dict(snapshot)
    generation_snapshot_id = int(snapshot_payload.get("generation_snapshot_id") or 0)
    if generation_snapshot_id <= 0:
        return None
    document_repository = DocumentRepository(store.backend)
    version_row = document_repository.get_latest_document_version_by_generation_snapshot_id(
        generation_snapshot_id=generation_snapshot_id,
    )
    if version_row is None:
        return None
    return GeneratedDocumentTraceBundle(
        snapshot=snapshot_payload,
        generation_snapshot_id=generation_snapshot_id,
        version_row=dict(version_row),
    )


def resolve_admin_generated_document_trace_bundle(
    *,
    store: UserStore,
    document_id: int,
) -> GeneratedDocumentTraceBundle | None:
    snapshot = store.get_generation_snapshot_by_generated_document_id(document_id=document_id)
    return _resolve_generation_snapshot_version_row(store=store, snapshot=snapshot)


def resolve_user_generated_document_trace_bundle(
    *,
    store: UserStore,
    username: str,
    legacy_generated_document_id: int,
) -> GeneratedDocumentTraceBundle | None:
    snapshot = store.get_generation_snapshot_by_generated_document_id_for_user(
        username=username,
        document_id=legacy_generated_document_id,
    )
    return _resolve_generation_snapshot_version_row(store=store, snapshot=snapshot)


def list_user_generated_document_history(
    *,
    store: UserStore,
    username: str,
    limit: int,
) -> list[dict[str, Any]]:
    return list(store.list_generation_snapshot_history_for_user(username=username, limit=limit))


def build_store_provenance_service(*, store: UserStore) -> ProvenanceService:
    validation_service = ValidationService(ValidationRepository(store.backend))
    return ProvenanceService(
        document_repository=DocumentRepository(store.backend),
        user_store=store,
        validation_service=validation_service,
    )


def resolve_generated_document_provenance_payload(
    *,
    store: UserStore,
    generation_snapshot_id: int,
) -> dict[str, Any] | None:
    return build_store_provenance_service(store=store).get_latest_trace_for_generation_snapshot(
        generation_snapshot_id=generation_snapshot_id,
    )


def build_generated_document_review_context_payload(
    *,
    store: UserStore,
    bundle: GeneratedDocumentTraceBundle,
) -> dict[str, Any]:
    snapshot_payload = dict(bundle.snapshot)
    generation_snapshot_id = int(bundle.generation_snapshot_id)
    version_row = dict(bundle.version_row)
    version_id = int(version_row["id"])
    content_payload = parse_document_content_payload(version_row)

    validation_service = ValidationService(ValidationRepository(store.backend))
    latest_validation = validation_service.get_latest_target_validation(
        target_type="document_version",
        target_id=version_id,
    )
    artifact_repository = ArtifactRepository(store.backend)
    citations = store.get_document_version_citations(
        document_version_id=version_id,
        server_id=str(snapshot_payload.get("server_code") or "").strip().lower() or None,
    )
    exports = artifact_repository.list_exports_for_document_version(document_version_id=version_id)
    attachments = artifact_repository.list_attachments_for_document_version(document_version_id=version_id)
    provenance = build_store_provenance_service(store=store).get_document_version_trace(document_version_id=version_id)

    bbcode_preview = str(content_payload.get("bbcode") or "").strip()
    if len(bbcode_preview) > 600:
        bbcode_preview = f"{bbcode_preview[:600].rstrip()}..."

    return {
        "generated_document": {
            "id": int(snapshot_payload["id"]),
            "generation_snapshot_id": generation_snapshot_id,
            "server_code": str(snapshot_payload.get("server_code") or ""),
            "document_kind": str(snapshot_payload.get("document_kind") or ""),
            "created_at": str(snapshot_payload.get("created_at") or ""),
        },
        "snapshot_summary": build_snapshot_summary(snapshot_payload),
        "document_version": {
            "id": version_id,
            "version_number": int(version_row.get("version_number") or 0),
            "bbcode_preview": bbcode_preview,
        },
        "validation_summary": {
            "latest_run_id": int((latest_validation or {}).get("id") or 0) or None,
            "latest_status": str((latest_validation or {}).get("status") or ""),
            "issues_count": len((latest_validation or {}).get("issues") or []),
            "issues": [
                {
                    "issue_code": str(item.get("issue_code") or ""),
                    "severity": str(item.get("severity") or ""),
                    "message": str(item.get("message") or ""),
                    "field_ref": str(item.get("field_ref") or ""),
                }
                for item in ((latest_validation or {}).get("issues") or [])[:5]
            ],
        },
        "workflow_linkage": build_workflow_linkage(
            snapshot_payload,
            document_version_id=version_id,
            generation_snapshot_id=generation_snapshot_id,
            latest_validation_run_id=int((latest_validation or {}).get("id") or 0) or None,
        ),
        "citations_summary": {
            "count": len(citations),
            "items": [
                {
                    "id": int(item.get("id") or 0),
                    "canonical_ref": str(item.get("canonical_ref") or ""),
                    "usage_type": str(item.get("usage_type") or ""),
                    "quoted_text": str(item.get("quoted_text") or ""),
                }
                for item in citations[:5]
            ],
        },
        "artifact_summary": {
            "exports_count": len(exports),
            "attachments_count": len(attachments),
            "exports": [
                {
                    "id": int(item.get("id") or 0),
                    "format": str(item.get("format") or ""),
                    "status": str(item.get("status") or ""),
                    "created_at": str(item.get("created_at") or ""),
                }
                for item in exports[:5]
            ],
            "attachments": [
                {
                    "id": int(item.get("id") or 0),
                    "filename": str(item.get("filename") or ""),
                    "upload_status": str(item.get("upload_status") or ""),
                    "link_type": str(item.get("link_type") or ""),
                }
                for item in attachments[:5]
            ],
        },
        "provenance": provenance,
    }

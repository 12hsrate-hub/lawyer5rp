from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status

from ogp_web.services.generation_snapshot_schema_service import build_snapshot_summary, build_workflow_linkage
from ogp_web.services.provenance_service import build_store_provenance_service
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


@dataclass(frozen=True)
class GeneratedDocumentReviewSupportData:
    content_payload: dict[str, Any]
    latest_validation: dict[str, Any] | None
    citations: list[dict[str, Any]]
    exports: list[dict[str, Any]]
    attachments: list[dict[str, Any]]
    provenance: dict[str, Any] | None


def parse_document_content_payload(version_row: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(str(version_row.get("content_json") or "{}"))
    except json.JSONDecodeError:
        payload = {}
    return payload if isinstance(payload, dict) else {}


def build_bbcode_preview(content_payload: dict[str, Any], *, max_length: int = 600) -> str:
    preview = str(content_payload.get("bbcode") or "").strip()
    if len(preview) > max_length:
        return f"{preview[:max_length].rstrip()}..."
    return preview


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


def require_admin_generated_document_trace_bundle(
    *,
    store: UserStore,
    document_id: int,
) -> GeneratedDocumentTraceBundle:
    bundle = resolve_admin_generated_document_trace_bundle(store=store, document_id=document_id)
    if bundle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Generated document not found."])
    return bundle


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


def require_user_generated_document_trace_bundle(
    *,
    store: UserStore,
    username: str,
    legacy_generated_document_id: int,
) -> GeneratedDocumentTraceBundle:
    bundle = resolve_user_generated_document_trace_bundle(
        store=store,
        username=username,
        legacy_generated_document_id=legacy_generated_document_id,
    )
    if bundle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Документ не найден."])
    return bundle


def list_user_generated_document_history(
    *,
    store: UserStore,
    username: str,
    limit: int,
) -> list[dict[str, Any]]:
    return list(store.list_generation_snapshot_history_for_user(username=username, limit=limit))


def resolve_generated_document_provenance_payload(
    *,
    store: UserStore,
    generation_snapshot_id: int,
    version_row: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    service = build_store_provenance_service(store=store)
    if version_row is not None:
        return service.get_document_version_trace_from_row(version_row=version_row)
    return service.get_latest_trace_for_generation_snapshot(
        generation_snapshot_id=generation_snapshot_id,
    )


def resolve_generated_document_provenance_payload_from_bundle(
    *,
    store: UserStore,
    bundle: GeneratedDocumentTraceBundle,
) -> dict[str, Any] | None:
    return resolve_generated_document_provenance_payload(
        store=store,
        generation_snapshot_id=bundle.generation_snapshot_id,
        version_row=bundle.version_row,
    )


def resolve_generated_document_review_support_data(
    *,
    store: UserStore,
    bundle: GeneratedDocumentTraceBundle,
) -> GeneratedDocumentReviewSupportData:
    snapshot_payload = dict(bundle.snapshot)
    version_row = dict(bundle.version_row)
    version_id = int(version_row["id"])
    content_payload = parse_document_content_payload(version_row)
    validation_service = ValidationService(ValidationRepository(store.backend))
    latest_validation = validation_service.get_latest_target_validation(
        target_type="document_version",
        target_id=version_id,
    )
    artifact_repository = ArtifactRepository(store.backend)
    citations = list(
        store.get_document_version_citations(
            document_version_id=version_id,
            server_id=str(snapshot_payload.get("server_code") or "").strip().lower() or None,
        )
    )
    exports = list(artifact_repository.list_exports_for_document_version(document_version_id=version_id))
    attachments = list(artifact_repository.list_attachments_for_document_version(document_version_id=version_id))
    provenance = build_store_provenance_service(store=store).get_document_version_trace_from_row(version_row=version_row)
    return GeneratedDocumentReviewSupportData(
        content_payload=content_payload,
        latest_validation=latest_validation,
        citations=citations,
        exports=exports,
        attachments=attachments,
        provenance=provenance,
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
    support_data = resolve_generated_document_review_support_data(store=store, bundle=bundle)

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
            "bbcode_preview": build_bbcode_preview(support_data.content_payload),
        },
        "validation_summary": {
            "latest_run_id": int((support_data.latest_validation or {}).get("id") or 0) or None,
            "latest_status": str((support_data.latest_validation or {}).get("status") or ""),
            "issues_count": len((support_data.latest_validation or {}).get("issues") or []),
            "issues": [
                {
                    "issue_code": str(item.get("issue_code") or ""),
                    "severity": str(item.get("severity") or ""),
                    "message": str(item.get("message") or ""),
                    "field_ref": str(item.get("field_ref") or ""),
                }
                for item in ((support_data.latest_validation or {}).get("issues") or [])[:5]
            ],
        },
        "workflow_linkage": build_workflow_linkage(
            snapshot_payload,
            document_version_id=version_id,
            generation_snapshot_id=generation_snapshot_id,
            latest_validation_run_id=int((support_data.latest_validation or {}).get("id") or 0) or None,
        ),
        "citations_summary": {
            "count": len(support_data.citations),
            "items": [
                {
                    "id": int(item.get("id") or 0),
                    "canonical_ref": str(item.get("canonical_ref") or ""),
                    "usage_type": str(item.get("usage_type") or ""),
                    "quoted_text": str(item.get("quoted_text") or ""),
                }
                for item in support_data.citations[:5]
            ],
        },
        "artifact_summary": {
            "exports_count": len(support_data.exports),
            "attachments_count": len(support_data.attachments),
            "exports": [
                {
                    "id": int(item.get("id") or 0),
                    "format": str(item.get("format") or ""),
                    "status": str(item.get("status") or ""),
                    "created_at": str(item.get("created_at") or ""),
                }
                for item in support_data.exports[:5]
            ],
            "attachments": [
                {
                    "id": int(item.get("id") or 0),
                    "filename": str(item.get("filename") or ""),
                    "upload_status": str(item.get("upload_status") or ""),
                    "link_type": str(item.get("link_type") or ""),
                }
                for item in support_data.attachments[:5]
            ],
        },
        "provenance": support_data.provenance,
    }


def resolve_generated_document_review_context_payload_from_bundle(
    *,
    store: UserStore,
    bundle: GeneratedDocumentTraceBundle,
) -> dict[str, Any]:
    return build_generated_document_review_context_payload(store=store, bundle=bundle)


def resolve_generated_document_snapshot_payload_from_bundle(
    *,
    store: UserStore,
    bundle: GeneratedDocumentTraceBundle,
) -> dict[str, Any]:
    provenance = resolve_generated_document_provenance_payload_from_bundle(store=store, bundle=bundle)
    return {
        **dict(bundle.snapshot),
        "provenance": provenance,
    }

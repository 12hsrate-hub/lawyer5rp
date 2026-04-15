from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ogp_web.services.generation_orchestrator import GenerationOrchestrator
from ogp_web.storage.document_repository import DocumentRepository
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
    snapshot = GenerationOrchestrator(store).get_snapshot_by_legacy_id(
        username=username,
        legacy_generated_document_id=legacy_generated_document_id,
    )
    return _resolve_generation_snapshot_version_row(store=store, snapshot=snapshot)

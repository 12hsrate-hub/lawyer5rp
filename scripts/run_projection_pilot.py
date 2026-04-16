#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, UTC
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    candidate_text = str(candidate)
    if candidate_text not in sys.path:
        sys.path.insert(0, candidate_text)

from ogp_web.db.factory import get_database_backend
from ogp_web.env import load_web_env
from ogp_web.services.admin_canonical_law_document_fetch_service import fetch_discovery_run_document_versions_payload
from ogp_web.services.admin_canonical_law_document_parse_service import parse_discovery_run_document_versions_payload
from ogp_web.services.admin_canonical_law_document_versions_service import ingest_discovery_run_document_versions_payload
from ogp_web.services.admin_canonical_law_documents_service import ingest_discovery_run_documents_payload
from ogp_web.services.admin_law_source_discovery_service import execute_source_set_discovery_payload
from ogp_web.services.admin_law_projection_service import (
    activate_server_effective_law_projection_payload,
    decide_server_effective_law_projection_payload,
    get_server_effective_law_projection_status_payload,
    materialize_server_effective_law_projection_payload,
    preview_server_effective_law_projection_payload,
)
from ogp_web.services.admin_law_sets_service import resolve_law_set_rollback_context
from ogp_web.services.admin_law_sources_service import (
    backfill_law_sources_source_set_payload,
    build_law_sources_status_payload,
)
from ogp_web.services.admin_runtime_servers_service import build_runtime_server_health_payload
from ogp_web.services.content_workflow_service import ContentWorkflowService
from ogp_web.services.law_admin_service import LawAdminService
from ogp_web.services.law_version_service import resolve_active_law_version
from ogp_web.storage.canonical_law_documents_store import CanonicalLawDocumentsStore
from ogp_web.storage.content_workflow_repository import ContentWorkflowRepository
from ogp_web.storage.canonical_law_document_versions_store import CanonicalLawDocumentVersionsStore
from ogp_web.storage.law_source_discovery_store import LawSourceDiscoveryStore
from ogp_web.storage.law_source_sets_store import LawSourceSetsStore
from ogp_web.storage.runtime_law_sets_store import RuntimeLawSetsStore
from ogp_web.storage.runtime_servers_store import RuntimeServersStore
from ogp_web.storage.server_effective_law_projections_store import ServerEffectiveLawProjectionsStore


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run projection preview/approve/materialize/activate pilot for a server.")
    parser.add_argument("--server", default="orange", help="Runtime server code")
    parser.add_argument("--actor-user-id", type=int, default=1, help="Actor user id for rebuild audit writes")
    parser.add_argument("--activated-by", default="github_actions:projection_pilot", help="Human-readable activation actor label")
    parser.add_argument("--decision-reason", default="pilot_projection_runtime_cutover", help="Approval reason")
    parser.add_argument("--env-file", default=None, help="Optional path to a runtime .env file to load before database access")
    return parser.parse_args()


def run_projection_pilot(
    *,
    server_code: str,
    actor_user_id: int,
    activated_by: str,
    decision_reason: str,
    env_file: str | None = None,
) -> dict[str, object]:
    normalized_server = str(server_code or "").strip().lower()
    if not normalized_server:
        raise ValueError("server_code_required")

    load_web_env(env_file)
    backend = get_database_backend()
    source_sets_store = LawSourceSetsStore(backend)
    discovery_store = LawSourceDiscoveryStore(backend)
    documents_store = CanonicalLawDocumentsStore(backend)
    versions_store = CanonicalLawDocumentVersionsStore(backend)
    projections_store = ServerEffectiveLawProjectionsStore(backend)
    runtime_law_sets_store = RuntimeLawSetsStore(backend)
    runtime_servers_store = RuntimeServersStore(backend)
    workflow_service = ContentWorkflowService(ContentWorkflowRepository(backend), legacy_store=None)
    law_admin_service = LawAdminService(workflow_service)

    request_id = f"projection-pilot:{normalized_server}:{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    before_active = resolve_active_law_version(server_code=normalized_server)
    bootstrap = backfill_law_sources_source_set_payload(
        workflow_service=workflow_service,
        source_sets_store=source_sets_store,
        server_code=normalized_server,
        actor_user_id=int(actor_user_id),
        request_id=request_id,
    )
    source_set_key = str(bootstrap.get("source_set_key") or "").strip().lower()
    if not source_set_key:
        raise ValueError("server_source_set_backfill_missing_key")
    discovery = execute_source_set_discovery_payload(
        source_sets_store=source_sets_store,
        discovery_store=discovery_store,
        source_set_key=source_set_key,
        trigger_mode="backfill",
        safe_rerun=True,
    )
    discovery_run_id = int((discovery.get("run") or {}).get("id") or 0)
    if discovery_run_id <= 0:
        raise ValueError("source_discovery_run_missing")
    documents = ingest_discovery_run_documents_payload(
        discovery_store=discovery_store,
        documents_store=documents_store,
        run_id=discovery_run_id,
        safe_rerun=True,
    )
    seeded_versions = ingest_discovery_run_document_versions_payload(
        discovery_store=discovery_store,
        documents_store=documents_store,
        versions_store=versions_store,
        run_id=discovery_run_id,
        safe_rerun=True,
    )
    fetched_versions = fetch_discovery_run_document_versions_payload(
        discovery_store=discovery_store,
        versions_store=versions_store,
        run_id=discovery_run_id,
        safe_rerun=True,
    )
    parsed_versions = parse_discovery_run_document_versions_payload(
        discovery_store=discovery_store,
        versions_store=versions_store,
        run_id=discovery_run_id,
        safe_rerun=True,
    )

    preview = preview_server_effective_law_projection_payload(
        source_sets_store=source_sets_store,
        versions_store=versions_store,
        projections_store=projections_store,
        server_code=normalized_server,
        trigger_mode="manual",
        safe_rerun=True,
    )
    run_id = int((preview.get("run") or {}).get("id") or 0)
    if run_id <= 0:
        raise ValueError("server_effective_law_projection_run_missing")

    approved = decide_server_effective_law_projection_payload(
        projections_store=projections_store,
        run_id=run_id,
        status="approved",
        decided_by=activated_by,
        reason=decision_reason,
    )
    materialized = materialize_server_effective_law_projection_payload(
        projections_store=projections_store,
        runtime_law_sets_store=runtime_law_sets_store,
        run_id=run_id,
        materialized_by=activated_by,
        safe_rerun=True,
    )
    activated = activate_server_effective_law_projection_payload(
        projections_store=projections_store,
        runtime_law_sets_store=runtime_law_sets_store,
        versions_store=versions_store,
        law_admin_service=law_admin_service,
        run_id=run_id,
        actor_user_id=int(actor_user_id),
        request_id=request_id,
        activated_by=activated_by,
        safe_rerun=True,
    )

    after_active = resolve_active_law_version(server_code=normalized_server)
    status_payload = get_server_effective_law_projection_status_payload(
        projections_store=projections_store,
        runtime_law_sets_store=runtime_law_sets_store,
        active_law_version=after_active,
        run_id=run_id,
    )
    health_payload = build_runtime_server_health_payload(
        server_code=normalized_server,
        runtime_servers_store=runtime_servers_store,
        law_sets_store=runtime_law_sets_store,
        projections_store=projections_store,
    )
    law_sources_status = build_law_sources_status_payload(
        workflow_service=workflow_service,
        server_code=normalized_server,
        projections_store=projections_store,
    )

    rollback_context = None
    law_set_id = int((status_payload.get("materialization") or {}).get("law_set_id") or 0)
    if law_set_id > 0:
        rollback_context = resolve_law_set_rollback_context(
            store=runtime_law_sets_store,
            law_set_id=law_set_id,
        )

    return {
        "ok": True,
        "server_code": normalized_server,
        "request_id": request_id,
        "before_active_law_version_id": int(before_active.id) if before_active else None,
        "after_active_law_version_id": int(after_active.id) if after_active else None,
        "bootstrap": bootstrap,
        "discovery": discovery,
        "documents": documents,
        "seeded_versions": seeded_versions,
        "fetched_versions": fetched_versions,
        "parsed_versions": parsed_versions,
        "preview": preview,
        "approved": approved,
        "materialized": materialized,
        "activated": activated,
        "status": status_payload,
        "health": health_payload,
        "law_sources_status": law_sources_status,
        "rollback_context": rollback_context,
    }


def main() -> int:
    args = _parse_args()
    result = run_projection_pilot(
        server_code=args.server,
        actor_user_id=args.actor_user_id,
        activated_by=str(args.activated_by or "").strip(),
        decision_reason=str(args.decision_reason or "").strip(),
        env_file=str(args.env_file or "").strip() or None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

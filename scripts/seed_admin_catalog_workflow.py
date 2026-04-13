#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.db.factory import get_database_backend
from ogp_web.env import load_web_env
from ogp_web.services.content_workflow_service import ContentWorkflowService
from ogp_web.storage.content_workflow_repository import ContentWorkflowRepository
from ogp_web.storage.user_store import get_default_user_store


SEED_ITEMS: dict[str, list[dict[str, object]]] = {
    "servers": [
        {
            "key": "blackberry_core",
            "title": "Blackberry core server",
            "config": {
                "code": "blackberry",
                "label": "Blackberry",
                "app_title": "OGP Builder Web",
                "is_active": True,
                "notes": "Primary production server profile for admin workflow.",
            },
        },
    ],
    "laws": [
        {
            "key": "complaint_law_index",
            "title": "Complaint law index",
            "config": {
                "bundle": "complaint_base",
                "document_kind": "complaint",
                "sources": [
                    "procedural_code",
                    "administrative_code",
                    "advocate_rules",
                ],
                "notes": "Base legal corpus used by complaint generation and law QA.",
            },
        },
        {
            "key": "rehab_law_index",
            "title": "Rehabilitation law index",
            "config": {
                "bundle": "rehab_base",
                "document_kind": "rehab",
                "sources": [
                    "rehabilitation_rules",
                    "appeal_rules",
                ],
                "notes": "Initial legal corpus for rehabilitation documents.",
            },
        },
    ],
    "templates": [
        {
            "key": "complaint_template_v1",
            "title": "Complaint template v1",
            "config": {
                "document_kind": "complaint",
                "template_family": "base",
                "status": "active",
                "notes": "Starter versioned complaint template.",
            },
        },
        {
            "key": "rehab_template_v1",
            "title": "Rehabilitation template v1",
            "config": {
                "document_kind": "rehab",
                "template_family": "base",
                "status": "active",
                "notes": "Starter versioned rehabilitation template.",
            },
        },
    ],
    "features": [
        {
            "key": "admin_catalog_workflow",
            "title": "Admin catalog workflow",
            "config": {
                "enabled": True,
                "rollout": "admin_only",
                "owner": "admin",
                "notes": "Controls CRUD + publish workflow for catalog entities.",
            },
        },
        {
            "key": "law_qa_retrieval",
            "title": "Law QA retrieval",
            "config": {
                "enabled": True,
                "rollout": "server_default",
                "owner": "legal_ai",
                "notes": "Initial retrieval feature toggle for legal answers.",
            },
        },
    ],
    "rules": [
        {
            "key": "publication_workflow_v1",
            "title": "Publication workflow v1",
            "config": {
                "states": ["draft", "in_review", "approved", "published", "rolled_back"],
                "transitions": {
                    "draft": ["in_review"],
                    "in_review": ["approved", "draft", "rejected"],
                    "approved": ["published"],
                    "published": ["rolled_back"],
                },
                "notes": "Base publication workflow for versioned admin catalog.",
            },
        },
        {
            "key": "admin_editing_policy",
            "title": "Admin editing policy",
            "config": {
                "require_review_before_publish": True,
                "allow_delete": False,
                "audit_required": True,
                "notes": "Starter governance rules for catalog changes.",
            },
        },
    ],
}


def _resolve_actor_user_id() -> int:
    user_store = get_default_user_store()
    for username in ("admin", "system"):
        actor_user_id = user_store.get_user_id(username)
        if actor_user_id is not None:
            return int(actor_user_id)
    return 1


def seed(*, server_scope: str = "server", server_id: str = "blackberry", safe_rerun: bool = True) -> dict[str, object]:
    load_web_env()
    backend = get_database_backend()
    repository = ContentWorkflowRepository(backend)
    service = ContentWorkflowService(repository, legacy_store=None)
    actor_user_id = _resolve_actor_user_id()

    created: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []

    for entity_type, items in SEED_ITEMS.items():
        for item in items:
            content_key = str(item["key"])
            existing = repository.get_content_item_by_identity(
                server_scope=server_scope,
                server_id=server_id if server_scope == "server" else None,
                content_type=entity_type,
                content_key=content_key,
            )
            existing_versions = (
                repository.list_content_versions(content_item_id=int(existing["id"]))
                if existing
                else []
            )
            is_fully_seeded = bool(existing and existing.get("current_published_version_id") and existing_versions)
            if existing and safe_rerun and is_fully_seeded:
                skipped.append({"entity_type": entity_type, "key": content_key, "id": existing.get("id")})
                continue

            created_item = existing or service.create_content_item(
                server_scope=server_scope,
                server_id=server_id if server_scope == "server" else None,
                content_type=entity_type,
                content_key=content_key,
                title=str(item["title"]),
                metadata_json={"seed": True, "seed_key": content_key},
                actor_user_id=actor_user_id,
                request_id="seed-admin-catalog",
            )
            result = service.create_draft_version(
                content_item_id=int(created_item["id"]),
                payload_json=dict(item["config"]),
                schema_version=1,
                actor_user_id=actor_user_id,
                request_id="seed-admin-catalog",
                server_scope=server_scope,
                server_id=server_id if server_scope == "server" else None,
                comment="initial seed",
            )
            submitted = service.submit_change_request(
                change_request_id=int(result["change_request"]["id"]),
                actor_user_id=actor_user_id,
                request_id="seed-admin-catalog",
                server_scope=server_scope,
                server_id=server_id if server_scope == "server" else None,
            )
            service.review_change_request(
                change_request_id=int(submitted["id"]),
                reviewer_user_id=actor_user_id,
                decision="approve",
                comment="initial seed auto-approve",
                diff_json={"seed": True},
                request_id="seed-admin-catalog",
                server_scope=server_scope,
                server_id=server_id if server_scope == "server" else None,
            )
            published = service.publish_change_request(
                change_request_id=int(submitted["id"]),
                actor_user_id=actor_user_id,
                request_id="seed-admin-catalog",
                summary_json={"seed": "admin_catalog_workflow"},
                server_scope=server_scope,
                server_id=server_id if server_scope == "server" else None,
            )
            created.append(
                {
                    "entity_type": entity_type,
                    "key": content_key,
                    "id": created_item.get("id"),
                    "publish_batch_id": published["batch"]["id"],
                }
            )

    return {
        "server_scope": server_scope,
        "server_id": server_id if server_scope == "server" else None,
        "created_count": len(created),
        "skipped_count": len(skipped),
        "created": created,
        "skipped": skipped,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed initial admin catalog content into DB-backed workflow")
    parser.add_argument("--server-scope", choices=["server", "global"], default="server")
    parser.add_argument("--server-id", default="blackberry")
    parser.add_argument("--no-safe-rerun", action="store_true")
    args = parser.parse_args()

    summary = seed(
        server_scope=args.server_scope,
        server_id=args.server_id,
        safe_rerun=not args.no_safe_rerun,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

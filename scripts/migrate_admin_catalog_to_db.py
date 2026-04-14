from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.db.factory import get_database_backend
from ogp_web.services.content_contracts import (
    CANONICAL_CONTENT_TYPES,
    normalize_content_type,
    validate_payload_contract,
)
from ogp_web.services.content_workflow_service import ContentWorkflowService
from ogp_web.storage.admin_catalog_store import AdminCatalogStore
from ogp_web.storage.content_workflow_repository import ContentWorkflowRepository


def get_user_store_for_migration():
    from ogp_web.storage.user_store import get_default_user_store

    return get_default_user_store()


def _build_canonical_payload(*, canonical_type: str, content_key: str, title: str, config: dict[str, Any]) -> dict[str, Any]:
    payload = dict(config or {})
    payload.setdefault("title", title)

    if canonical_type == "procedures":
        payload.setdefault("procedure_code", content_key)
        payload.setdefault("steps", [])
    elif canonical_type == "bb_catalogs":
        payload.setdefault("catalog_code", content_key)
        payload.setdefault("entries", [])
    elif canonical_type == "forms":
        payload.setdefault("form_code", content_key)
        payload.setdefault("fields", [])
    elif canonical_type == "validation_rules":
        payload.setdefault("rule_code", content_key)
        payload.setdefault("ruleset", {})
    elif canonical_type == "templates":
        payload.setdefault("template_code", content_key)
        payload.setdefault("body", "")
    elif canonical_type == "features":
        payload.setdefault("feature_code", content_key)
        payload.setdefault("enabled", False)

    return payload


def migrate(*, dry_run: bool = False, safe_rerun: bool = True, server_scope: str = "server", server_id: str = "blackberry") -> dict[str, Any]:
    legacy_store = AdminCatalogStore()
    backend = get_database_backend()
    repository = ContentWorkflowRepository(backend)
    service = ContentWorkflowService(repository, legacy_store=legacy_store)
    user_store = get_user_store_for_migration()
    actor_user_id = user_store.get_user_id("admin") or user_store.get_user_id("system") or 1

    migrated_items = 0
    migrated_versions = 0
    skipped = 0
    errors = 0
    total_entities = 0
    compatible_entities = 0
    incompatible_records: list[dict[str, Any]] = []
    per_type_totals = {content_type: 0 for content_type in CANONICAL_CONTENT_TYPES}
    per_type_migrated = {content_type: 0 for content_type in CANONICAL_CONTENT_TYPES}

    for legacy_entity_type, item in legacy_store.iter_legacy_items():
        total_entities += 1
        try:
            canonical_type = normalize_content_type(legacy_entity_type, allow_legacy_import_alias=True)
            per_type_totals[canonical_type] += 1
            content_key = str(item.get("id") or item.get("title") or "").strip().lower().replace(" ", "_")
            title = str(item.get("title") or "Untitled")
            if not content_key:
                incompatible_records.append({"legacy_entity_type": legacy_entity_type, "reason": "missing_content_key", "item": item})
                skipped += 1
                continue
            canonical_payload = _build_canonical_payload(
                canonical_type=canonical_type,
                content_key=content_key,
                title=title,
                config=item.get("config") if isinstance(item.get("config"), dict) else {},
            )
            validation = validate_payload_contract(content_type=canonical_type, payload_json=canonical_payload)
            if not validation.ok:
                incompatible_records.append(
                    {
                        "legacy_entity_type": legacy_entity_type,
                        "canonical_type": canonical_type,
                        "content_key": content_key,
                        "reasons": list(validation.errors),
                    }
                )
                skipped += 1
                continue

            compatible_entities += 1
            existing = repository.get_content_item_by_identity(
                server_scope=server_scope,
                server_id=server_id if server_scope == "server" else None,
                content_type=canonical_type,
                content_key=content_key,
            )
            if existing and safe_rerun:
                skipped += 1
                continue
            if dry_run:
                migrated_items += 1
                migrated_versions += 1
                per_type_migrated[canonical_type] += 1
                continue

            created_item = existing or service.create_content_item(
                server_scope=server_scope,
                server_id=server_id if server_scope == "server" else None,
                content_type=canonical_type,
                content_key=content_key,
                title=title,
                metadata_json={"legacy_import": True, "legacy_entity_type": legacy_entity_type},
                actor_user_id=int(actor_user_id),
                request_id="migration-script",
            )
            result = service.create_draft_version(
                content_item_id=int(created_item["id"]),
                payload_json=canonical_payload,
                schema_version=1,
                actor_user_id=int(actor_user_id),
                request_id="migration-script",
                server_scope=server_scope,
                server_id=server_id if server_scope == "server" else None,
                comment="legacy import",
            )
            cr = service.submit_change_request(
                change_request_id=int(result["change_request"]["id"]),
                actor_user_id=int(actor_user_id),
                request_id="migration-script",
                server_scope=server_scope,
                server_id=server_id if server_scope == "server" else None,
            )
            service.review_change_request(
                change_request_id=int(cr["id"]),
                reviewer_user_id=int(actor_user_id),
                decision="approve",
                comment="legacy import auto-approve",
                diff_json={"import": True},
                request_id="migration-script",
                server_scope=server_scope,
                server_id=server_id if server_scope == "server" else None,
            )
            service.publish_change_request(
                change_request_id=int(cr["id"]),
                actor_user_id=int(actor_user_id),
                request_id="migration-script",
                summary_json={"migration": "legacy_admin_catalog"},
                server_scope=server_scope,
                server_id=server_id if server_scope == "server" else None,
            )
            migrated_items += 1
            migrated_versions += 1
            per_type_migrated[canonical_type] += 1
        except Exception as exc:  # noqa: BLE001
            errors += 1
            incompatible_records.append({"legacy_entity_type": legacy_entity_type, "reason": str(exc), "item": item})
            print(f"[error] failed to migrate entity={legacy_entity_type}: {exc}")

    compatible_coverage_pct = round((compatible_entities / total_entities) * 100, 2) if total_entities else 0.0
    migrated_coverage_pct = round((migrated_items / total_entities) * 100, 2) if total_entities else 0.0
    return {
        "migrated_items": migrated_items,
        "migrated_versions": migrated_versions,
        "skipped": skipped,
        "errors": errors,
        "report": {
            "total_entities": total_entities,
            "compatible_entities": compatible_entities,
            "compatible_coverage_pct": compatible_coverage_pct,
            "migrated_coverage_pct": migrated_coverage_pct,
            "per_type_totals": per_type_totals,
            "per_type_migrated": per_type_migrated,
            "incompatible_records": incompatible_records,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate legacy admin catalog into DB content workflow")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-safe-rerun", action="store_true")
    parser.add_argument("--server-scope", choices=["server", "global"], default="server")
    parser.add_argument("--server-id", default="blackberry")
    args = parser.parse_args()

    summary = migrate(
        dry_run=args.dry_run,
        safe_rerun=not args.no_safe_rerun,
        server_scope=args.server_scope,
        server_id=args.server_id,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

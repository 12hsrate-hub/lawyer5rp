from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ogp_web.services.content_workflow_service import ContentWorkflowService
from ogp_web.services.law_bundle_service import (
    build_law_bundle,
    load_law_bundle_meta,
    resolve_law_bundle_path,
    write_law_bundle,
)
from ogp_web.services.server_context_service import (
    extract_server_identity_settings,
    list_servers_with_law_qa_context,
    resolve_server_config,
    resolve_server_law_bundle_path,
    resolve_server_law_sources,
)
from ogp_web.services.law_version_service import (
    import_law_snapshot,
    list_recent_law_versions,
    resolve_active_law_version,
)
from ogp_web.services.law_sources_dependencies import build_sources_dependency_payload
from ogp_web.services.law_sources_validation import (
    build_invalid_source_urls_error,
    normalize_source_urls,
    validate_source_urls,
)


LAW_SOURCES_CONTENT_TYPE = "laws"
LAW_SOURCES_CONTENT_KEY = "law_sources_manifest"


@dataclass(frozen=True)
class LawSourcesSnapshot:
    server_code: str
    source_urls: tuple[str, ...]
    source_origin: str
    manifest_item: dict[str, Any] | None
    manifest_version: dict[str, Any] | None
    active_law_version: dict[str, Any] | None
    bundle_meta: dict[str, Any] | None


class LawAdminService:
    def __init__(self, workflow_service: ContentWorkflowService):
        self.workflow_service = workflow_service
        self.repository = workflow_service.repository

    def get_effective_sources(self, *, server_code: str) -> LawSourcesSnapshot:
        manifest_item = self.repository.get_content_item_by_identity(
            server_scope="server",
            server_id=server_code,
            content_type=LAW_SOURCES_CONTENT_TYPE,
            content_key=LAW_SOURCES_CONTENT_KEY,
        )
        manifest_version: dict[str, Any] | None = None
        source_urls: tuple[str, ...] = ()
        source_origin = "server_config"

        if manifest_item and manifest_item.get("current_published_version_id"):
            manifest_version = self.repository.get_content_version(
                version_id=int(manifest_item["current_published_version_id"])
            )
            payload_json = manifest_version.get("payload_json") if manifest_version else {}
            if isinstance(payload_json, dict):
                source_urls = normalize_source_urls(payload_json.get("source_urls") or [])
                if source_urls:
                    source_origin = "content_workflow"

        if not source_urls:
            source_urls = resolve_server_law_sources(server_code=server_code)

        active_version = resolve_active_law_version(server_code=server_code)
        bundle_meta = load_law_bundle_meta(
            server_code,
            resolve_server_law_bundle_path(server_code=server_code),
        )

        return LawSourcesSnapshot(
            server_code=server_code,
            source_urls=source_urls,
            source_origin=source_origin,
            manifest_item=manifest_item,
            manifest_version=manifest_version,
            active_law_version=active_version.__dict__ if active_version else None,
            bundle_meta=bundle_meta.__dict__ if bundle_meta else None,
        )

    def sync_sources_manifest_from_server_config(
        self,
        *,
        server_code: str,
        actor_user_id: int,
        request_id: str,
        safe_rerun: bool = True,
    ) -> dict[str, Any]:
        source_urls = resolve_server_law_sources(server_code=server_code)
        if not source_urls:
            raise ValueError("server_has_no_law_qa_sources")
        snapshot = self.get_effective_sources(server_code=server_code)
        if safe_rerun and snapshot.source_origin == "content_workflow" and snapshot.source_urls == source_urls:
            return {
                "ok": True,
                "changed": False,
                "source_urls": list(source_urls),
                "manifest_item_id": snapshot.manifest_item.get("id") if snapshot.manifest_item else None,
            }
        return self.publish_sources_manifest(
            server_code=server_code,
            source_urls=list(source_urls),
            actor_user_id=actor_user_id,
            request_id=request_id,
            comment="sync_from_server_config",
        )

    def publish_sources_manifest(
        self,
        *,
        server_code: str,
        source_urls: list[str],
        actor_user_id: int,
        request_id: str,
        comment: str = "",
    ) -> dict[str, Any]:
        validation = validate_source_urls(source_urls)
        normalized_urls = validation.accepted_urls
        if not normalized_urls:
            raise ValueError("source_urls_required")
        if validation.invalid_urls:
            raise ValueError(build_invalid_source_urls_error(validation))

        item = self.repository.get_content_item_by_identity(
            server_scope="server",
            server_id=server_code,
            content_type=LAW_SOURCES_CONTENT_TYPE,
            content_key=LAW_SOURCES_CONTENT_KEY,
        )
        if not item:
            item = self.workflow_service.create_content_item(
                server_scope="server",
                server_id=server_code,
                content_type=LAW_SOURCES_CONTENT_TYPE,
                content_key=LAW_SOURCES_CONTENT_KEY,
                title="Law sources manifest",
                metadata_json={"managed_by": "law_admin_service"},
                actor_user_id=actor_user_id,
                request_id=request_id,
            )

        payload_json = {
            "key": LAW_SOURCES_CONTENT_KEY,
            "server_code": server_code,
            "source_urls": list(normalized_urls),
            "status": "published",
        }
        result = self.workflow_service.create_draft_version(
            content_item_id=int(item["id"]),
            payload_json=payload_json,
            schema_version=1,
            actor_user_id=actor_user_id,
            request_id=request_id,
            server_scope="server",
            server_id=server_code,
            comment=comment or "law_sources_update",
        )
        submitted = self.workflow_service.submit_change_request(
            change_request_id=int(result["change_request"]["id"]),
            actor_user_id=actor_user_id,
            request_id=request_id,
            server_scope="server",
            server_id=server_code,
        )
        self.workflow_service.review_change_request(
            change_request_id=int(submitted["id"]),
            reviewer_user_id=actor_user_id,
            decision="approve",
            comment="law_sources_auto_approve",
            diff_json={"source_urls_count": len(normalized_urls)},
            request_id=request_id,
            server_scope="server",
            server_id=server_code,
        )
        published = self.workflow_service.publish_change_request(
            change_request_id=int(submitted["id"]),
            actor_user_id=actor_user_id,
            request_id=request_id,
            summary_json={"source": "law_admin_service"},
            server_scope="server",
            server_id=server_code,
        )
        return {
            "ok": True,
            "changed": True,
            "source_urls": list(normalized_urls),
            "manifest_item_id": item["id"],
            "publish_batch_id": published["batch"]["id"],
        }

    def rebuild_index(
        self,
        *,
        server_code: str,
        source_urls: list[str] | None = None,
        actor_user_id: int,
        request_id: str,
        persist_sources: bool = True,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        validation = validate_source_urls(source_urls or list(self.get_effective_sources(server_code=server_code).source_urls))
        effective_urls = validation.accepted_urls
        if not effective_urls:
            raise ValueError("source_urls_required")
        if validation.invalid_urls:
            raise ValueError(build_invalid_source_urls_error(validation))

        manifest_result = None
        if persist_sources:
            manifest_result = self.publish_sources_manifest(
                server_code=server_code,
                source_urls=list(effective_urls),
                actor_user_id=actor_user_id,
                request_id=request_id,
                comment="law_index_rebuild",
            )

        bundle = build_law_bundle(server_code, effective_urls)
        if dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "server_code": server_code,
                "source_urls": list(effective_urls),
                "source_count": len(bundle.get("sources", []) if isinstance(bundle, dict) else []),
                "article_count": len(bundle.get("articles", []) if isinstance(bundle, dict) else []),
                "manifest": manifest_result,
            }
        bundle_path = resolve_law_bundle_path(server_code, resolve_server_law_bundle_path(server_code=server_code))
        write_law_bundle(bundle, bundle_path)
        version_id = import_law_snapshot(
            server_code=server_code,
            payload=bundle,
            source_ref=str(bundle_path),
        )
        return {
            "ok": True,
            "server_code": server_code,
            "source_urls": list(effective_urls),
            "bundle_path": str(bundle_path),
            "source_count": len(bundle.get("sources", []) if isinstance(bundle, dict) else []),
            "article_count": len(bundle.get("articles", []) if isinstance(bundle, dict) else []),
            "law_version_id": version_id,
            "manifest": manifest_result,
        }

    def preview_sources(
        self,
        *,
        source_urls: list[str],
    ) -> dict[str, Any]:
        validation = validate_source_urls(source_urls)
        return {
            "ok": True,
            "accepted_urls": list(validation.accepted_urls),
            "invalid_urls": list(validation.invalid_urls),
            "invalid_details": list(validation.invalid_details),
            "duplicate_count": validation.duplicate_count,
            "duplicate_urls": list(validation.duplicate_urls),
            "accepted_count": len(validation.accepted_urls),
            "invalid_count": len(validation.invalid_urls),
        }
    def list_recent_versions(self, *, server_code: str, limit: int = 10) -> dict[str, Any]:
        rows = list_recent_law_versions(server_code=server_code, limit=limit)
        return {
            "ok": True,
            "items": [row.__dict__ for row in rows],
            "count": len(rows),
        }

    def describe_sources_dependencies(self) -> dict[str, Any]:
        server_rows: list[dict[str, Any]] = []
        for item in list_servers_with_law_qa_context():
            snapshot = self.get_effective_sources(server_code=item["code"])
            server_rows.append(
                {
                    "server_code": item["code"],
                    "server_name": item["name"],
                    "source_origin": snapshot.source_origin,
                    "source_urls": list(snapshot.source_urls),
                    "active_law_version_id": (snapshot.active_law_version or {}).get("id") if isinstance(snapshot.active_law_version, dict) else None,
                }
            )
        return build_sources_dependency_payload(server_rows)

    def rollback_active_version(self, *, server_code: str, law_version_id: int | None = None) -> dict[str, Any]:
        rows = list_recent_law_versions(server_code=server_code, limit=20)
        if not rows:
            raise ValueError("law_versions_not_found")
        target = None
        if law_version_id is not None:
            target = next((row for row in rows if int(row.id) == int(law_version_id)), None)
            if target is None:
                raise ValueError("law_version_not_found")
        else:
            if len(rows) < 2:
                raise ValueError("rollback_target_not_found")
            target = rows[1]
        assert target is not None
        conn = self.repository.backend.connect()
        try:
            conn.execute(
                """
                UPDATE law_versions
                SET effective_to = NOW()
                WHERE server_code = %s AND id <> %s AND effective_to IS NULL
                """,
                (server_code, int(target.id)),
            )
            conn.execute(
                """
                UPDATE law_versions
                SET effective_from = NOW(), effective_to = NULL
                WHERE id = %s AND server_code = %s
                """,
                (int(target.id), server_code),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        active = resolve_active_law_version(server_code=server_code)
        return {
            "ok": True,
            "server_code": server_code,
            "rolled_back_to_version_id": int(target.id),
            "active_law_version_id": int(active.id) if active else None,
        }

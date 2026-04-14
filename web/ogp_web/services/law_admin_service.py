from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from ogp_web.server_config import get_server_config
from ogp_web.services.content_workflow_service import ContentWorkflowService
from ogp_web.services.law_bundle_service import (
    build_law_bundle,
    load_law_bundle_meta,
    resolve_law_bundle_path,
    write_law_bundle,
)
from ogp_web.services.law_version_service import import_law_snapshot, resolve_active_law_version


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


@dataclass(frozen=True)
class LawSourcesValidation:
    normalized_urls: tuple[str, ...]
    accepted_urls: tuple[str, ...]
    invalid_urls: tuple[str, ...]
    duplicate_count: int


def normalize_source_urls(source_urls: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in source_urls:
        value = str(raw or "").strip()
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return tuple(normalized)


def is_valid_source_url(value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return False
    return bool(parsed.netloc)


def validate_source_urls(source_urls: list[str] | tuple[str, ...]) -> LawSourcesValidation:
    normalized = normalize_source_urls(source_urls)
    accepted: list[str] = []
    invalid: list[str] = []
    seen: set[str] = set()
    duplicate_count = 0

    for raw in source_urls:
        value = str(raw or "").strip()
        if not value:
            continue
        if value in seen:
            duplicate_count += 1
            continue
        seen.add(value)
        if is_valid_source_url(value):
            accepted.append(value)
        else:
            invalid.append(value)

    return LawSourcesValidation(
        normalized_urls=normalized,
        accepted_urls=tuple(accepted),
        invalid_urls=tuple(invalid),
        duplicate_count=duplicate_count,
    )


class LawAdminService:
    def __init__(self, workflow_service: ContentWorkflowService):
        self.workflow_service = workflow_service
        self.repository = workflow_service.repository

    def get_effective_sources(self, *, server_code: str) -> LawSourcesSnapshot:
        server_config = get_server_config(server_code)
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
            source_urls = normalize_source_urls(getattr(server_config, "law_qa_sources", ()))

        active_version = resolve_active_law_version(server_code=server_code)
        bundle_meta = load_law_bundle_meta(
            server_code,
            getattr(server_config, "law_qa_bundle_path", ""),
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
        source_urls = normalize_source_urls(getattr(get_server_config(server_code), "law_qa_sources", ()))
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
            raise ValueError("source_urls_invalid")

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
    ) -> dict[str, Any]:
        validation = validate_source_urls(source_urls or list(self.get_effective_sources(server_code=server_code).source_urls))
        effective_urls = validation.accepted_urls
        if not effective_urls:
            raise ValueError("source_urls_required")
        if validation.invalid_urls:
            raise ValueError("source_urls_invalid")

        manifest_result = None
        if persist_sources:
            manifest_result = self.publish_sources_manifest(
                server_code=server_code,
                source_urls=list(effective_urls),
                actor_user_id=actor_user_id,
                request_id=request_id,
                comment="law_index_rebuild",
            )

        server_config = get_server_config(server_code)
        bundle = build_law_bundle(server_code, effective_urls)
        bundle_path = resolve_law_bundle_path(server_code, getattr(server_config, "law_qa_bundle_path", ""))
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
            "duplicate_count": validation.duplicate_count,
            "accepted_count": len(validation.accepted_urls),
            "invalid_count": len(validation.invalid_urls),
        }

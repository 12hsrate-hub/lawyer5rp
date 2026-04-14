from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ogp_web.services.content_contracts import normalize_content_type, validate_payload_contract
from ogp_web.storage.admin_catalog_store import AdminCatalogStore
from ogp_web.storage.content_workflow_repository import ContentWorkflowRepository

ALLOWED_SERVER_SCOPES = {"server", "global"}
REVIEW_DECISIONS = {"approve", "reject", "request_changes"}
CHANGE_REQUEST_STATUSES = {"draft", "in_review", "approved", "rejected", "published", "rolled_back"}
HIGH_RISK_TWO_PERSON_TYPES = {"procedures", "templates", "validation_rules"}


@dataclass(frozen=True)
class ScopeContext:
    server_scope: str
    server_id: str | None


class ContentWorkflowService:
    def __init__(self, repository: ContentWorkflowRepository, *, legacy_store: AdminCatalogStore | None = None):
        self.repository = repository
        self.legacy_store = legacy_store

    def _validate_scope(self, *, server_scope: str, server_id: str | None) -> ScopeContext:
        normalized_scope = str(server_scope or "").strip().lower()
        if normalized_scope not in ALLOWED_SERVER_SCOPES:
            raise ValueError("unsupported_server_scope")
        normalized_server_id = str(server_id or "").strip() or None
        if normalized_scope == "server" and not normalized_server_id:
            raise ValueError("server_id_required_for_server_scope")
        if normalized_scope == "global" and normalized_server_id:
            raise ValueError("global_scope_must_not_have_server_id")
        return ScopeContext(server_scope=normalized_scope, server_id=normalized_server_id)

    def _assert_item_scope(self, item: dict[str, Any], *, server_scope: str, server_id: str | None) -> None:
        scope = self._validate_scope(server_scope=server_scope, server_id=server_id)
        if item.get("server_scope") != scope.server_scope or item.get("server_id") != scope.server_id:
            raise PermissionError("scope_mismatch")

    @staticmethod
    def _requires_two_person_review(content_type: str) -> bool:
        return str(content_type or "").strip().lower() in HIGH_RISK_TWO_PERSON_TYPES

    def list_content_items(
        self,
        *,
        server_scope: str,
        server_id: str | None,
        content_type: str | None = None,
        include_legacy_fallback: bool = False,
    ) -> dict[str, Any]:
        scope = self._validate_scope(server_scope=server_scope, server_id=server_id)
        normalized_content_type = normalize_content_type(content_type) if content_type else None
        items = self.repository.list_content_items(
            server_scope=scope.server_scope,
            server_id=scope.server_id,
            content_type=normalized_content_type,
        )
        _ = include_legacy_fallback
        fallback_items: list[dict[str, Any]] = []
        return {
            "items": items,
            "legacy_fallback": fallback_items,
        }

    def get_content_item(self, *, content_item_id: int, server_scope: str, server_id: str | None) -> dict[str, Any]:
        item = self.repository.get_content_item(content_item_id=content_item_id)
        if not item:
            raise KeyError("not_found")
        self._assert_item_scope(item, server_scope=server_scope, server_id=server_id)
        return item

    def create_content_item(
        self,
        *,
        server_scope: str,
        server_id: str | None,
        content_type: str,
        content_key: str,
        title: str,
        metadata_json: dict[str, Any] | None,
        actor_user_id: int,
        request_id: str,
    ) -> dict[str, Any]:
        scope = self._validate_scope(server_scope=server_scope, server_id=server_id)
        normalized_content_type = normalize_content_type(content_type)
        existing = self.repository.get_content_item_by_identity(
            server_scope=scope.server_scope,
            server_id=scope.server_id,
            content_type=normalized_content_type,
            content_key=content_key,
        )
        if existing:
            raise ValueError("content_item_already_exists")
        item = self.repository.create_content_item(
            server_scope=scope.server_scope,
            server_id=scope.server_id,
            content_type=normalized_content_type,
            content_key=content_key,
            title=title,
            status="draft",
            metadata_json=metadata_json or {},
        )
        self._audit(
            server_id=scope.server_id,
            actor_user_id=actor_user_id,
            entity_type="content_item",
            entity_id=str(item["id"]),
            action="create_content_item",
            before_json={},
            after_json=item,
            diff_json={"created": True},
            request_id=request_id,
            metadata_json={"content_type": normalized_content_type, "content_key": content_key},
        )
        return item


    def list_versions(self, *, content_item_id: int, server_scope: str, server_id: str | None) -> list[dict[str, Any]]:
        _ = self.get_content_item(content_item_id=content_item_id, server_scope=server_scope, server_id=server_id)
        return self.repository.list_content_versions(content_item_id=content_item_id)

    def list_change_requests(self, *, content_item_id: int, server_scope: str, server_id: str | None) -> list[dict[str, Any]]:
        _ = self.get_content_item(content_item_id=content_item_id, server_scope=server_scope, server_id=server_id)
        return self.repository.list_change_requests(content_item_id=content_item_id)

    def create_draft_version(
        self,
        *,
        content_item_id: int,
        payload_json: dict[str, Any],
        schema_version: int,
        actor_user_id: int,
        request_id: str,
        server_scope: str,
        server_id: str | None,
        comment: str = "",
    ) -> dict[str, Any]:
        item = self.get_content_item(content_item_id=content_item_id, server_scope=server_scope, server_id=server_id)
        content_type = normalize_content_type(str(item.get("content_type") or ""))
        payload = dict(payload_json or {})
        validation = validate_payload_contract(content_type=content_type, payload_json=payload)
        if not validation.ok:
            raise ValueError(f"content_payload_contract_violation:{';'.join(validation.errors)}")
        version = self.repository.create_content_version(
            content_item_id=content_item_id,
            payload_json=payload,
            schema_version=max(1, int(schema_version or 1)),
            created_by=actor_user_id,
        )
        cr = self.repository.create_change_request(
            content_item_id=content_item_id,
            base_version_id=item.get("current_published_version_id"),
            candidate_version_id=version["id"],
            status="draft",
            proposed_by=actor_user_id,
            comment=comment,
        )
        self._audit(
            server_id=item.get("server_id"),
            actor_user_id=actor_user_id,
            entity_type="change_request",
            entity_id=str(cr["id"]),
            action="create_draft_change_request",
            before_json={},
            after_json=cr,
            diff_json={"candidate_version_id": version["id"]},
            request_id=request_id,
            metadata_json={"content_item_id": content_item_id},
        )
        return {"content_item": item, "version": version, "change_request": cr}

    def validate_change_request(
        self,
        *,
        change_request_id: int,
        server_scope: str,
        server_id: str | None,
    ) -> dict[str, Any]:
        cr = self.repository.get_change_request(change_request_id=change_request_id)
        if not cr:
            raise KeyError("not_found")
        item = self.get_content_item(
            content_item_id=int(cr["content_item_id"]),
            server_scope=server_scope,
            server_id=server_id,
        )
        candidate_version_id = cr.get("candidate_version_id")
        if candidate_version_id is None:
            raise ValueError("change_request_has_no_candidate_version")
        version = self.repository.get_content_version(version_id=int(candidate_version_id))
        if not version:
            raise KeyError("candidate_version_not_found")
        payload = version.get("payload_json")
        content_type = normalize_content_type(str(item.get("content_type") or ""))
        validation = validate_payload_contract(
            content_type=content_type,
            payload_json=dict(payload or {}) if isinstance(payload, dict) else {},
        )
        return {
            "ok": validation.ok,
            "errors": list(validation.errors),
            "content_item": item,
            "change_request": cr,
            "version": version,
            "content_type": content_type,
        }

    def submit_change_request(
        self,
        *,
        change_request_id: int,
        actor_user_id: int,
        request_id: str,
        server_scope: str,
        server_id: str | None,
    ) -> dict[str, Any]:
        cr = self.repository.get_change_request(change_request_id=change_request_id)
        if not cr:
            raise KeyError("not_found")
        item = self.get_content_item(content_item_id=int(cr["content_item_id"]), server_scope=server_scope, server_id=server_id)
        if cr.get("status") != "draft":
            raise ValueError("change_request_must_be_draft")
        validation = self.validate_change_request(
            change_request_id=change_request_id,
            server_scope=server_scope,
            server_id=server_id,
        )
        if not validation["ok"]:
            raise ValueError(f"change_request_validation_failed:{';'.join(validation['errors'])}")
        updated = self.repository.update_change_request_status(change_request_id=change_request_id, status="in_review")
        self._audit(
            server_id=item.get("server_id"),
            actor_user_id=actor_user_id,
            entity_type="change_request",
            entity_id=str(change_request_id),
            action="submit_for_review",
            before_json=cr,
            after_json=updated,
            diff_json={"status": {"from": cr.get("status"), "to": "in_review"}},
            request_id=request_id,
            metadata_json={"content_item_id": item["id"]},
        )
        return updated

    def review_change_request(
        self,
        *,
        change_request_id: int,
        reviewer_user_id: int,
        decision: str,
        comment: str,
        diff_json: dict[str, Any],
        request_id: str,
        server_scope: str,
        server_id: str | None,
    ) -> dict[str, Any]:
        normalized_decision = str(decision or "").strip().lower()
        if normalized_decision not in REVIEW_DECISIONS:
            raise ValueError("unsupported_review_decision")
        cr = self.repository.get_change_request(change_request_id=change_request_id)
        if not cr:
            raise KeyError("not_found")
        item = self.get_content_item(content_item_id=int(cr["content_item_id"]), server_scope=server_scope, server_id=server_id)
        if cr.get("status") != "in_review":
            raise ValueError("change_request_must_be_in_review")
        content_type = normalize_content_type(str(item.get("content_type") or ""))
        if (
            normalized_decision == "approve"
            and self._requires_two_person_review(content_type)
            and int(cr.get("proposed_by") or 0) == int(reviewer_user_id)
        ):
            raise ValueError("two_person_review_required_for_high_risk_entity")
        review = self.repository.create_review(
            change_request_id=change_request_id,
            reviewer_user_id=reviewer_user_id,
            decision=normalized_decision,
            comment=comment,
            diff_json=diff_json or {},
        )
        status = "approved" if normalized_decision == "approve" else "rejected"
        if normalized_decision == "request_changes":
            status = "draft"
        updated = self.repository.update_change_request_status(change_request_id=change_request_id, status=status)
        self._audit(
            server_id=item.get("server_id"),
            actor_user_id=reviewer_user_id,
            entity_type="review",
            entity_id=str(review["id"]),
            action=f"review_{normalized_decision}",
            before_json=cr,
            after_json=updated,
            diff_json={"decision": normalized_decision, "status": status},
            request_id=request_id,
            metadata_json={"change_request_id": change_request_id},
        )
        return {"review": review, "change_request": updated}

    def publish_change_request(
        self,
        *,
        change_request_id: int,
        actor_user_id: int,
        request_id: str,
        summary_json: dict[str, Any] | None,
        server_scope: str,
        server_id: str | None,
    ) -> dict[str, Any]:
        cr = self.repository.get_change_request(change_request_id=change_request_id)
        if not cr:
            raise KeyError("not_found")
        if cr.get("status") != "approved":
            raise ValueError("publish_requires_approved_change_request")
        validation = self.validate_change_request(
            change_request_id=change_request_id,
            server_scope=server_scope,
            server_id=server_id,
        )
        if not validation["ok"]:
            raise ValueError(f"change_request_validation_failed:{';'.join(validation['errors'])}")
        item = self.get_content_item(content_item_id=int(cr["content_item_id"]), server_scope=server_scope, server_id=server_id)
        candidate_version_id = int(cr["candidate_version_id"])
        previous_version_id = item.get("current_published_version_id")
        batch = self.repository.create_publish_batch(
            server_scope=item["server_scope"],
            server_id=item.get("server_id"),
            published_by=actor_user_id,
            rollback_of_batch_id=None,
            summary_json=summary_json or {},
        )
        batch_item = self.repository.create_publish_batch_item(
            publish_batch_id=batch["id"],
            content_item_id=item["id"],
            published_version_id=candidate_version_id,
            previous_published_version_id=previous_version_id,
        )
        updated_item = self.repository.set_current_published_version(
            content_item_id=item["id"],
            version_id=candidate_version_id,
            status="published",
        )
        updated_cr = self.repository.update_change_request_status(change_request_id=change_request_id, status="published")
        self._audit(
            server_id=item.get("server_id"),
            actor_user_id=actor_user_id,
            entity_type="publish_batch",
            entity_id=str(batch["id"]),
            action="publish_change_request",
            before_json={"current_published_version_id": previous_version_id},
            after_json={"current_published_version_id": candidate_version_id},
            diff_json={"change_request_id": change_request_id, "batch_item_id": batch_item["id"]},
            request_id=request_id,
            metadata_json={"content_item_id": item["id"]},
        )
        return {
            "batch": batch,
            "batch_item": batch_item,
            "content_item": updated_item,
            "change_request": updated_cr,
        }

    def rollback_publish_batch(
        self,
        *,
        publish_batch_id: int,
        actor_user_id: int,
        request_id: str,
        reason: str,
        server_scope: str,
        server_id: str | None,
    ) -> dict[str, Any]:
        source_batch = self.repository.get_publish_batch(batch_id=publish_batch_id)
        if not source_batch:
            raise KeyError("batch_not_found")
        scope = self._validate_scope(server_scope=server_scope, server_id=server_id)
        if source_batch.get("server_scope") != scope.server_scope or source_batch.get("server_id") != scope.server_id:
            raise PermissionError("scope_mismatch")
        source_items = self.repository.list_publish_batch_items(publish_batch_id=publish_batch_id)
        if not source_items:
            raise ValueError("empty_publish_batch")
        rollback_batch = self.repository.create_publish_batch(
            server_scope=scope.server_scope,
            server_id=scope.server_id,
            published_by=actor_user_id,
            rollback_of_batch_id=publish_batch_id,
            summary_json={"reason": reason, "mode": "rollback"},
        )
        created_items: list[dict[str, Any]] = []
        for source_item in source_items:
            item = self.get_content_item(
                content_item_id=int(source_item["content_item_id"]),
                server_scope=scope.server_scope,
                server_id=scope.server_id,
            )
            restore_version_id = source_item.get("previous_published_version_id")
            created_items.append(
                self.repository.create_publish_batch_item(
                    publish_batch_id=rollback_batch["id"],
                    content_item_id=int(source_item["content_item_id"]),
                    published_version_id=restore_version_id,
                    previous_published_version_id=item.get("current_published_version_id"),
                )
            )
            self.repository.set_current_published_version(
                content_item_id=int(source_item["content_item_id"]),
                version_id=restore_version_id,
                status="published" if restore_version_id else "draft",
            )
        self._audit(
            server_id=scope.server_id,
            actor_user_id=actor_user_id,
            entity_type="publish_batch",
            entity_id=str(rollback_batch["id"]),
            action="rollback_publish_batch",
            before_json={"rollback_of_batch_id": None},
            after_json={"rollback_of_batch_id": publish_batch_id},
            diff_json={"items": len(created_items)},
            request_id=request_id,
            metadata_json={"reason": reason},
        )
        return {"batch": rollback_batch, "items": created_items}

    def list_audit_trail(
        self,
        *,
        server_scope: str,
        server_id: str | None,
        entity_type: str = "",
        entity_id: str = "",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        scope = self._validate_scope(server_scope=server_scope, server_id=server_id)
        return self.repository.list_audit_logs(
            server_id=scope.server_id,
            entity_type=entity_type,
            entity_id=entity_id,
            limit=limit,
        )

    def _audit(
        self,
        *,
        server_id: str | None,
        actor_user_id: int,
        entity_type: str,
        entity_id: str,
        action: str,
        before_json: dict[str, Any],
        after_json: dict[str, Any],
        diff_json: dict[str, Any],
        request_id: str,
        metadata_json: dict[str, Any],
    ) -> None:
        self.repository.append_audit_log(
            server_id=server_id,
            actor_user_id=actor_user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            before_json=before_json,
            after_json=after_json,
            diff_json=diff_json,
            request_id=request_id,
            metadata_json=metadata_json,
        )

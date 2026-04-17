from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ogp_web.services.content_workflow_service import ContentWorkflowService
from ogp_web.services.law_admin_service import LawAdminService
from ogp_web.services.law_bundle_service import load_law_bundle_meta
from ogp_web.services.law_version_service import resolve_active_law_version
from ogp_web.services.law_sources_validation import normalize_source_urls
from ogp_web.services.runtime_pack_reader_service import RuntimePackSnapshot, read_runtime_pack_snapshot
from ogp_web.services.server_context_service import (
    resolve_server_law_bundle_path,
    resolve_server_law_sources,
)
from ogp_web.storage.content_workflow_repository import ContentWorkflowRepository
from ogp_web.storage.law_source_sets_store import LawSourceSetsStore
from ogp_web.storage.server_effective_law_projections_store import ServerEffectiveLawProjectionsStore


class _NullWorkflowService:
    repository = None


class _EmptyLawSourceSetsStore:
    def list_bindings(self, *, server_code: str):
        _ = server_code
        return []

    def list_revisions(self, *, source_set_key: str):
        _ = source_set_key
        return []


class _EmptyProjectionsStore:
    def list_runs(self, *, server_code: str):
        _ = server_code
        return []


@dataclass(frozen=True)
class LawContextReadiness:
    server_code: str
    is_ready: bool
    status: str
    mode: str
    reason_code: str
    reason_detail: str
    requested_law_version_id: int | None
    active_law_version_id: int | None
    matches_requested_version: bool | None
    source_origin: str
    source_urls: tuple[str, ...]
    active_binding_ids: tuple[int, ...]
    active_source_set_keys: tuple[str, ...]
    latest_published_revision_ids: tuple[int, ...]
    projection_run_id: int | None
    projection_status: str
    projection_law_version_id: int | None
    projection_matches_active_version: bool | None
    bundle_fingerprint: str
    bundle_chunk_count: int
    runtime_pack_resolution_mode: str
    runtime_pack_source_label: str
    runtime_pack_version: int | None
    runtime_pack_is_published: bool

    def to_payload(self) -> dict[str, Any]:
        return {
            "server_code": self.server_code,
            "is_ready": self.is_ready,
            "status": self.status,
            "mode": self.mode,
            "reason_code": self.reason_code,
            "reason_detail": self.reason_detail,
            "requested_law_version_id": self.requested_law_version_id,
            "active_law_version_id": self.active_law_version_id,
            "matches_requested_version": self.matches_requested_version,
            "source_origin": self.source_origin,
            "source_urls": list(self.source_urls),
            "bindings": {
                "active_binding_ids": list(self.active_binding_ids),
                "active_source_set_keys": list(self.active_source_set_keys),
                "latest_published_revision_ids": list(self.latest_published_revision_ids),
                "has_canonical_bindings": bool(self.active_binding_ids),
            },
            "projection": {
                "run_id": self.projection_run_id,
                "status": self.projection_status,
                "law_version_id": self.projection_law_version_id,
                "matches_active_law_version": self.projection_matches_active_version,
            },
            "bundle": {
                "fingerprint": self.bundle_fingerprint,
                "chunk_count": self.bundle_chunk_count,
            },
            "runtime_pack": {
                "resolution_mode": self.runtime_pack_resolution_mode,
                "source_label": self.runtime_pack_source_label,
                "pack_version": self.runtime_pack_version,
                "is_published": self.runtime_pack_is_published,
            },
            "provenance_refs": {
                "binding_ids": list(self.active_binding_ids),
                "source_set_keys": list(self.active_source_set_keys),
                "source_set_revision_ids": list(self.latest_published_revision_ids),
                "projection_run_id": self.projection_run_id,
                "law_version_id": self.active_law_version_id,
                "runtime_pack_version": self.runtime_pack_version,
                "runtime_pack_resolution_mode": self.runtime_pack_resolution_mode,
            },
        }


def _build_snapshot_stub(
    *,
    source_origin: str,
    source_urls: tuple[str, ...],
    active_law_version: dict[str, Any] | None,
    bundle_meta: dict[str, Any] | None,
):
    return type(
        "Snapshot",
        (),
        {
            "source_origin": source_origin,
            "source_urls": source_urls,
            "active_law_version": active_law_version,
            "bundle_meta": bundle_meta,
        },
    )()


def _load_bundle_meta_from_runtime_pack(
    *,
    server_code: str,
    pack_snapshot: RuntimePackSnapshot,
) -> dict[str, Any]:
    bundle_path = str(pack_snapshot.metadata.get("law_qa_bundle_path") or "").strip()
    if not bundle_path:
        return {}
    try:
        bundle_meta = load_law_bundle_meta(server_code, bundle_path)
    except Exception:
        return {}
    if bundle_meta is None:
        return {}
    return dict(getattr(bundle_meta, "__dict__", {}) or {})


def _apply_runtime_pack_fallback(
    *,
    snapshot: Any,
    pack_snapshot: RuntimePackSnapshot,
) -> Any:
    source_origin = str(getattr(snapshot, "source_origin", "") or "").strip() or "unknown"
    source_urls = normalize_source_urls(getattr(snapshot, "source_urls", ()) or ())
    active_law_version = (
        dict(getattr(snapshot, "active_law_version", {}) or {})
        if isinstance(getattr(snapshot, "active_law_version", {}), dict)
        else None
    )
    bundle_meta = (
        dict(getattr(snapshot, "bundle_meta", {}) or {})
        if isinstance(getattr(snapshot, "bundle_meta", {}), dict)
        else {}
    )
    pack_source_urls = normalize_source_urls(pack_snapshot.metadata.get("law_qa_sources") or ())
    if not source_urls and pack_source_urls:
        source_urls = pack_source_urls
        if pack_snapshot.resolution_mode in {"published_pack", "bootstrap_pack"}:
            source_origin = "runtime_pack"
    if not bundle_meta:
        bundle_meta = _load_bundle_meta_from_runtime_pack(
            server_code=pack_snapshot.server_code,
            pack_snapshot=pack_snapshot,
        )
    return _build_snapshot_stub(
        source_origin=source_origin,
        source_urls=source_urls,
        active_law_version=active_law_version,
        bundle_meta=bundle_meta,
    )


def _build_legacy_server_context_snapshot(*, server_code: str) -> Any:
    try:
        bundle_path = resolve_server_law_bundle_path(server_code=server_code)
    except Exception:
        bundle_path = ""
    try:
        source_urls = resolve_server_law_sources(server_code=server_code)
    except Exception:
        source_urls = ()
    try:
        bundle_meta = load_law_bundle_meta(server_code, bundle_path) if bundle_path else None
    except Exception:
        bundle_meta = None
    return _build_snapshot_stub(
        source_origin="server_config",
        source_urls=normalize_source_urls(source_urls),
        active_law_version=None,
        bundle_meta=dict(getattr(bundle_meta, "__dict__", {}) or {}),
    )


def _latest_published_revision_id(
    source_sets_store: LawSourceSetsStore,
    *,
    source_set_key: str,
) -> int | None:
    try:
        revisions = source_sets_store.list_revisions(source_set_key=source_set_key)
    except Exception:
        return None
    for item in revisions:
        if str(item.status or "").strip().lower() in {"published", "legacy_flat"}:
            return int(item.id)
    return None


def _select_projection_summary(
    projections_store: ServerEffectiveLawProjectionsStore,
    *,
    server_code: str,
    active_law_version_id: int | None,
) -> dict[str, Any]:
    runs = projections_store.list_runs(server_code=server_code)
    if not runs:
        return {}
    selected = None
    for run in runs:
        summary_json = dict(run.summary_json or {})
        activation = dict(summary_json.get("activation") or {})
        if active_law_version_id and int(activation.get("law_version_id") or 0) == int(active_law_version_id):
            selected = run
            break
    if selected is None:
        selected = runs[0]
    summary_json = dict(selected.summary_json or {})
    activation = dict(summary_json.get("activation") or {})
    projection_law_version_id = int(activation.get("law_version_id") or 0) or None
    return {
        "run_id": int(selected.id),
        "status": str(selected.status or ""),
        "law_version_id": projection_law_version_id,
        "matches_active_law_version": (
            bool(active_law_version_id and projection_law_version_id == int(active_law_version_id))
            if active_law_version_id
            else None
        ),
    }


class LawContextReadinessService:
    def __init__(
        self,
        *,
        workflow_service: ContentWorkflowService,
        source_sets_store: LawSourceSetsStore,
        projections_store: ServerEffectiveLawProjectionsStore,
    ):
        self.workflow_service = workflow_service
        self.source_sets_store = source_sets_store
        self.projections_store = projections_store
        self.law_admin_service = LawAdminService(workflow_service)

    def get_readiness(
        self,
        *,
        server_code: str,
        requested_law_version_id: int | None = None,
    ) -> LawContextReadiness:
        normalized_server = str(server_code or "").strip().lower()
        pack_snapshot = read_runtime_pack_snapshot(server_code=normalized_server)
        try:
            snapshot = self.law_admin_service.get_effective_sources(server_code=normalized_server)
        except Exception:
            snapshot = _build_legacy_server_context_snapshot(server_code=normalized_server)
        snapshot = _apply_runtime_pack_fallback(snapshot=snapshot, pack_snapshot=pack_snapshot)
        active_law_version = dict(snapshot.active_law_version or {}) if isinstance(snapshot.active_law_version, dict) else {}
        if not active_law_version:
            try:
                resolved_version = resolve_active_law_version(server_code=normalized_server)
            except Exception:
                resolved_version = None
            if resolved_version is not None:
                active_law_version = {
                    "id": int(getattr(resolved_version, "id", 0) or 0) or None,
                    "chunk_count": int(getattr(resolved_version, "chunk_count", 0) or 0),
                    "fingerprint": str(getattr(resolved_version, "fingerprint", "") or ""),
                }
        bundle_meta = dict(snapshot.bundle_meta or {}) if isinstance(snapshot.bundle_meta, dict) else {}
        active_law_version_id = int(active_law_version.get("id") or 0) or None
        try:
            bindings = list(self.source_sets_store.list_bindings(server_code=normalized_server))
        except Exception:
            bindings = []
        active_bindings = [item for item in bindings if bool(getattr(item, "is_active", False))]
        latest_revision_ids = tuple(
            revision_id
            for revision_id in (
                _latest_published_revision_id(self.source_sets_store, source_set_key=item.source_set_key)
                for item in active_bindings
            )
            if revision_id is not None
        )
        try:
            projection = _select_projection_summary(
                self.projections_store,
                server_code=normalized_server,
                active_law_version_id=active_law_version_id,
            )
        except Exception:
            projection = {}
        projection_run_id = int(projection.get("run_id") or 0) or None
        projection_status = str(projection.get("status") or "")
        projection_law_version_id = int(projection.get("law_version_id") or 0) or None
        projection_matches_active = projection.get("matches_active_law_version")
        requested_version_id = int(requested_law_version_id or 0) or None
        matches_requested = (
            bool(active_law_version_id and requested_version_id == active_law_version_id)
            if requested_version_id is not None and active_law_version_id is not None
            else None
        )

        if requested_version_id is not None and active_law_version_id is not None and requested_version_id != active_law_version_id:
            return LawContextReadiness(
                server_code=normalized_server,
                is_ready=False,
                status="blocked",
                mode="selected_server_runtime_drift",
                reason_code="runtime_drift",
                reason_detail="Requested law version does not match the selected server active runtime law version.",
                requested_law_version_id=requested_version_id,
                active_law_version_id=active_law_version_id,
                matches_requested_version=False,
                source_origin=str(snapshot.source_origin or ""),
                source_urls=tuple(snapshot.source_urls or ()),
                active_binding_ids=tuple(int(item.id) for item in active_bindings),
                active_source_set_keys=tuple(item.source_set_key for item in active_bindings),
                latest_published_revision_ids=latest_revision_ids,
                projection_run_id=projection_run_id,
                projection_status=projection_status,
                projection_law_version_id=projection_law_version_id,
                projection_matches_active_version=projection_matches_active,
                bundle_fingerprint=str(bundle_meta.get("fingerprint") or ""),
                bundle_chunk_count=int(bundle_meta.get("chunk_count") or 0),
                runtime_pack_resolution_mode=pack_snapshot.resolution_mode,
                runtime_pack_source_label=pack_snapshot.source_label,
                runtime_pack_version=pack_snapshot.pack_version,
                runtime_pack_is_published=pack_snapshot.has_published_pack,
            )

        if active_bindings:
            if not latest_revision_ids:
                return LawContextReadiness(
                    server_code=normalized_server,
                    is_ready=False,
                    status="blocked",
                    mode="canonical_bindings",
                    reason_code="no_published_revision",
                    reason_detail="Active source-set bindings exist, but no published revisions are available.",
                    requested_law_version_id=requested_version_id,
                    active_law_version_id=active_law_version_id,
                    matches_requested_version=matches_requested,
                    source_origin=str(snapshot.source_origin or ""),
                    source_urls=tuple(snapshot.source_urls or ()),
                    active_binding_ids=tuple(int(item.id) for item in active_bindings),
                    active_source_set_keys=tuple(item.source_set_key for item in active_bindings),
                    latest_published_revision_ids=latest_revision_ids,
                    projection_run_id=projection_run_id,
                    projection_status=projection_status,
                    projection_law_version_id=projection_law_version_id,
                    projection_matches_active_version=projection_matches_active,
                    bundle_fingerprint=str(bundle_meta.get("fingerprint") or ""),
                    bundle_chunk_count=int(bundle_meta.get("chunk_count") or 0),
                    runtime_pack_resolution_mode=pack_snapshot.resolution_mode,
                    runtime_pack_source_label=pack_snapshot.source_label,
                    runtime_pack_version=pack_snapshot.pack_version,
                    runtime_pack_is_published=pack_snapshot.has_published_pack,
                )
            if projection_run_id is None:
                return LawContextReadiness(
                    server_code=normalized_server,
                    is_ready=False,
                    status="blocked",
                    mode="canonical_bindings",
                    reason_code="no_projection",
                    reason_detail="Active source-set bindings exist, but no approved projection bridge is available.",
                    requested_law_version_id=requested_version_id,
                    active_law_version_id=active_law_version_id,
                    matches_requested_version=matches_requested,
                    source_origin=str(snapshot.source_origin or ""),
                    source_urls=tuple(snapshot.source_urls or ()),
                    active_binding_ids=tuple(int(item.id) for item in active_bindings),
                    active_source_set_keys=tuple(item.source_set_key for item in active_bindings),
                    latest_published_revision_ids=latest_revision_ids,
                    projection_run_id=projection_run_id,
                    projection_status=projection_status,
                    projection_law_version_id=projection_law_version_id,
                    projection_matches_active_version=projection_matches_active,
                    bundle_fingerprint=str(bundle_meta.get("fingerprint") or ""),
                    bundle_chunk_count=int(bundle_meta.get("chunk_count") or 0),
                    runtime_pack_resolution_mode=pack_snapshot.resolution_mode,
                    runtime_pack_source_label=pack_snapshot.source_label,
                    runtime_pack_version=pack_snapshot.pack_version,
                    runtime_pack_is_published=pack_snapshot.has_published_pack,
                )
            if active_law_version_id is None:
                return LawContextReadiness(
                    server_code=normalized_server,
                    is_ready=False,
                    status="blocked",
                    mode="canonical_bindings",
                    reason_code="no_active_runtime_version",
                    reason_detail="Projection bridge exists, but no active runtime law version is available.",
                    requested_law_version_id=requested_version_id,
                    active_law_version_id=active_law_version_id,
                    matches_requested_version=matches_requested,
                    source_origin=str(snapshot.source_origin or ""),
                    source_urls=tuple(snapshot.source_urls or ()),
                    active_binding_ids=tuple(int(item.id) for item in active_bindings),
                    active_source_set_keys=tuple(item.source_set_key for item in active_bindings),
                    latest_published_revision_ids=latest_revision_ids,
                    projection_run_id=projection_run_id,
                    projection_status=projection_status,
                    projection_law_version_id=projection_law_version_id,
                    projection_matches_active_version=projection_matches_active,
                    bundle_fingerprint=str(bundle_meta.get("fingerprint") or ""),
                    bundle_chunk_count=int(bundle_meta.get("chunk_count") or 0),
                    runtime_pack_resolution_mode=pack_snapshot.resolution_mode,
                    runtime_pack_source_label=pack_snapshot.source_label,
                    runtime_pack_version=pack_snapshot.pack_version,
                    runtime_pack_is_published=pack_snapshot.has_published_pack,
                )
            if projection_matches_active is False:
                return LawContextReadiness(
                    server_code=normalized_server,
                    is_ready=False,
                    status="blocked",
                    mode="canonical_bindings",
                    reason_code="runtime_drift",
                    reason_detail="Projection bridge does not match the selected server active runtime law version.",
                    requested_law_version_id=requested_version_id,
                    active_law_version_id=active_law_version_id,
                    matches_requested_version=matches_requested,
                    source_origin=str(snapshot.source_origin or ""),
                    source_urls=tuple(snapshot.source_urls or ()),
                    active_binding_ids=tuple(int(item.id) for item in active_bindings),
                    active_source_set_keys=tuple(item.source_set_key for item in active_bindings),
                    latest_published_revision_ids=latest_revision_ids,
                    projection_run_id=projection_run_id,
                    projection_status=projection_status,
                    projection_law_version_id=projection_law_version_id,
                    projection_matches_active_version=projection_matches_active,
                    bundle_fingerprint=str(bundle_meta.get("fingerprint") or ""),
                    bundle_chunk_count=int(bundle_meta.get("chunk_count") or 0),
                    runtime_pack_resolution_mode=pack_snapshot.resolution_mode,
                    runtime_pack_source_label=pack_snapshot.source_label,
                    runtime_pack_version=pack_snapshot.pack_version,
                    runtime_pack_is_published=pack_snapshot.has_published_pack,
                )
            return LawContextReadiness(
                server_code=normalized_server,
                is_ready=True,
                status="ready",
                mode="projection_bridge",
                reason_code="ready",
                reason_detail="Selected server law context is aligned through canonical bindings and active projection bridge.",
                requested_law_version_id=requested_version_id,
                active_law_version_id=active_law_version_id,
                matches_requested_version=matches_requested,
                source_origin=str(snapshot.source_origin or ""),
                source_urls=tuple(snapshot.source_urls or ()),
                active_binding_ids=tuple(int(item.id) for item in active_bindings),
                active_source_set_keys=tuple(item.source_set_key for item in active_bindings),
                latest_published_revision_ids=latest_revision_ids,
                projection_run_id=projection_run_id,
                projection_status=projection_status,
                projection_law_version_id=projection_law_version_id,
                projection_matches_active_version=projection_matches_active,
                bundle_fingerprint=str(bundle_meta.get("fingerprint") or ""),
                bundle_chunk_count=int(bundle_meta.get("chunk_count") or 0),
                runtime_pack_resolution_mode=pack_snapshot.resolution_mode,
                runtime_pack_source_label=pack_snapshot.source_label,
                runtime_pack_version=pack_snapshot.pack_version,
                runtime_pack_is_published=pack_snapshot.has_published_pack,
            )

        if tuple(snapshot.source_urls or ()) and active_law_version_id is not None:
            return LawContextReadiness(
                server_code=normalized_server,
                is_ready=True,
                status="ready_with_compatibility",
                mode="legacy_effective_sources",
                reason_code="compatibility_bridge",
                reason_detail="Selected server law context is available through legacy effective sources and the active runtime law version.",
                requested_law_version_id=requested_version_id,
                active_law_version_id=active_law_version_id,
                matches_requested_version=matches_requested,
                source_origin=str(snapshot.source_origin or ""),
                source_urls=tuple(snapshot.source_urls or ()),
                active_binding_ids=(),
                active_source_set_keys=(),
                latest_published_revision_ids=(),
                projection_run_id=projection_run_id,
                projection_status=projection_status,
                projection_law_version_id=projection_law_version_id,
                projection_matches_active_version=projection_matches_active,
                bundle_fingerprint=str(bundle_meta.get("fingerprint") or ""),
                bundle_chunk_count=int(bundle_meta.get("chunk_count") or 0),
                runtime_pack_resolution_mode=pack_snapshot.resolution_mode,
                runtime_pack_source_label=pack_snapshot.source_label,
                runtime_pack_version=pack_snapshot.pack_version,
                runtime_pack_is_published=pack_snapshot.has_published_pack,
            )

        if tuple(snapshot.source_urls or ()) and int(bundle_meta.get("chunk_count") or 0) > 0:
            return LawContextReadiness(
                server_code=normalized_server,
                is_ready=True,
                status="ready_with_compatibility",
                mode="legacy_bundle_fallback",
                reason_code="compatibility_bridge",
                reason_detail="Selected server law context is available through the server-bound bundle fallback, but has no active runtime law version.",
                requested_law_version_id=requested_version_id,
                active_law_version_id=active_law_version_id,
                matches_requested_version=matches_requested,
                source_origin=str(snapshot.source_origin or ""),
                source_urls=tuple(snapshot.source_urls or ()),
                active_binding_ids=(),
                active_source_set_keys=(),
                latest_published_revision_ids=(),
                projection_run_id=projection_run_id,
                projection_status=projection_status,
                projection_law_version_id=projection_law_version_id,
                projection_matches_active_version=projection_matches_active,
                bundle_fingerprint=str(bundle_meta.get("fingerprint") or ""),
                bundle_chunk_count=int(bundle_meta.get("chunk_count") or 0),
                runtime_pack_resolution_mode=pack_snapshot.resolution_mode,
                runtime_pack_source_label=pack_snapshot.source_label,
                runtime_pack_version=pack_snapshot.pack_version,
                runtime_pack_is_published=pack_snapshot.has_published_pack,
            )

        return LawContextReadiness(
            server_code=normalized_server,
            is_ready=False,
            status="blocked",
            mode="unconfigured",
            reason_code="no_bindings",
            reason_detail="Selected server has no canonical bindings or legacy effective law context configured.",
            requested_law_version_id=requested_version_id,
            active_law_version_id=active_law_version_id,
            matches_requested_version=matches_requested,
            source_origin=str(snapshot.source_origin or ""),
            source_urls=tuple(snapshot.source_urls or ()),
            active_binding_ids=(),
            active_source_set_keys=(),
            latest_published_revision_ids=(),
            projection_run_id=projection_run_id,
            projection_status=projection_status,
            projection_law_version_id=projection_law_version_id,
            projection_matches_active_version=projection_matches_active,
            bundle_fingerprint=str(bundle_meta.get("fingerprint") or ""),
            bundle_chunk_count=int(bundle_meta.get("chunk_count") or 0),
            runtime_pack_resolution_mode=pack_snapshot.resolution_mode,
            runtime_pack_source_label=pack_snapshot.source_label,
            runtime_pack_version=pack_snapshot.pack_version,
            runtime_pack_is_published=pack_snapshot.has_published_pack,
        )


def build_law_context_readiness_service(
    *,
    backend: Any | None = None,
    workflow_service: ContentWorkflowService | Any | None = None,
    source_sets_store: LawSourceSetsStore | Any | None = None,
    projections_store: ServerEffectiveLawProjectionsStore | Any | None = None,
) -> LawContextReadinessService:
    if workflow_service is None:
        if backend is not None:
            workflow_service = ContentWorkflowService(ContentWorkflowRepository(backend), legacy_store=None)
        else:
            workflow_service = _NullWorkflowService()
    if source_sets_store is None:
        source_sets_store = LawSourceSetsStore(backend) if backend is not None else _EmptyLawSourceSetsStore()
    if projections_store is None:
        projections_store = (
            ServerEffectiveLawProjectionsStore(backend) if backend is not None else _EmptyProjectionsStore()
        )
    return LawContextReadinessService(
        workflow_service=workflow_service,
        source_sets_store=source_sets_store,
        projections_store=projections_store,
    )

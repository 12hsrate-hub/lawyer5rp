from __future__ import annotations

from typing import Any

from ogp_web.services.admin_law_projection_service import (
    preview_server_effective_law_projection_payload,
)
from ogp_web.services.admin_runtime_servers_service import (
    build_runtime_config_debt_summary,
    build_runtime_config_posture_summary,
    build_runtime_resolution_policy_summary,
    build_runtime_server_health_payload,
    normalize_runtime_server_code,
)
from ogp_web.storage.canonical_law_document_versions_store import (
    CanonicalLawDocumentVersionsStore,
)
from ogp_web.storage.law_source_sets_store import LawSourceSetsStore
from ogp_web.storage.runtime_law_sets_store import RuntimeLawSetsStore
from ogp_web.storage.runtime_servers_store import RuntimeServersStore
from ogp_web.storage.server_effective_law_projections_store import (
    ServerEffectiveLawProjectionItemRecord,
    ServerEffectiveLawProjectionRunRecord,
    ServerEffectiveLawProjectionsStore,
)


def _serialize_binding(binding: Any) -> dict[str, Any]:
    include_law_keys = getattr(binding, "include_law_keys", [])
    exclude_law_keys = getattr(binding, "exclude_law_keys", [])
    pin_policy_json = getattr(binding, "pin_policy_json", {})
    metadata_json = getattr(binding, "metadata_json", {})
    return {
        "id": int(binding.id),
        "server_code": str(binding.server_code or ""),
        "source_set_key": str(binding.source_set_key or ""),
        "priority": int(binding.priority or 0),
        "is_active": bool(binding.is_active),
        "include_law_keys": [str(item or "") for item in list(include_law_keys or []) if str(item or "").strip()],
        "exclude_law_keys": [str(item or "") for item in list(exclude_law_keys or []) if str(item or "").strip()],
        "pin_policy_json": dict(pin_policy_json or {}),
        "metadata_json": dict(metadata_json or {}),
        "created_at": str(getattr(binding, "created_at", "") or ""),
        "updated_at": str(getattr(binding, "updated_at", "") or ""),
    }


def _serialize_run(run: ServerEffectiveLawProjectionRunRecord | None) -> dict[str, Any] | None:
    if run is None:
        return None
    summary_json = dict(run.summary_json or {})
    return {
        "id": int(run.id),
        "server_code": str(run.server_code or ""),
        "trigger_mode": str(run.trigger_mode or "manual"),
        "status": str(run.status or "preview"),
        "summary_json": summary_json,
        "decision_status": str(summary_json.get("decision_status") or ""),
        "selected_count": int(summary_json.get("selected_count") or 0),
        "candidate_count": int(summary_json.get("candidate_count") or 0),
        "created_at": str(run.created_at or ""),
    }


def _latest_projection_runs(
    projections_store: ServerEffectiveLawProjectionsStore,
    *,
    server_code: str,
) -> tuple[ServerEffectiveLawProjectionRunRecord | None, ServerEffectiveLawProjectionRunRecord | None]:
    runs = projections_store.list_runs(server_code=server_code)
    current = runs[0] if runs else None
    previous = runs[1] if len(runs) > 1 else None
    return current, previous


def _safe_excerpt(text: str, *, limit: int = 220) -> str:
    normalized = " ".join(str(text or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _diff_summary(
    current_items: list[ServerEffectiveLawProjectionItemRecord],
    previous_items: list[ServerEffectiveLawProjectionItemRecord],
) -> dict[str, Any]:
    current_map = {
        str(item.canonical_identity_key or "").strip().lower(): int(item.selected_document_version_id)
        for item in current_items
        if str(item.canonical_identity_key or "").strip()
    }
    previous_map = {
        str(item.canonical_identity_key or "").strip().lower(): int(item.selected_document_version_id)
        for item in previous_items
        if str(item.canonical_identity_key or "").strip()
    }
    current_keys = set(current_map)
    previous_keys = set(previous_map)
    shared = current_keys & previous_keys
    added = current_keys - previous_keys
    removed = previous_keys - current_keys
    changed = {key for key in shared if current_map.get(key) != previous_map.get(key)}
    unchanged = shared - changed
    errored = sum(1 for item in current_items if str(item.status or "").strip().lower() != "candidate")
    return {
        "baseline_run_id": None,
        "current_run_id": None,
        "added": len(added),
        "removed": len(removed),
        "changed": len(changed),
        "unchanged": len(unchanged),
        "errored": int(errored),
    }


def _effective_items_payload(
    *,
    projections_store: ServerEffectiveLawProjectionsStore,
    versions_store: CanonicalLawDocumentVersionsStore,
    run: ServerEffectiveLawProjectionRunRecord | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if run is None:
        return [], {
            "run": None,
            "count": 0,
            "with_content": 0,
            "missing_content": 0,
            "error_count": 0,
            "last_updated_at": "",
        }
    items = projections_store.list_items(projection_run_id=int(run.id))
    payload_items: list[dict[str, Any]] = []
    with_content = 0
    missing_content = 0
    error_count = 0
    last_updated_at = ""
    for item in items:
        version = versions_store.get_version(version_id=int(item.selected_document_version_id))
        title = ""
        preview_text = ""
        updated_at = ""
        fetch_status = "missing"
        parse_status = "missing"
        has_content = False
        if version is not None:
            title = str(
                version.parsed_title
                or version.raw_title
                or version.display_title
                or item.canonical_identity_key
                or item.normalized_url
                or ""
            ).strip()
            preview_text = _safe_excerpt(version.body_text)
            updated_at = str(version.updated_at or "")
            fetch_status = str(version.fetch_status or "missing")
            parse_status = str(version.parse_status or "missing")
            has_content = bool(str(version.body_text or "").strip())
            if updated_at and updated_at > last_updated_at:
                last_updated_at = updated_at
        if has_content:
            with_content += 1
        else:
            missing_content += 1
        if fetch_status == "failed" or parse_status == "failed" or version is None:
            error_count += 1
        payload_items.append(
            {
                "projection_item_id": int(item.id),
                "canonical_identity_key": str(item.canonical_identity_key or ""),
                "title": title or str(item.canonical_identity_key or item.normalized_url or "—"),
                "normalized_url": str(item.normalized_url or ""),
                "selected_document_version_id": int(item.selected_document_version_id or 0),
                "selected_source_set_key": str(item.selected_source_set_key or ""),
                "selected_revision": int(item.selected_revision or 0),
                "precedence_rank": int(item.precedence_rank or 0),
                "status": str(item.status or "candidate"),
                "has_content": has_content,
                "preview_excerpt": preview_text,
                "updated_at": updated_at,
                "fetch_status": fetch_status,
                "parse_status": parse_status,
                "contributor_count": int(item.contributor_count or 0),
                "provenance_json": dict(item.provenance_json or {}),
            }
        )
    return payload_items, {
        "run": _serialize_run(run),
        "count": len(payload_items),
        "with_content": with_content,
        "missing_content": missing_content,
        "error_count": error_count,
        "last_updated_at": last_updated_at,
    }


def _active_runtime_law_items_payload(
    *,
    law_sets_store: RuntimeLawSetsStore,
    active_law_set_id: int | None,
) -> list[dict[str, Any]]:
    if not active_law_set_id:
        return []
    try:
        detail = law_sets_store.get_law_set_detail(law_set_id=int(active_law_set_id))
    except Exception:
        return []
    items = detail.get("items") if isinstance(detail, dict) else []
    payload_items: list[dict[str, Any]] = []
    for item in items or []:
        law_code = str((item or {}).get("law_code") or "").strip().lower()
        if not law_code:
            continue
        payload_items.append(
            {
                "law_code": law_code,
                "priority": int((item or {}).get("priority") or 0),
                "effective_from": str((item or {}).get("effective_from") or ""),
                "source_name": str((item or {}).get("source_name") or ""),
                "source_url": str((item or {}).get("source_url") or ""),
            }
        )
    return payload_items


def _runtime_item_parity_summary(
    *,
    active_runtime_items: list[dict[str, Any]],
    projection_items: list[dict[str, Any]],
) -> dict[str, Any]:
    active_keys = {
        str(item.get("law_code") or "").strip().lower()
        for item in active_runtime_items
        if str(item.get("law_code") or "").strip()
    }
    projected_keys = {
        str(getattr(item, "canonical_identity_key", "") or "").strip().lower()
        for item in projection_items
        if str(getattr(item, "canonical_identity_key", "") or "").strip()
    }
    shared = active_keys & projected_keys
    runtime_only = active_keys - projected_keys
    projection_only = projected_keys - active_keys
    runtime_only_keys = sorted(runtime_only)
    projection_only_keys = sorted(projection_only)
    runtime_only_sample = runtime_only_keys[:3]
    projection_only_sample = projection_only_keys[:3]
    drift_parts: list[str] = []
    if runtime_only_sample:
        drift_parts.append(f"runtime_only: {', '.join(runtime_only_sample)}")
    if projection_only_sample:
        drift_parts.append(f"projection_only: {', '.join(projection_only_sample)}")
    if active_keys and projected_keys and not runtime_only and not projection_only:
        status = "aligned"
        detail = "Active runtime law shell matches the latest projection by law identity."
    elif active_keys or projected_keys:
        status = "drift"
        detail = "Active runtime law shell and latest projection differ by law identity."
    else:
        status = "uninitialized"
        detail = "There is not enough runtime or projection data to compare law identity sets."
    return {
        "status": status,
        "detail": detail,
        "runtime_count": len(active_keys),
        "projection_count": len(projected_keys),
        "shared_count": len(shared),
        "runtime_only_count": len(runtime_only),
        "projection_only_count": len(projection_only),
        "runtime_only_keys": runtime_only_keys,
        "projection_only_keys": projection_only_keys,
        "runtime_only_sample": runtime_only_sample,
        "projection_only_sample": projection_only_sample,
        "drift_summary": "; ".join(drift_parts),
    }


def _runtime_version_parity_summary(*, health_payload: dict[str, Any]) -> dict[str, Any]:
    runtime_alignment = dict((health_payload or {}).get("runtime_alignment") or {})
    runtime_provenance = dict((health_payload or {}).get("runtime_provenance") or {})
    projection_bridge = dict((health_payload or {}).get("projection_bridge") or {})
    active_law_set_id = int(runtime_alignment.get("active_law_set_id") or 0)
    active_law_version_id = int(runtime_alignment.get("active_law_version_id") or 0)
    projected_law_set_id = int(runtime_alignment.get("projected_law_set_id") or 0)
    projected_law_version_id = int(runtime_alignment.get("projected_law_version_id") or 0)
    projection_run_id = int(runtime_alignment.get("projection_run_id") or projection_bridge.get("run_id") or 0)

    if projected_law_version_id > 0 and active_law_version_id > 0 and projected_law_version_id == active_law_version_id:
        status = "aligned"
        detail = "Promoted projection law_version matches the current active runtime law_version."
    elif projected_law_version_id > 0 and active_law_version_id > 0:
        status = "drift"
        detail = "Promoted projection law_version and active runtime law_version differ."
    elif active_law_version_id > 0:
        status = "legacy_only"
        detail = "Active runtime law_version exists without a promoted projection law_version."
    elif projected_law_version_id > 0 or projected_law_set_id > 0 or projection_run_id > 0:
        status = "pending_activation"
        detail = "Promoted projection exists, but there is no active runtime law_version yet."
    else:
        status = "uninitialized"
        detail = "There is not enough runtime/projection version data to compare law_version parity."

    drift_summary = ""
    shell_artifact_present = bool(active_law_set_id or projected_law_set_id)
    if status in {"drift", "legacy_only", "pending_activation"}:
        drift_parts: list[str] = []
        if active_law_version_id > 0:
            drift_parts.append(f"active_version={active_law_version_id}")
        if projected_law_version_id > 0:
            drift_parts.append(f"projected_version={projected_law_version_id}")
        if not drift_parts and shell_artifact_present:
            drift_parts.append("runtime_shell_artifact_present")
        drift_summary = "; ".join(drift_parts)

    return {
        "status": status,
        "detail": detail,
        "active_law_set_id": active_law_set_id or None,
        "active_law_version_id": active_law_version_id or None,
        "projected_law_set_id": projected_law_set_id or None,
        "projected_law_version_id": projected_law_version_id or None,
        "projection_run_id": projection_run_id or None,
        "matches_active_law_version": (
            projected_law_version_id > 0 and active_law_version_id > 0 and projected_law_version_id == active_law_version_id
        ),
        "law_set_observational_only": True,
        "shell_artifact_present": shell_artifact_present,
        "shell_role": str(runtime_alignment.get("shell_role") or runtime_provenance.get("shell_role") or "").strip().lower() or None,
        "shell_stage": str(runtime_alignment.get("shell_stage") or runtime_provenance.get("shell_stage") or "").strip().lower() or None,
        "drift_summary": drift_summary,
    }


def _projection_bridge_lifecycle_summary(*, health_payload: dict[str, Any]) -> dict[str, Any]:
    projection_bridge = dict((health_payload or {}).get("projection_bridge") or {})
    runtime_alignment = dict((health_payload or {}).get("runtime_alignment") or {})
    runtime_provenance = dict((health_payload or {}).get("runtime_provenance") or {})
    run_id = int(projection_bridge.get("run_id") or 0)
    law_set_id = int(projection_bridge.get("law_set_id") or 0)
    law_version_id = int(projection_bridge.get("law_version_id") or 0)
    matches_active = bool(projection_bridge.get("matches_active_law_version"))
    active_law_version_id = int(runtime_alignment.get("active_law_version_id") or 0)
    runtime_mode = str(runtime_provenance.get("mode") or "").strip().lower()
    shell_role = str(runtime_provenance.get("shell_role") or "").strip().lower()
    shell_stage = str(runtime_provenance.get("shell_stage") or "").strip().lower()

    if run_id <= 0:
        status = "uninitialized"
        detail = "No promoted projection lifecycle is available for this server yet."
    elif law_version_id > 0 and matches_active:
        status = "activated"
        detail = "Projection bridge is activated and matches the current runtime law_version."
    elif law_version_id > 0:
        status = "drifted"
        detail = "Projection bridge has an activation record, but it no longer matches the current runtime law_version."
    elif law_set_id > 0:
        status = "materialized"
        detail = "Projection bridge materialized a runtime shell artifact, but no active runtime law_version is aligned yet."
    else:
        status = "preview_only"
        detail = "Projection bridge currently exists only as a preview/decision run without materialization."

    if runtime_mode == "materialized_shell_only" and law_set_id > 0 and law_version_id <= 0:
        status = "materialized"
    elif runtime_mode == "projection_drift" and law_version_id > 0 and active_law_version_id > 0 and law_version_id != active_law_version_id:
        status = "drifted"

    return {
        "status": status,
        "detail": detail,
        "run_id": run_id or None,
        "law_set_id": law_set_id or None,
        "law_version_id": law_version_id or None,
        "active_law_version_id": active_law_version_id or None,
        "matches_active_law_version": matches_active if law_version_id > 0 else None,
        "law_set_observational_only": True,
        "shell_artifact_present": bool(law_set_id),
        "shell_role": shell_role or None,
        "shell_stage": shell_stage or None,
    }


def build_projection_bridge_readiness_summary(
    *,
    binding_count: int,
    projection_bridge_lifecycle: dict[str, Any],
    runtime_version_parity: dict[str, Any],
    fill_summary: dict[str, Any] | None = None,
    latest_projection_run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    lifecycle_status = str((projection_bridge_lifecycle or {}).get("status") or "").strip().lower()
    version_status = str((runtime_version_parity or {}).get("status") or "").strip().lower()
    fill = dict(fill_summary or {})
    run = dict(latest_projection_run or {})
    selected_count = int(run.get("selected_count") or fill.get("count") or 0)
    with_content = int(fill.get("with_content") or 0)
    missing_content = int(fill.get("missing_content") or 0)
    error_count = int(fill.get("error_count") or 0)
    blockers: list[str] = []
    next_step = ""

    if int(binding_count or 0) <= 0:
        status = "not_configured"
        blockers.append("no_bindings")
        next_step = "Добавьте source set bindings для сервера."
        detail = "Server has no active source set bindings, so projection bridge cannot become ready."
    elif lifecycle_status == "uninitialized":
        status = "action_required"
        blockers.append("preview_missing")
        next_step = "Запустите безопасный preview, чтобы создать projection run."
        detail = "No promoted projection lifecycle exists yet for this server."
    elif lifecycle_status == "preview_only":
        status = "action_required"
        blockers.append("activation_pending")
        next_step = "Проверьте preview и продолжайте bridge через materialize/activate path, когда это допустимо."
        detail = "Projection preview exists, but the bridge has not been materialized or activated yet."
    elif lifecycle_status == "materialized":
        status = "action_required"
        blockers.append("activation_pending")
        next_step = "Проверьте materialized shell и завершите activation bridge, когда это допустимо."
        detail = "Projection bridge materialized a runtime shell, but no active runtime law_version is aligned yet."
    elif lifecycle_status == "drifted" or version_status in {"drift", "legacy_only", "pending_activation"}:
        status = "action_required"
        blockers.append("runtime_drift")
        next_step = "Сверьте active runtime shell с latest promoted projection и выполните безопасный recheck."
        detail = "Runtime and promoted projection no longer align cleanly."
    elif error_count > 0:
        status = "action_required"
        blockers.append("content_errors")
        next_step = "Исправьте fetch/parse errors перед дальнейшим bridge-продвижением."
        detail = "Projection items still contain content errors."
    elif selected_count > 0 and missing_content > 0:
        status = "action_required"
        blockers.append("content_missing")
        next_step = "Проверьте наполнение и добейтесь content-ready состояния для selected laws."
        detail = "Some selected projection items still have missing content."
    else:
        status = "ready"
        next_step = "Bridge выглядит готовым для дальнейшей controlled promotion."
        detail = "Projection bridge readiness signals are green."

    return {
        "status": status,
        "detail": detail,
        "blockers": blockers,
        "next_step": next_step,
        "counters": {
            "binding_count": int(binding_count or 0),
            "selected_count": selected_count,
            "with_content": with_content,
            "missing_content": missing_content,
            "error_count": error_count,
        },
    }


def build_promotion_candidate_summary(
    *,
    diff_summary: dict[str, Any],
    fill_summary: dict[str, Any],
    projection_bridge_readiness: dict[str, Any],
    runtime_version_parity: dict[str, Any],
    latest_projection_run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    diff = dict(diff_summary or {})
    fill = dict(fill_summary or {})
    readiness = dict(projection_bridge_readiness or {})
    version_parity = dict(runtime_version_parity or {})
    run = dict(latest_projection_run or {})
    selected_count = int(run.get("selected_count") or fill.get("count") or 0)
    changed = int(diff.get("changed") or 0)
    added = int(diff.get("added") or 0)
    removed = int(diff.get("removed") or 0)
    missing_content = int(fill.get("missing_content") or 0)
    error_count = int(fill.get("error_count") or 0)
    with_content = int(fill.get("with_content") or 0)
    readiness_status = str(readiness.get("status") or "").strip().lower()
    version_status = str(version_parity.get("status") or "").strip().lower()

    if readiness_status in {"not_configured", "action_required"}:
        status = "blocked"
        detail = str(readiness.get("detail") or "Projection bridge is not ready for controlled promotion.")
        next_step = str(readiness.get("next_step") or "Устраните blockers перед controlled promotion.")
    elif selected_count <= 0 and readiness_status not in {"ready"}:
        status = "empty"
        detail = "Latest projection does not currently select any laws."
        next_step = "Проверьте bindings и запустите preview ещё раз."
    elif error_count > 0 or missing_content > 0:
        status = "content_incomplete"
        detail = "Latest projection still has missing content or content errors."
        next_step = "Проверьте наполнение и устраните content gaps."
    elif version_status not in {"aligned", "uninitialized"}:
        status = "runtime_drift"
        detail = "Runtime version parity still requires attention before controlled promotion."
        next_step = "Сверьте active runtime law_version с promoted projection."
    elif changed > 0 or added > 0 or removed > 0:
        status = "review_needed"
        detail = "Latest projection candidate differs from the previous baseline and should be reviewed."
        next_step = "Проверьте diff и подтвердите, что изменения ожидаемы."
    else:
        status = "ready"
        detail = "Latest projection candidate looks stable for the next controlled promotion step."
        next_step = "Кандидат выглядит готовым к controlled promotion."

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "counts": {
            "selected_count": selected_count,
            "with_content": with_content,
            "missing_content": missing_content,
            "error_count": error_count,
            "changed": changed,
            "added": added,
            "removed": removed,
        },
    }

def build_promotion_delta_summary(
    *,
    diff_summary: dict[str, Any],
    fill_summary: dict[str, Any],
    latest_projection_run: dict[str, Any] | None = None,
    projection_bridge_readiness: dict[str, Any] | None = None,
) -> dict[str, Any]:
    diff = dict(diff_summary or {})
    fill = dict(fill_summary or {})
    run = dict(latest_projection_run or {})
    readiness = dict(projection_bridge_readiness or {})
    selected_count = int(run.get("selected_count") or fill.get("count") or 0)
    added = int(diff.get("added") or 0)
    removed = int(diff.get("removed") or 0)
    changed = int(diff.get("changed") or 0)
    unchanged = int(diff.get("unchanged") or 0)
    missing_content = int(fill.get("missing_content") or 0)
    error_count = int(fill.get("error_count") or 0)
    with_content = int(fill.get("with_content") or 0)

    readiness_status = str(readiness.get("status") or "").strip().lower()

    if selected_count <= 0 and readiness_status == "action_required":
        status = "attention"
        detail = str(readiness.get("detail") or "Projection bridge still requires attention.")
    elif selected_count <= 0 and readiness_status == "ready":
        status = "stable"
        detail = "Projection bridge looks stable in the current read model."
    elif selected_count <= 0:
        status = "empty"
        detail = "Latest projection does not currently select any laws."
    elif added > 0 or removed > 0 or changed > 0 or missing_content > 0 or error_count > 0:
        status = "attention"
        detail = "Latest projection candidate has changes or content gaps that deserve review."
    else:
        status = "stable"
        detail = "Latest projection candidate has no visible delta or content gaps."

    return {
        "status": status,
        "detail": detail,
        "counts": {
            "selected_count": selected_count,
            "added": added,
            "removed": removed,
            "changed": changed,
            "unchanged": unchanged,
            "with_content": with_content,
            "missing_content": missing_content,
            "error_count": error_count,
        },
    }


def build_promotion_review_signal_summary(
    *,
    promotion_candidate: dict[str, Any],
    promotion_delta: dict[str, Any],
    promotion_blockers: dict[str, Any],
) -> dict[str, Any]:
    candidate = dict(promotion_candidate or {})
    delta = dict(promotion_delta or {})
    blockers = dict(promotion_blockers or {})

    candidate_status = str(candidate.get("status") or "").strip().lower()
    delta_status = str(delta.get("status") or "").strip().lower()
    blockers_status = str(blockers.get("status") or "").strip().lower()
    blocker_items = [
        dict(item)
        for item in list(blockers.get("items") or [])
        if isinstance(item, dict)
    ]
    advisory_items = [
        item
        for item in blocker_items
        if str(item.get("kind") or "").strip().lower() in {"candidate_review_needed", "delta_attention"}
    ]

    if blockers_status == "blocked":
        status = "deferred"
        detail = "Hard blockers still take priority over advisory promotion review."
        next_step = str(blockers.get("next_step") or "Сначала устраните hard blockers, затем вернитесь к review delta.").strip()
    elif blockers_status == "review" or candidate_status == "review_needed" or delta_status == "attention":
        status = "review"
        detail = "Only advisory promotion review signals remain in the current read model."
        next_step = str(candidate.get("next_step") or "Проверьте diff и подтвердите, что изменения ожидаемы.").strip()
    else:
        status = "stable"
        detail = "No standalone promotion review signal remains in the current read model."
        next_step = "Отдельных advisory review signal не видно."

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "counts": {
            "candidate_selected_count": int((candidate.get("counts") or {}).get("selected_count") or 0),
            "candidate_changed": int((candidate.get("counts") or {}).get("changed") or 0),
            "delta_added": int((delta.get("counts") or {}).get("added") or 0),
            "delta_removed": int((delta.get("counts") or {}).get("removed") or 0),
            "delta_changed": int((delta.get("counts") or {}).get("changed") or 0),
            "delta_missing_content": int((delta.get("counts") or {}).get("missing_content") or 0),
            "delta_error_count": int((delta.get("counts") or {}).get("error_count") or 0),
            "advisory_count": len(advisory_items),
        },
        "items": advisory_items[:4],
        "candidate_status": candidate_status,
        "delta_status": delta_status,
        "blockers_status": blockers_status,
    }


def build_promotion_blockers_summary(
    *,
    projection_bridge_readiness: dict[str, Any],
    promotion_candidate: dict[str, Any],
    promotion_delta: dict[str, Any],
    runtime_item_parity: dict[str, Any],
    runtime_version_parity: dict[str, Any],
    projection_bridge_lifecycle: dict[str, Any],
) -> dict[str, Any]:
    advisory_kinds = {"candidate_review_needed", "delta_attention"}
    readiness = dict(projection_bridge_readiness or {})
    candidate = dict(promotion_candidate or {})
    delta = dict(promotion_delta or {})
    item_parity = dict(runtime_item_parity or {})
    version_parity = dict(runtime_version_parity or {})
    lifecycle = dict(projection_bridge_lifecycle or {})

    blocker_items: list[dict[str, str]] = []
    for blocker in list(readiness.get("blockers") or []):
        normalized = str(blocker or "").strip().lower()
        if not normalized:
            continue
        blocker_items.append(
            {
                "kind": normalized,
                "title": normalized.replace("_", " "),
                "detail": str(readiness.get("detail") or "").strip(),
            }
        )

    candidate_status = str(candidate.get("status") or "").strip().lower()
    if candidate_status in {"content_incomplete", "runtime_drift", "review_needed"}:
        blocker_items.append(
            {
                "kind": f"candidate_{candidate_status}",
                "title": f"candidate {candidate_status.replace('_', ' ')}",
                "detail": str(candidate.get("detail") or "").strip(),
            }
        )

    if str(delta.get("status") or "").strip().lower() == "attention":
        blocker_items.append(
            {
                "kind": "delta_attention",
                "title": "delta attention",
                "detail": str(delta.get("detail") or "").strip(),
            }
        )

    if str(item_parity.get("status") or "").strip().lower() == "drift":
        blocker_items.append(
            {
                "kind": "item_parity_drift",
                "title": "item parity drift",
                "detail": str(item_parity.get("drift_summary") or item_parity.get("detail") or "").strip(),
            }
        )

    version_status = str(version_parity.get("status") or "").strip().lower()
    if version_status in {"drift", "legacy_only", "pending_activation"}:
        blocker_items.append(
            {
                "kind": f"version_{version_status}",
                "title": f"version {version_status.replace('_', ' ')}",
                "detail": str(version_parity.get("drift_summary") or version_parity.get("detail") or "").strip(),
            }
        )

    lifecycle_status = str(lifecycle.get("status") or "").strip().lower()
    if lifecycle_status in {"preview_only", "materialized", "drifted"}:
        blocker_items.append(
            {
                "kind": f"lifecycle_{lifecycle_status}",
                "title": f"lifecycle {lifecycle_status.replace('_', ' ')}",
                "detail": str(lifecycle.get("detail") or "").strip(),
            }
        )

    deduped_items: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in blocker_items:
        kind = str(item.get("kind") or "").strip().lower()
        if not kind or kind in seen:
            continue
        seen.add(kind)
        deduped_items.append(item)

    hard_items = [
        item for item in deduped_items
        if str(item.get("kind") or "").strip().lower() not in advisory_kinds
    ]

    if hard_items:
        status = "blocked"
        detail = f"{len(hard_items)} blocker(s) still require attention before runtime can look clean."
        next_step = str(readiness.get("next_step") or candidate.get("next_step") or "Проверьте blockers и выполните безопасный recheck.").strip()
    elif deduped_items:
        status = "review"
        detail = "Only advisory review signals remain before runtime can be considered clean."
        next_step = str(candidate.get("next_step") or "Проверьте diff и подтвердите, что изменения ожидаемы.").strip()
    else:
        status = "clear"
        detail = "No promotion blockers are visible in the current read model."
        next_step = "Критичных blockers не видно."

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "count": len(deduped_items),
        "hard_count": len(hard_items),
        "advisory_count": len(deduped_items) - len(hard_items),
        "items": deduped_items[:8],
    }


def build_activation_gap_summary(
    *,
    projection_bridge_readiness: dict[str, Any],
    runtime_version_parity: dict[str, Any],
    projection_bridge_lifecycle: dict[str, Any],
    promotion_blockers: dict[str, Any],
) -> dict[str, Any]:
    readiness = dict(projection_bridge_readiness or {})
    version_parity = dict(runtime_version_parity or {})
    lifecycle = dict(projection_bridge_lifecycle or {})
    blockers = dict(promotion_blockers or {})

    readiness_status = str(readiness.get("status") or "").strip().lower()
    version_status = str(version_parity.get("status") or "").strip().lower()
    lifecycle_status = str(lifecycle.get("status") or "").strip().lower()
    shell_stage = str(version_parity.get("shell_stage") or lifecycle.get("shell_stage") or "").strip().lower()

    if lifecycle_status == "activated" and version_status == "aligned":
        status = "closed"
        detail = "Latest promoted projection matches the active runtime shell."
        next_step = "Activation gap is closed."
    elif lifecycle_status in {"preview_only", "materialized"} or version_status in {"legacy_only", "pending_activation"}:
        status = "open"
        detail = "Latest promoted projection still has not reached the active runtime shell."
        next_step = str(readiness.get("next_step") or "Нужен controlled activation step после проверки кандидата.").strip()
    elif lifecycle_status == "drifted" or version_status == "drift":
        status = "drift"
        detail = "Active runtime shell no longer matches the promoted projection baseline."
        next_step = "Сверьте active runtime shell и promoted projection, затем выполните безопасный recheck."
    elif readiness_status == "not_configured":
        status = "not_ready"
        detail = str(readiness.get("detail") or "Projection bridge is not configured yet.")
        next_step = str(readiness.get("next_step") or "Сначала завершите настройку bindings и preview.").strip()
    elif str(blockers.get("status") or "").strip().lower() == "blocked":
        status = "blocked"
        detail = "Activation gap is still masked by upstream promotion blockers."
        next_step = str(blockers.get("next_step") or "Сначала снимите promotion blockers.").strip()
    else:
        status = "unknown"
        detail = "Activation gap could not be classified from the current read model."
        next_step = "Проверьте runtime parity и bridge lifecycle."

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "active_law_version_id": version_parity.get("active_law_version_id"),
        "projected_law_version_id": version_parity.get("projected_law_version_id"),
        "lifecycle_status": lifecycle_status,
        "version_status": version_status,
        "shell_stage": shell_stage or None,
    }


def build_runtime_shell_debt_summary(
    *,
    runtime_provenance: dict[str, Any],
    runtime_version_parity: dict[str, Any],
    projection_bridge_lifecycle: dict[str, Any],
    onboarding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    provenance = dict(runtime_provenance or {})
    version_parity = dict(runtime_version_parity or {})
    lifecycle = dict(projection_bridge_lifecycle or {})
    onboarding_payload = dict(onboarding or {})

    provenance_mode = str(provenance.get("mode") or "").strip().lower()
    version_status = str(version_parity.get("status") or "").strip().lower()
    lifecycle_status = str(lifecycle.get("status") or "").strip().lower()
    shell_stage = str(provenance.get("shell_stage") or version_parity.get("shell_stage") or lifecycle.get("shell_stage") or "").strip().lower()
    resolution_mode = str(onboarding_payload.get("resolution_mode") or "").strip().lower()

    reasons: list[str] = []
    if provenance_mode in {"legacy_runtime_shell", "materialized_shell_only", "projection_drift"}:
        reasons.append(provenance_mode)
    if version_status in {"legacy_only", "pending_activation", "drift"}:
        reasons.append(version_status)
    if lifecycle_status in {"preview_only", "materialized", "drifted"}:
        reasons.append(lifecycle_status)
    if resolution_mode in {"neutral_fallback", "bootstrap_pack"}:
        reasons.append(resolution_mode)

    deduped_reasons: list[str] = []
    seen: set[str] = set()
    for reason in reasons:
        normalized = str(reason or "").strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped_reasons.append(normalized)

    if not deduped_reasons:
        status = "low"
        detail = "Runtime shell debt looks low in the current read model."
        next_step = "Runtime shell artifact dependence is not currently a visible blocker."
    elif provenance_mode == "legacy_runtime_shell" or version_status == "legacy_only":
        status = "high"
        detail = "Runtime still depends heavily on the runtime shell artifact path."
        next_step = "Сведите зависимость к projection-backed runtime and a controlled activation path."
    else:
        status = "medium"
        detail = "Runtime still carries compatibility shell debt that deserves follow-up."
        next_step = "Сведите activation/provenance drift и проверьте runtime shell artifact dependence через безопасный recheck."

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "reason_count": len(deduped_reasons),
        "reasons": deduped_reasons[:8],
        "provenance_mode": provenance_mode,
        "version_status": version_status,
        "lifecycle_status": lifecycle_status,
        "shell_stage": shell_stage or None,
        "resolution_mode": resolution_mode,
    }


def build_runtime_convergence_summary(
    *,
    promotion_blockers: dict[str, Any],
    activation_gap: dict[str, Any],
    runtime_shell_debt: dict[str, Any],
) -> dict[str, Any]:
    blockers = dict(promotion_blockers or {})
    gap = dict(activation_gap or {})
    shell_debt = dict(runtime_shell_debt or {})

    blockers_status = str(blockers.get("status") or "").strip().lower()
    gap_status = str(gap.get("status") or "").strip().lower()
    shell_debt_status = str(shell_debt.get("status") or "").strip().lower()
    shell_role = str(gap.get("shell_role") or shell_debt.get("shell_role") or "").strip().lower()
    shell_stage = str(gap.get("shell_stage") or shell_debt.get("shell_stage") or "").strip().lower()

    if blockers_status in {"clear", "review"} and gap_status == "closed" and shell_debt_status == "low":
        status = "converged"
        detail = "Server looks close to a fully projection-backed runtime state."
        next_step = "Runtime convergence looks healthy."
    elif blockers_status == "blocked":
        status = "blocked"
        detail = "Upstream promotion blockers still prevent runtime convergence."
        next_step = str(blockers.get("next_step") or "Сначала снимите promotion blockers.").strip()
    elif blockers_status == "review":
        status = "advancing"
        detail = "Runtime looks converged, but the latest promotion delta still deserves operator review."
        next_step = str(blockers.get("next_step") or "Проверьте diff и подтвердите ожидаемые изменения.").strip()
    elif gap_status in {"open", "drift", "blocked"}:
        status = "activation_pending"
        detail = "Runtime convergence is still waiting on activation-side alignment."
        next_step = str(gap.get("next_step") or "Сначала закройте activation gap.").strip()
    elif shell_debt_status in {"high", "medium"}:
        status = "compatibility_mode"
        detail = "Runtime still converges through compatibility shell debt."
        next_step = str(shell_debt.get("next_step") or "Продолжайте сжимать legacy runtime shell dependence.").strip()
    else:
        status = "advancing"
        detail = "Runtime is moving toward convergence, but some compatibility signals remain."
        next_step = "Проверьте blockers, activation gap и shell debt."

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "blockers_status": blockers_status,
        "activation_gap_status": gap_status,
        "shell_debt_status": shell_debt_status,
        "shell_role": shell_role or None,
        "shell_stage": shell_stage or None,
    }


def build_cutover_readiness_summary(
    *,
    projection_bridge_readiness: dict[str, Any],
    runtime_convergence: dict[str, Any],
    runtime_shell_debt: dict[str, Any],
    activation_gap: dict[str, Any],
) -> dict[str, Any]:
    readiness = dict(projection_bridge_readiness or {})
    convergence = dict(runtime_convergence or {})
    shell_debt = dict(runtime_shell_debt or {})
    gap = dict(activation_gap or {})

    readiness_status = str(readiness.get("status") or "").strip().lower()
    convergence_status = str(convergence.get("status") or "").strip().lower()
    shell_debt_status = str(shell_debt.get("status") or "").strip().lower()
    gap_status = str(gap.get("status") or "").strip().lower()
    shell_role = str(convergence.get("shell_role") or gap.get("shell_role") or shell_debt.get("shell_role") or "").strip().lower()
    shell_stage = str(convergence.get("shell_stage") or gap.get("shell_stage") or shell_debt.get("shell_stage") or "").strip().lower()

    if convergence_status == "converged" and shell_debt_status == "low" and gap_status == "closed":
        status = "ready_for_cutover"
        detail = "Server looks ready for a controlled compatibility-bridge shrinking step."
        next_step = "Можно планировать controlled cutover review."
    elif readiness_status == "not_configured":
        status = "not_ready"
        detail = str(readiness.get("detail") or "Projection bridge is not configured yet.")
        next_step = str(readiness.get("next_step") or "Сначала завершите bindings и preview readiness.").strip()
    elif gap_status in {"open", "drift", "blocked"}:
        status = "needs_activation_alignment"
        detail = "Runtime still needs activation-side alignment before any cutover discussion."
        next_step = str(gap.get("next_step") or "Сначала закройте activation gap.").strip()
    elif shell_debt_status in {"high", "medium"}:
        status = "compatibility_dependent"
        detail = "Server still depends too much on compatibility shell behavior for cutover."
        next_step = str(shell_debt.get("next_step") or "Продолжайте сжимать runtime shell debt.").strip()
    elif convergence_status in {"blocked", "activation_pending", "compatibility_mode"}:
        status = "stabilize_first"
        detail = "Server still needs convergence stabilization before considering cutover."
        next_step = str(convergence.get("next_step") or "Сначала стабилизируйте runtime convergence.").strip()
    else:
        status = "monitor"
        detail = "Server is moving toward cutover readiness, but the current read model is not decisive yet."
        next_step = "Продолжайте следить за convergence, debt и activation gap."

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "readiness_status": readiness_status,
        "convergence_status": convergence_status,
        "shell_debt_status": shell_debt_status,
        "activation_gap_status": gap_status,
        "shell_role": shell_role or None,
        "shell_stage": shell_stage or None,
    }


def build_bridge_shrink_checklist_summary(
    *,
    projection_bridge_readiness: dict[str, Any],
    activation_gap: dict[str, Any],
    runtime_shell_debt: dict[str, Any],
    runtime_convergence: dict[str, Any],
    cutover_readiness: dict[str, Any],
) -> dict[str, Any]:
    readiness = dict(projection_bridge_readiness or {})
    gap = dict(activation_gap or {})
    shell_debt = dict(runtime_shell_debt or {})
    convergence = dict(runtime_convergence or {})
    cutover = dict(cutover_readiness or {})

    steps = [
        {
            "key": "bindings_and_preview_ready",
            "label": "Bindings and preview readiness",
            "done": str(readiness.get("status") or "").strip().lower() == "ready",
            "detail": str(readiness.get("detail") or "").strip(),
        },
        {
            "key": "activation_aligned",
            "label": "Activation alignment",
            "done": str(gap.get("status") or "").strip().lower() == "closed",
            "detail": str(gap.get("detail") or "").strip(),
        },
        {
            "key": "shell_debt_low",
            "label": "Low runtime shell debt",
            "done": str(shell_debt.get("status") or "").strip().lower() == "low",
            "detail": str(shell_debt.get("detail") or "").strip(),
        },
        {
            "key": "runtime_converged",
            "label": "Runtime convergence",
            "done": str(convergence.get("status") or "").strip().lower() == "converged",
            "detail": str(convergence.get("detail") or "").strip(),
        },
        {
            "key": "cutover_ready",
            "label": "Cutover readiness",
            "done": str(cutover.get("status") or "").strip().lower() == "ready_for_cutover",
            "detail": str(cutover.get("detail") or "").strip(),
        },
    ]
    completed = sum(1 for item in steps if bool(item.get("done")))
    total = len(steps)

    if completed >= total:
        status = "ready"
        detail = "Bridge shrink checklist is fully green for the current read model."
        next_step = "Можно обсуждать controlled bridge shrinking."
    elif completed <= 0:
        status = "blocked"
        detail = "Bridge shrink checklist is still blocked on every major step."
        next_step = "Начните с projection bridge readiness и activation alignment."
    else:
        status = "in_progress"
        detail = f"Bridge shrink checklist has {completed}/{total} steps completed."
        next_step = "Продолжайте закрывать незавершённые checklist items."

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "completed_count": completed,
        "total_count": total,
        "items": steps,
    }


def build_cutover_blockers_breakdown_summary(
    *,
    promotion_blockers: dict[str, Any],
    runtime_shell_debt: dict[str, Any],
    activation_gap: dict[str, Any],
    cutover_readiness: dict[str, Any],
) -> dict[str, Any]:
    advisory_kinds = {"candidate_review_needed", "delta_attention"}
    blockers = dict(promotion_blockers or {})
    shell_debt = dict(runtime_shell_debt or {})
    gap = dict(activation_gap or {})
    cutover = dict(cutover_readiness or {})

    items: list[dict[str, str]] = []
    for item in list(blockers.get("items") or []):
        kind = str(item.get("kind") or "").strip().lower()
        if not kind:
            continue
        if kind in advisory_kinds:
            continue
        items.append(
            {
                "category": "promotion",
                "kind": kind,
                "detail": str(item.get("detail") or "").strip(),
            }
        )

    for reason in list(shell_debt.get("reasons") or []):
        normalized = str(reason or "").strip().lower()
        if not normalized:
            continue
        items.append(
            {
                "category": "shell_debt",
                "kind": normalized,
                "detail": str(shell_debt.get("detail") or "").strip(),
            }
        )

    gap_status = str(gap.get("status") or "").strip().lower()
    if gap_status in {"open", "drift", "blocked", "not_ready"}:
        items.append(
            {
                "category": "activation",
                "kind": gap_status,
                "detail": str(gap.get("detail") or "").strip(),
            }
        )

    cutover_status = str(cutover.get("status") or "").strip().lower()
    if cutover_status not in {"", "ready_for_cutover", "monitor"}:
        items.append(
            {
                "category": "cutover",
                "kind": cutover_status,
                "detail": str(cutover.get("detail") or "").strip(),
            }
        )

    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        marker = (str(item.get("category") or ""), str(item.get("kind") or ""))
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(item)

    category_counts: dict[str, int] = {}
    for item in deduped:
        category = str(item.get("category") or "other")
        category_counts[category] = int(category_counts.get(category) or 0) + 1

    if deduped:
        status = "blocked"
        detail = f"{len(deduped)} cutover blocker(s) still require attention."
        next_step = str(cutover.get("next_step") or blockers.get("next_step") or "Сначала разберите blocker breakdown по категориям.").strip()
    else:
        status = "clear"
        detail = "No explicit cutover blockers are visible in the current read model."
        next_step = "Явных cutover blockers не видно."

    shell_role = str(gap.get("shell_role") or shell_debt.get("shell_role") or "").strip().lower()
    shell_stage = str(gap.get("shell_stage") or shell_debt.get("shell_stage") or "").strip().lower()

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "count": len(deduped),
        "category_counts": category_counts,
        "items": deduped[:10],
        "shell_role": shell_role or None,
        "shell_stage": shell_stage or None,
    }


def build_runtime_cutover_mode_summary(
    *,
    cutover_readiness: dict[str, Any],
    runtime_convergence: dict[str, Any],
    runtime_shell_debt: dict[str, Any],
    runtime_config_debt: dict[str, Any],
) -> dict[str, Any]:
    cutover = dict(cutover_readiness or {})
    convergence = dict(runtime_convergence or {})
    shell_debt = dict(runtime_shell_debt or {})
    config_debt = dict(runtime_config_debt or {})

    cutover_status = str(cutover.get("status") or "").strip().lower()
    convergence_status = str(convergence.get("status") or "").strip().lower()
    shell_debt_status = str(shell_debt.get("status") or "").strip().lower()
    config_debt_status = str(config_debt.get("status") or "").strip().lower()
    shell_role = str(convergence.get("shell_role") or shell_debt.get("shell_role") or "").strip().lower()
    shell_stage = str(convergence.get("shell_stage") or shell_debt.get("shell_stage") or "").strip().lower()
    config_path_role = str(config_debt.get("path_role") or "").strip().lower()
    config_path_stage = str(config_debt.get("path_stage") or "").strip().lower()

    if cutover_status == "ready_for_cutover" and convergence_status == "converged" and shell_debt_status == "low" and config_debt_status == "low":
        status = "projection_preferred"
        detail = "Server now looks suitable for a projection-preferred runtime posture."
        next_step = "Можно рассматривать controlled shrinking compatibility bridge для этого сервера."
    elif config_debt_status == "high" or cutover_status in {"compatibility_dependent", "needs_activation_alignment", "not_ready"}:
        status = "compatibility_mode"
        detail = "Server still depends on compatibility-era runtime paths."
        next_step = str(cutover.get("next_step") or config_debt.get("next_step") or "Сначала снимите compatibility dependencies.").strip()
    elif config_debt_status == "medium" or cutover_status in {"stabilize_first", "monitor"} or convergence_status in {"advancing", "compatibility_mode"}:
        status = "cutover_candidate"
        detail = "Server is moving toward projection-preferred runtime, but it is still transitional."
        next_step = str(cutover.get("next_step") or convergence.get("next_step") or "Продолжайте стабилизировать convergence и config path.").strip()
    else:
        status = "observe"
        detail = "Runtime cutover mode is not decisive yet in the current read model."
        next_step = "Продолжайте следить за cutover readiness, shell debt и config policy."

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "cutover_status": cutover_status,
        "convergence_status": convergence_status,
        "shell_debt_status": shell_debt_status,
        "config_debt_status": config_debt_status,
        "shell_role": shell_role or None,
        "shell_stage": shell_stage or None,
        "config_path_role": config_path_role or None,
        "config_path_stage": config_path_stage or None,
    }


def build_runtime_bridge_policy_summary(
    *,
    runtime_resolution_policy: dict[str, Any],
    runtime_cutover_mode: dict[str, Any],
    cutover_readiness: dict[str, Any],
) -> dict[str, Any]:
    resolution = dict(runtime_resolution_policy or {})
    cutover_mode = dict(runtime_cutover_mode or {})
    cutover = dict(cutover_readiness or {})

    resolution_status = str(resolution.get("status") or "").strip().lower()
    cutover_mode_status = str(cutover_mode.get("status") or "").strip().lower()
    cutover_status = str(cutover.get("status") or "").strip().lower()
    shell_role = str(cutover_mode.get("shell_role") or cutover.get("shell_role") or "").strip().lower()
    shell_stage = str(cutover_mode.get("shell_stage") or cutover.get("shell_stage") or "").strip().lower()
    config_path_role = str(resolution.get("path_role") or "").strip().lower()
    config_path_stage = str(resolution.get("path_stage") or "").strip().lower()

    if resolution_status == "declared_runtime" and cutover_mode_status == "projection_preferred":
        status = "prefer_projection_runtime"
        detail = "Server can now be treated as projection-preferred in runtime policy discussions."
        next_step = "Удерживайте projection-backed runtime как основной целевой режим для этого сервера."
    elif resolution_status == "compatibility_exception" or cutover_mode_status == "compatibility_mode" or cutover_status in {
        "compatibility_dependent",
        "needs_activation_alignment",
        "not_ready",
    }:
        status = "keep_compatibility"
        detail = "Server should stay on compatibility-oriented runtime policy until the remaining bridge debt is resolved."
        next_step = str(
            cutover_mode.get("next_step")
            or cutover.get("next_step")
            or resolution.get("next_step")
            or "Сохраняйте compatibility policy и продолжайте shrinking blockers."
        ).strip()
    elif resolution_status == "transitional_bootstrap" or cutover_mode_status in {"cutover_candidate", "observe"} or cutover_status in {
        "stabilize_first",
        "monitor",
    }:
        status = "stabilize_for_cutover"
        detail = "Server is transitional: keep stabilizing the bridge before changing runtime policy preference."
        next_step = str(
            cutover.get("next_step")
            or cutover_mode.get("next_step")
            or resolution.get("next_step")
            or "Сначала стабилизируйте cutover path, затем меняйте runtime policy."
        ).strip()
    else:
        status = "observe"
        detail = "Runtime bridge policy is not decisive yet in the current read model."
        next_step = "Продолжайте наблюдать resolution policy и cutover mode."

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "resolution_policy_status": resolution_status,
        "cutover_mode_status": cutover_mode_status,
        "cutover_readiness_status": cutover_status,
        "shell_role": shell_role or None,
        "shell_stage": shell_stage or None,
        "config_path_role": config_path_role or None,
        "config_path_stage": config_path_stage or None,
    }


def build_runtime_operating_mode_summary(
    *,
    runtime_bridge_policy: dict[str, Any],
    runtime_config_posture: dict[str, Any],
    runtime_provenance: dict[str, Any],
    runtime_cutover_mode: dict[str, Any],
) -> dict[str, Any]:
    bridge_policy = dict(runtime_bridge_policy or {})
    config_posture = dict(runtime_config_posture or {})
    provenance = dict(runtime_provenance or {})
    cutover_mode = dict(runtime_cutover_mode or {})

    bridge_policy_status = str(bridge_policy.get("status") or "").strip().lower()
    config_posture_status = str(config_posture.get("status") or "").strip().lower()
    provenance_mode = str(provenance.get("mode") or "").strip().lower()
    cutover_mode_status = str(cutover_mode.get("status") or "").strip().lower()
    shell_role = str(cutover_mode.get("shell_role") or provenance.get("shell_role") or "").strip().lower()
    shell_stage = str(cutover_mode.get("shell_stage") or provenance.get("shell_stage") or "").strip().lower()
    config_path_role = str(config_posture.get("path_role") or "").strip().lower()
    config_path_stage = str(config_posture.get("path_stage") or "").strip().lower()

    if (
        bridge_policy_status == "prefer_projection_runtime"
        and config_posture_status == "declared_ready"
        and provenance_mode == "projection_backed"
        and cutover_mode_status == "projection_preferred"
    ):
        status = "projection_runtime"
        detail = "Server is operating in a projection-first runtime mode in the current read model."
        next_step = "Сохраняйте projection-backed runtime как основной operating mode."
    elif bridge_policy_status == "keep_compatibility" or config_posture_status == "fallback_only":
        status = "compatibility_runtime"
        detail = "Server still operates in a compatibility-oriented runtime mode."
        next_step = str(
            bridge_policy.get("next_step")
            or config_posture.get("next_step")
            or "Сначала снимите compatibility dependencies."
        ).strip()
    elif (
        bridge_policy_status == "stabilize_for_cutover"
        or config_posture_status == "bootstrap_transition"
        or cutover_mode_status in {"cutover_candidate", "observe"}
    ):
        status = "transitional_runtime"
        detail = "Server is in a transitional runtime mode while cutover and config stabilization continue."
        next_step = str(
            bridge_policy.get("next_step")
            or cutover_mode.get("next_step")
            or config_posture.get("next_step")
            or "Продолжайте стабилизировать runtime bridge и config path."
        ).strip()
    else:
        status = "observe"
        detail = "Runtime operating mode is not decisive yet in the current read model."
        next_step = "Продолжайте наблюдать bridge policy, config posture и runtime provenance."

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "bridge_policy_status": bridge_policy_status,
        "config_posture_status": config_posture_status,
        "provenance_mode": provenance_mode,
        "cutover_mode_status": cutover_mode_status,
        "shell_role": shell_role or None,
        "shell_stage": shell_stage or None,
        "config_path_role": config_path_role or None,
        "config_path_stage": config_path_stage or None,
    }


def build_runtime_policy_violations_summary(
    *,
    runtime_bridge_policy: dict[str, Any],
    runtime_operating_mode: dict[str, Any],
    runtime_config_posture: dict[str, Any],
    runtime_provenance: dict[str, Any],
    runtime_shell_debt: dict[str, Any],
    cutover_readiness: dict[str, Any],
) -> dict[str, Any]:
    bridge_policy = dict(runtime_bridge_policy or {})
    operating_mode = dict(runtime_operating_mode or {})
    config_posture = dict(runtime_config_posture or {})
    provenance = dict(runtime_provenance or {})
    shell_debt = dict(runtime_shell_debt or {})
    cutover = dict(cutover_readiness or {})

    bridge_policy_status = str(bridge_policy.get("status") or "").strip().lower()
    operating_mode_status = str(operating_mode.get("status") or "").strip().lower()
    config_posture_status = str(config_posture.get("status") or "").strip().lower()
    provenance_mode = str(provenance.get("mode") or "").strip().lower()
    shell_debt_status = str(shell_debt.get("status") or "").strip().lower()
    cutover_status = str(cutover.get("status") or "").strip().lower()
    shell_role = str(operating_mode.get("shell_role") or shell_debt.get("shell_role") or provenance.get("shell_role") or "").strip().lower()
    shell_stage = str(operating_mode.get("shell_stage") or shell_debt.get("shell_stage") or provenance.get("shell_stage") or "").strip().lower()
    config_path_role = str(config_posture.get("path_role") or "").strip().lower()
    config_path_stage = str(config_posture.get("path_stage") or "").strip().lower()

    items: list[dict[str, str]] = []

    if bridge_policy_status == "prefer_projection_runtime" and config_posture_status != "declared_ready":
        items.append(
            {
                "kind": "projection_policy_requires_declared_runtime",
                "detail": "Projection-preferred policy is set while config posture is not declared-ready.",
            }
        )
    if bridge_policy_status == "prefer_projection_runtime" and provenance_mode != "projection_backed":
        items.append(
            {
                "kind": "projection_policy_without_projection_runtime",
                "detail": "Projection-preferred policy is set while runtime provenance is not projection-backed.",
            }
        )
    if bridge_policy_status == "prefer_projection_runtime" and shell_debt_status != "low":
        items.append(
            {
                "kind": "projection_policy_with_shell_debt",
                "detail": "Projection-preferred policy is set while runtime shell debt is not low.",
            }
        )
    if bridge_policy_status == "prefer_projection_runtime" and cutover_status != "ready_for_cutover":
        items.append(
            {
                "kind": "projection_policy_without_cutover_readiness",
                "detail": "Projection-preferred policy is set while cutover readiness is not fully green.",
            }
        )
    if operating_mode_status == "projection_runtime" and bridge_policy_status != "prefer_projection_runtime":
        items.append(
            {
                "kind": "projection_runtime_without_projection_policy",
                "detail": "Projection runtime operating mode is visible without a matching projection-preferred bridge policy.",
            }
        )

    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        kind = str(item.get("kind") or "").strip().lower()
        if not kind or kind in seen:
            continue
        seen.add(kind)
        deduped.append(item)

    if deduped:
        status = "blocked"
        detail = f"{len(deduped)} runtime policy violation(s) still require attention."
        next_step = str(
            bridge_policy.get("next_step")
            or cutover.get("next_step")
            or "Сначала уберите policy violations перед дальнейшим cutover tightening."
        ).strip()
    else:
        status = "clear"
        detail = "No explicit runtime policy violations are visible in the current read model."
        next_step = "Явных policy violations не видно."

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "count": len(deduped),
        "items": deduped[:10],
        "bridge_policy_status": bridge_policy_status,
        "operating_mode_status": operating_mode_status,
        "shell_role": shell_role or None,
        "shell_stage": shell_stage or None,
        "config_path_role": config_path_role or None,
        "config_path_stage": config_path_stage or None,
    }


def build_cutover_guardrails_summary(
    *,
    runtime_bridge_policy: dict[str, Any],
    runtime_operating_mode: dict[str, Any],
    runtime_policy_violations: dict[str, Any],
    cutover_readiness: dict[str, Any],
) -> dict[str, Any]:
    bridge_policy = dict(runtime_bridge_policy or {})
    operating_mode = dict(runtime_operating_mode or {})
    violations = dict(runtime_policy_violations or {})
    cutover = dict(cutover_readiness or {})

    bridge_policy_status = str(bridge_policy.get("status") or "").strip().lower()
    operating_mode_status = str(operating_mode.get("status") or "").strip().lower()
    violations_status = str(violations.get("status") or "").strip().lower()
    cutover_status = str(cutover.get("status") or "").strip().lower()
    shell_role = str(operating_mode.get("shell_role") or bridge_policy.get("shell_role") or "").strip().lower()
    shell_stage = str(operating_mode.get("shell_stage") or bridge_policy.get("shell_stage") or "").strip().lower()

    if bridge_policy_status == "prefer_projection_runtime" and violations_status == "clear" and cutover_status == "ready_for_cutover":
        status = "enforced"
        detail = "Cutover guardrails are aligned with a projection-preferred runtime policy."
        next_step = "Не допускайте деградации сервера обратно в transitional or compatibility paths."
    elif bridge_policy_status == "keep_compatibility":
        status = "compatibility_guardrails"
        detail = "Guardrails still require compatibility-oriented runtime constraints."
        next_step = str(bridge_policy.get("next_step") or "Сначала снимите compatibility dependencies.").strip()
    elif violations_status == "blocked" or cutover_status not in {"ready_for_cutover", "monitor"} or operating_mode_status == "transitional_runtime":
        status = "hold"
        detail = "Cutover guardrails should still hold the server in a transitional state."
        next_step = str(
            violations.get("next_step")
            or cutover.get("next_step")
            or bridge_policy.get("next_step")
            or "Сначала снимите violations и стабилизируйте cutover path."
        ).strip()
    else:
        status = "observe"
        detail = "Cutover guardrails are not decisive yet in the current read model."
        next_step = "Продолжайте наблюдать policy violations и operating mode."

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "bridge_policy_status": bridge_policy_status,
        "operating_mode_status": operating_mode_status,
        "violations_status": violations_status,
        "cutover_status": cutover_status,
        "shell_role": shell_role or None,
        "shell_stage": shell_stage or None,
    }


def build_runtime_policy_enforcement_summary(
    *,
    runtime_bridge_policy: dict[str, Any],
    runtime_operating_mode: dict[str, Any],
    runtime_policy_violations: dict[str, Any],
    cutover_guardrails: dict[str, Any],
) -> dict[str, Any]:
    bridge_policy = dict(runtime_bridge_policy or {})
    operating_mode = dict(runtime_operating_mode or {})
    violations = dict(runtime_policy_violations or {})
    guardrails = dict(cutover_guardrails or {})

    bridge_policy_status = str(bridge_policy.get("status") or "").strip().lower()
    operating_mode_status = str(operating_mode.get("status") or "").strip().lower()
    violations_status = str(violations.get("status") or "").strip().lower()
    guardrails_status = str(guardrails.get("status") or "").strip().lower()
    shell_role = str(operating_mode.get("shell_role") or bridge_policy.get("shell_role") or "").strip().lower()
    shell_stage = str(operating_mode.get("shell_stage") or bridge_policy.get("shell_stage") or "").strip().lower()

    if bridge_policy_status == "prefer_projection_runtime" and violations_status == "clear" and guardrails_status == "enforced":
        status = "enforced"
        detail = "Projection-preferred runtime policy is actively enforced for this server."
        next_step = "Поддерживайте текущий projection-first runtime posture без деградации в compatibility paths."
    elif bridge_policy_status == "prefer_projection_runtime" and violations_status == "blocked":
        status = "violated"
        detail = "Server violates its projection-preferred runtime policy in the current read model."
        next_step = str(
            violations.get("next_step")
            or guardrails.get("next_step")
            or "Сначала снимите policy violations и восстановите projection guardrails."
        ).strip()
    elif bridge_policy_status == "stabilize_for_cutover" or guardrails_status == "hold":
        status = "pre_enforcement"
        detail = "Server is still in a pre-enforcement runtime policy stage."
        next_step = str(
            guardrails.get("next_step")
            or bridge_policy.get("next_step")
            or "Сначала стабилизируйте cutover path, затем переходите к strict policy enforcement."
        ).strip()
    elif bridge_policy_status == "keep_compatibility" or operating_mode_status == "compatibility_runtime":
        status = "compatibility_hold"
        detail = "Runtime policy still intentionally holds this server in compatibility mode."
        next_step = str(
            bridge_policy.get("next_step")
            or operating_mode.get("next_step")
            or "Сначала снимите compatibility dependencies."
        ).strip()
    else:
        status = "observe"
        detail = "Runtime policy enforcement is not decisive yet in the current read model."
        next_step = "Продолжайте наблюдать violations, guardrails и operating mode."

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "bridge_policy_status": bridge_policy_status,
        "operating_mode_status": operating_mode_status,
        "violations_status": violations_status,
        "guardrails_status": guardrails_status,
        "shell_role": shell_role or None,
        "shell_stage": shell_stage or None,
    }


def build_policy_breach_summary(
    *,
    runtime_bridge_policy: dict[str, Any],
    runtime_operating_mode: dict[str, Any],
    runtime_policy_violations: dict[str, Any],
    runtime_policy_enforcement: dict[str, Any],
) -> dict[str, Any]:
    bridge_policy = dict(runtime_bridge_policy or {})
    operating_mode = dict(runtime_operating_mode or {})
    violations = dict(runtime_policy_violations or {})
    enforcement = dict(runtime_policy_enforcement or {})

    bridge_policy_status = str(bridge_policy.get("status") or "").strip().lower()
    operating_mode_status = str(operating_mode.get("status") or "").strip().lower()
    violations_status = str(violations.get("status") or "").strip().lower()
    enforcement_status = str(enforcement.get("status") or "").strip().lower()
    shell_role = str(operating_mode.get("shell_role") or bridge_policy.get("shell_role") or "").strip().lower()
    shell_stage = str(operating_mode.get("shell_stage") or bridge_policy.get("shell_stage") or "").strip().lower()

    if enforcement_status == "violated":
        status = "breached"
        detail = "Runtime policy is currently breached for this server."
        next_step = str(
            enforcement.get("next_step")
            or violations.get("next_step")
            or "Сначала снимите policy violations и восстановите runtime policy alignment."
        ).strip()
    elif bridge_policy_status == "prefer_projection_runtime" and (
        operating_mode_status != "projection_runtime" or violations_status == "blocked"
    ):
        status = "risk_of_breach"
        detail = "Projection-preferred policy is at risk because the effective runtime state is not fully aligned yet."
        next_step = str(
            violations.get("next_step")
            or enforcement.get("next_step")
            or "Сначала закройте оставшиеся policy gaps before they become a hard breach."
        ).strip()
    else:
        status = "clear"
        detail = "No explicit policy breach is visible in the current read model."
        next_step = "Явных policy breaches не видно."

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "bridge_policy_status": bridge_policy_status,
        "operating_mode_status": operating_mode_status,
        "violations_status": violations_status,
        "enforcement_status": enforcement_status,
        "shell_role": shell_role or None,
        "shell_stage": shell_stage or None,
    }


def build_runtime_risk_register_summary(
    *,
    runtime_config_debt: dict[str, Any],
    runtime_shell_debt: dict[str, Any],
    runtime_policy_violations: dict[str, Any],
    runtime_policy_enforcement: dict[str, Any],
    policy_breach_summary: dict[str, Any],
    cutover_guardrails: dict[str, Any],
) -> dict[str, Any]:
    config_debt = dict(runtime_config_debt or {})
    shell_debt = dict(runtime_shell_debt or {})
    violations = dict(runtime_policy_violations or {})
    enforcement = dict(runtime_policy_enforcement or {})
    breach = dict(policy_breach_summary or {})
    guardrails = dict(cutover_guardrails or {})

    config_debt_status = str(config_debt.get("status") or "").strip().lower()
    shell_debt_status = str(shell_debt.get("status") or "").strip().lower()
    violations_status = str(violations.get("status") or "").strip().lower()
    enforcement_status = str(enforcement.get("status") or "").strip().lower()
    breach_status = str(breach.get("status") or "").strip().lower()
    guardrails_status = str(guardrails.get("status") or "").strip().lower()
    shell_role = str(shell_debt.get("shell_role") or "").strip().lower()
    shell_stage = str(shell_debt.get("shell_stage") or "").strip().lower()

    items: list[dict[str, str]] = []
    if config_debt_status in {"high", "medium"}:
        items.append({"kind": "config_debt", "severity": "high" if config_debt_status == "high" else "medium", "detail": str(config_debt.get("detail") or "").strip()})
    if shell_debt_status in {"high", "medium"}:
        items.append({"kind": "shell_debt", "severity": "high" if shell_debt_status == "high" else "medium", "detail": str(shell_debt.get("detail") or "").strip()})
    if violations_status == "blocked":
        items.append({"kind": "policy_violations", "severity": "high", "detail": str(violations.get("detail") or "").strip()})
    if breach_status == "breached":
        items.append({"kind": "policy_breach", "severity": "critical", "detail": str(breach.get("detail") or "").strip()})
    elif breach_status == "risk_of_breach":
        items.append({"kind": "policy_breach_risk", "severity": "medium", "detail": str(breach.get("detail") or "").strip()})
    if enforcement_status in {"pre_enforcement", "compatibility_hold"}:
        items.append({"kind": "enforcement_stage", "severity": "medium", "detail": str(enforcement.get("detail") or "").strip()})
    if guardrails_status in {"hold", "compatibility_guardrails"}:
        items.append({"kind": "guardrails_hold", "severity": "medium", "detail": str(guardrails.get("detail") or "").strip()})

    if any(item["severity"] == "critical" for item in items):
        status = "critical"
    elif any(item["severity"] == "high" for item in items):
        status = "high"
    elif items:
        status = "medium"
    else:
        status = "low"

    if items:
        detail = f"{len(items)} runtime risk item(s) are currently open."
        next_step = str(
            breach.get("next_step")
            or violations.get("next_step")
            or enforcement.get("next_step")
            or "Разберите открытые runtime risk items и сократите compatibility debt."
        ).strip()
    else:
        detail = "No explicit runtime risks are visible in the current read model."
        next_step = "Явных runtime risks не видно."

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "count": len(items),
        "items": items[:10],
        "breach_status": breach_status,
        "violations_status": violations_status,
        "enforcement_status": enforcement_status,
        "shell_role": shell_role or None,
        "shell_stage": shell_stage or None,
    }


def build_runtime_governance_contract_summary(
    *,
    runtime_bridge_policy: dict[str, Any],
    runtime_operating_mode: dict[str, Any],
    runtime_policy_enforcement: dict[str, Any],
    runtime_resolution_policy: dict[str, Any],
) -> dict[str, Any]:
    bridge_policy = dict(runtime_bridge_policy or {})
    operating_mode = dict(runtime_operating_mode or {})
    enforcement = dict(runtime_policy_enforcement or {})
    resolution = dict(runtime_resolution_policy or {})

    bridge_policy_status = str(bridge_policy.get("status") or "").strip().lower()
    operating_mode_status = str(operating_mode.get("status") or "").strip().lower()
    enforcement_status = str(enforcement.get("status") or "").strip().lower()
    resolution_status = str(resolution.get("status") or "").strip().lower()
    shell_role = str(operating_mode.get("shell_role") or bridge_policy.get("shell_role") or "").strip().lower()
    shell_stage = str(operating_mode.get("shell_stage") or bridge_policy.get("shell_stage") or "").strip().lower()

    if (
        bridge_policy_status == "prefer_projection_runtime"
        and operating_mode_status == "projection_runtime"
        and enforcement_status == "enforced"
        and resolution_status == "declared_runtime"
    ):
        status = "projection_contract"
        detail = "Server satisfies the declared projection-runtime governance contract in the current read model."
        next_step = "Удерживайте projection runtime contract и не допускайте возврата к compatibility paths."
    elif (
        bridge_policy_status == "keep_compatibility"
        or operating_mode_status == "compatibility_runtime"
        or enforcement_status == "compatibility_hold"
        or resolution_status == "compatibility_exception"
    ):
        status = "compatibility_contract"
        detail = "Server still operates under a compatibility-focused runtime governance contract."
        next_step = str(
            bridge_policy.get("next_step")
            or enforcement.get("next_step")
            or "Сначала снимите compatibility dependencies и стабилизируйте cutover path."
        ).strip()
    elif (
        bridge_policy_status == "stabilize_for_cutover"
        or operating_mode_status == "transitional_runtime"
        or enforcement_status == "pre_enforcement"
        or resolution_status == "transitional_bootstrap"
    ):
        status = "transitional_contract"
        detail = "Server is in a transitional runtime governance contract while compatibility debt is being shrunk."
        next_step = str(
            enforcement.get("next_step")
            or bridge_policy.get("next_step")
            or "Продолжайте shrinking blockers до projection-runtime contract."
        ).strip()
    else:
        status = "observe"
        detail = "Runtime governance contract is not decisive yet in the current read model."
        next_step = "Продолжайте наблюдать bridge policy, operating mode и enforcement."

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "bridge_policy_status": bridge_policy_status,
        "operating_mode_status": operating_mode_status,
        "enforcement_status": enforcement_status,
        "resolution_policy_status": resolution_status,
        "shell_role": shell_role or None,
        "shell_stage": shell_stage or None,
    }


def build_legacy_path_allowance_summary(
    *,
    runtime_governance_contract: dict[str, Any],
    runtime_resolution_policy: dict[str, Any],
    runtime_config_posture: dict[str, Any],
    runtime_operating_mode: dict[str, Any],
    runtime_shell_debt: dict[str, Any],
) -> dict[str, Any]:
    contract = dict(runtime_governance_contract or {})
    resolution = dict(runtime_resolution_policy or {})
    config_posture = dict(runtime_config_posture or {})
    operating_mode = dict(runtime_operating_mode or {})
    shell_debt = dict(runtime_shell_debt or {})

    contract_status = str(contract.get("status") or "").strip().lower()
    resolution_status = str(resolution.get("status") or "").strip().lower()
    config_posture_status = str(config_posture.get("status") or "").strip().lower()
    operating_mode_status = str(operating_mode.get("status") or "").strip().lower()
    shell_debt_status = str(shell_debt.get("status") or "").strip().lower()
    shell_role = str(operating_mode.get("shell_role") or shell_debt.get("shell_role") or "").strip().lower()
    shell_stage = str(operating_mode.get("shell_stage") or shell_debt.get("shell_stage") or "").strip().lower()
    config_path_role = str(resolution.get("path_role") or config_posture.get("path_role") or "").strip().lower()
    config_path_stage = str(resolution.get("path_stage") or config_posture.get("path_stage") or "").strip().lower()

    allowance_items: list[str] = []
    if resolution_status == "compatibility_exception":
        allowance_items.append("neutral_fallback")
    elif resolution_status == "transitional_bootstrap":
        allowance_items.append("bootstrap_pack")
    if operating_mode_status == "compatibility_runtime":
        allowance_items.append("runtime_shell_artifact")
    elif shell_debt_status in {"high", "medium"}:
        allowance_items.append("legacy_shell_debt")
    allowance_kinds = set(allowance_items)
    only_shell_artifact_allowance = bool(allowance_kinds) and allowance_kinds.issubset({"runtime_shell_artifact", "legacy_shell_debt"})

    if (
        contract_status == "projection_contract"
        and resolution_status == "declared_runtime"
        and config_posture_status == "declared_ready"
        and operating_mode_status == "projection_runtime"
        and shell_debt_status == "low"
    ):
        status = "denied"
        detail = "Legacy runtime paths should no longer be required for this server."
        next_step = "Сохраняйте legacy path allowance закрытым и отслеживайте только regressions."
    elif contract_status == "transitional_contract":
        status = "limited"
        detail = "Only transitional legacy paths should still be tolerated while cutover stabilizes."
        next_step = str(contract.get("next_step") or "Постепенно убирайте bootstrap/runtime-shell-artifact allowance.").strip()
    elif only_shell_artifact_allowance:
        status = "limited"
        detail = "Only runtime-shell-artifact carry remains tolerated while the last compatibility debt is being reduced."
        next_step = str(contract.get("next_step") or "Постепенно снимайте runtime shell artifact carry и доводите path allowance до denied.").strip()
    elif contract_status == "compatibility_contract" or allowance_items:
        status = "compatibility_allowed"
        detail = "Compatibility-era paths are still allowed for this server in the current runtime contract."
        next_step = str(contract.get("next_step") or "Сначала снимите compatibility dependencies.").strip()
    else:
        status = "observe"
        detail = "Legacy path allowance is not decisive yet in the current read model."
        next_step = "Продолжайте наблюдать resolution policy и shell debt."

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "allowed_paths": allowance_items[:10],
        "count": len(allowance_items),
        "contract_status": contract_status,
        "resolution_policy_status": resolution_status,
        "config_posture_status": config_posture_status,
        "operating_mode_status": operating_mode_status,
        "shell_debt_status": shell_debt_status,
        "shell_role": shell_role or None,
        "shell_stage": shell_stage or None,
        "config_path_role": config_path_role or None,
        "config_path_stage": config_path_stage or None,
    }


def build_compatibility_exit_scorecard_summary(
    *,
    bridge_shrink_checklist: dict[str, Any],
    cutover_blockers_breakdown: dict[str, Any],
    runtime_risk_register: dict[str, Any],
    policy_breach_summary: dict[str, Any],
    legacy_path_allowance: dict[str, Any],
) -> dict[str, Any]:
    checklist = dict(bridge_shrink_checklist or {})
    blockers = dict(cutover_blockers_breakdown or {})
    risk_register = dict(runtime_risk_register or {})
    breach = dict(policy_breach_summary or {})
    allowance = dict(legacy_path_allowance or {})

    checklist_status = str(checklist.get("status") or "").strip().lower()
    blockers_status = str(blockers.get("status") or "").strip().lower()
    risk_status = str(risk_register.get("status") or "").strip().lower()
    breach_status = str(breach.get("status") or "").strip().lower()
    allowance_status = str(allowance.get("status") or "").strip().lower()
    shell_role = str(risk_register.get("shell_role") or allowance.get("shell_role") or "").strip().lower()
    shell_stage = str(risk_register.get("shell_stage") or allowance.get("shell_stage") or "").strip().lower()

    if (
        checklist_status == "ready"
        and blockers_status == "clear"
        and risk_status == "low"
        and breach_status == "clear"
        and allowance_status == "denied"
    ):
        status = "ready_to_exit"
        detail = "Server looks ready to exit compatibility runtime handling in the current read model."
        next_step = "Используйте этот сервер как кандидат на controlled compatibility-bridge shrinking."
    elif checklist_status in {"in_progress", "ready"} and blockers_status != "clear":
        status = "exit_in_progress"
        detail = "Compatibility exit is underway, but blocker categories still require attention."
        next_step = str(blockers.get("next_step") or checklist.get("next_step") or "Закройте remaining blocker categories.").strip()
    elif allowance_status == "compatibility_allowed" or risk_status in {"critical", "high"} or breach_status == "breached":
        status = "not_ready"
        detail = "Server is not ready to exit compatibility paths yet."
        next_step = str(
            breach.get("next_step")
            or risk_register.get("next_step")
            or allowance.get("next_step")
            or "Сначала снимите runtime risks и compatibility allowances."
        ).strip()
    else:
        status = "observe"
        detail = "Compatibility exit scorecard is not decisive yet in the current read model."
        next_step = "Продолжайте наблюдать checklist, blockers, risk register и allowance."

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "checklist_status": checklist_status,
        "blockers_status": blockers_status,
        "risk_status": risk_status,
        "breach_status": breach_status,
        "allowance_status": allowance_status,
        "shell_role": shell_role or None,
        "shell_stage": shell_stage or None,
    }


def build_runtime_breach_categories_summary(
    *,
    runtime_policy_violations: dict[str, Any],
    runtime_risk_register: dict[str, Any],
    policy_breach_summary: dict[str, Any],
    legacy_path_allowance: dict[str, Any],
    cutover_blockers_breakdown: dict[str, Any],
) -> dict[str, Any]:
    violations = dict(runtime_policy_violations or {})
    risk_register = dict(runtime_risk_register or {})
    breach = dict(policy_breach_summary or {})
    allowance = dict(legacy_path_allowance or {})
    blockers = dict(cutover_blockers_breakdown or {})

    category_counts = {"config": 0, "legacy_path": 0, "policy": 0, "cutover": 0}
    items: list[dict[str, str]] = []

    allowance_status = str(allowance.get("status") or "").strip().lower()
    if allowance_status in {"compatibility_allowed", "limited"}:
        category_counts["legacy_path"] += max(1, int(allowance.get("count") or 0))
        items.append({"category": "legacy_path", "detail": str(allowance.get("detail") or "").strip()})

    for item in list(violations.get("items") or []):
        kind = str((item or {}).get("kind") or "").strip().lower()
        detail = str((item or {}).get("detail") or "").strip()
        if "declared_runtime" in kind:
            category_counts["config"] += 1
            items.append({"category": "config", "detail": detail})
        elif "projection_policy" in kind or "policy" in kind:
            category_counts["policy"] += 1
            items.append({"category": "policy", "detail": detail})
        else:
            category_counts["cutover"] += 1
            items.append({"category": "cutover", "detail": detail})

    breach_status = str(breach.get("status") or "").strip().lower()
    if breach_status in {"risk_of_breach", "breached"}:
        category_counts["policy"] += 1
        items.append({"category": "policy", "detail": str(breach.get("detail") or "").strip()})

    for item in list(risk_register.get("items") or []):
        kind = str((item or {}).get("kind") or "").strip().lower()
        detail = str((item or {}).get("detail") or "").strip()
        if kind == "config_debt":
            category_counts["config"] += 1
            items.append({"category": "config", "detail": detail})
        elif kind in {"shell_debt", "guardrails_hold"}:
            category_counts["legacy_path"] += 1
            items.append({"category": "legacy_path", "detail": detail})
        elif kind in {"policy_violations", "policy_breach", "policy_breach_risk", "enforcement_stage"}:
            category_counts["policy"] += 1
            items.append({"category": "policy", "detail": detail})

    blocker_counts = dict(blockers.get("category_counts") or {})
    category_counts["cutover"] += int(blocker_counts.get("promotion") or 0) + int(blocker_counts.get("activation") or 0) + int(blocker_counts.get("cutover") or 0)
    category_counts["legacy_path"] += int(blocker_counts.get("shell_debt") or 0)

    total = sum(category_counts.values())
    if breach_status == "breached":
        status = "breached"
        detail = "At least one runtime breach category is already in a breached state."
        next_step = str(breach.get("next_step") or "Сначала снимите hard policy breach.").strip()
    elif total > 0:
        status = "attention"
        detail = f"{total} runtime breach-category signal(s) still require attention."
        next_step = str(
            blockers.get("next_step")
            or risk_register.get("next_step")
            or allowance.get("next_step")
            or "Разберите category-level runtime risks перед дальнейшим shrinking."
        ).strip()
    else:
        status = "clear"
        detail = "No explicit runtime breach categories are visible in the current read model."
        next_step = "Явных runtime breach categories не видно."

    shell_role = str(risk_register.get("shell_role") or allowance.get("shell_role") or "").strip().lower()
    shell_stage = str(risk_register.get("shell_stage") or allowance.get("shell_stage") or "").strip().lower()

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "count": total,
        "category_counts": category_counts,
        "items": items[:10],
        "shell_role": shell_role or None,
        "shell_stage": shell_stage or None,
    }


def build_legacy_path_controls_summary(
    *,
    legacy_path_allowance: dict[str, Any],
    runtime_resolution_policy: dict[str, Any],
    runtime_operating_mode: dict[str, Any],
    runtime_governance_contract: dict[str, Any],
) -> dict[str, Any]:
    allowance = dict(legacy_path_allowance or {})
    resolution = dict(runtime_resolution_policy or {})
    operating_mode = dict(runtime_operating_mode or {})
    contract = dict(runtime_governance_contract or {})

    allowance_status = str(allowance.get("status") or "").strip().lower()
    resolution_status = str(resolution.get("status") or "").strip().lower()
    operating_mode_status = str(operating_mode.get("status") or "").strip().lower()
    contract_status = str(contract.get("status") or "").strip().lower()
    shell_role = str(operating_mode.get("shell_role") or allowance.get("shell_role") or "").strip().lower()
    shell_stage = str(operating_mode.get("shell_stage") or allowance.get("shell_stage") or "").strip().lower()
    config_path_role = str(resolution.get("path_role") or "").strip().lower()
    config_path_stage = str(resolution.get("path_stage") or "").strip().lower()

    control_items: list[dict[str, str]] = []

    def _control(path: str, status: str, detail: str) -> None:
        control_items.append({"path": path, "status": status, "detail": detail})

    if resolution_status == "compatibility_exception":
        _control("neutral_fallback", "allowed", "Neutral fallback is still tolerated under the current runtime contract.")
    elif contract_status == "projection_contract":
        _control("neutral_fallback", "blocked", "Neutral fallback should no longer be relied on for this server.")
    else:
        _control("neutral_fallback", "transition_only", "Neutral fallback should remain exceptional and temporary.")

    if resolution_status == "transitional_bootstrap":
        bootstrap_status = "transition_only" if contract_status != "compatibility_contract" else "allowed"
        _control("bootstrap_pack", bootstrap_status, "Bootstrap pack remains a transitional runtime-config path.")
    elif contract_status == "projection_contract":
        _control("bootstrap_pack", "blocked", "Bootstrap pack should no longer be part of the steady-state runtime path.")

    runtime_shell_limited_tail = (
        allowance_status == "limited"
        and shell_role == "runtime_shell_artifact"
        and resolution_status == "declared_runtime"
        and config_path_stage == "published"
    )

    if operating_mode_status == "compatibility_runtime" and not runtime_shell_limited_tail:
        _control("runtime_shell_artifact", "allowed", "Runtime shell artifact is still part of the active runtime contract.")
    elif runtime_shell_limited_tail:
        _control("runtime_shell_artifact", "transition_only", "Runtime shell artifact is the only remaining bounded transitional carry.")
    elif allowance_status in {"limited", "compatibility_allowed"}:
        _control("runtime_shell_artifact", "transition_only", "Runtime shell artifact should only remain as a transitional/rollback shell.")
    else:
        _control("runtime_shell_artifact", "blocked", "Runtime shell artifact should no longer be required as an active path.")

    blocked_count = sum(1 for item in control_items if item["status"] == "blocked")
    transition_only_count = sum(1 for item in control_items if item["status"] == "transition_only")
    allowed_count = sum(1 for item in control_items if item["status"] == "allowed")

    if allowed_count > 0:
        status = "compatibility_controls"
        detail = "Some legacy runtime paths are still explicitly allowed for this server."
        next_step = str(allowance.get("next_step") or "Сначала снимите compatibility allowances.").strip()
    elif transition_only_count > 0:
        status = "transition_controls"
        detail = "Legacy paths are limited to transitional use only in the current contract."
        next_step = str(contract.get("next_step") or "Доведите transitional controls до fully blocked state.").strip()
    elif blocked_count > 0:
        status = "projection_controls"
        detail = "Legacy runtime paths are blocked by the current projection-grade contract."
        next_step = "Поддерживайте blocked controls и отслеживайте только regressions."
    else:
        status = "observe"
        detail = "Legacy-path controls are not decisive yet in the current read model."
        next_step = "Продолжайте наблюдать allowance и governance contract."

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "count": len(control_items),
        "blocked_count": blocked_count,
        "transition_only_count": transition_only_count,
        "allowed_count": allowed_count,
        "items": control_items[:10],
        "shell_role": shell_role or None,
        "shell_stage": shell_stage or None,
        "config_path_role": config_path_role or None,
        "config_path_stage": config_path_stage or None,
    }


def build_projection_runtime_gate_summary(
    *,
    runtime_governance_contract: dict[str, Any],
    compatibility_exit_scorecard: dict[str, Any],
    runtime_policy_enforcement: dict[str, Any],
    runtime_breach_categories: dict[str, Any],
) -> dict[str, Any]:
    contract = dict(runtime_governance_contract or {})
    scorecard = dict(compatibility_exit_scorecard or {})
    enforcement = dict(runtime_policy_enforcement or {})
    breach_categories = dict(runtime_breach_categories or {})

    contract_status = str(contract.get("status") or "").strip().lower()
    scorecard_status = str(scorecard.get("status") or "").strip().lower()
    enforcement_status = str(enforcement.get("status") or "").strip().lower()
    breach_status = str(breach_categories.get("status") or "").strip().lower()
    shell_role = str(contract.get("shell_role") or scorecard.get("shell_role") or "").strip().lower()
    shell_stage = str(contract.get("shell_stage") or scorecard.get("shell_stage") or "").strip().lower()

    if (
        contract_status == "projection_contract"
        and scorecard_status == "ready_to_exit"
        and enforcement_status == "enforced"
        and breach_status == "clear"
    ):
        status = "open"
        detail = "Projection-runtime gate is open for this server in the current read model."
        next_step = "Используйте сервер как candidate для controlled compatibility shrinking."
    elif breach_status == "breached" or enforcement_status == "violated":
        status = "blocked"
        detail = "Projection-runtime gate is blocked by policy breach/enforcement failure."
        next_step = str(enforcement.get("next_step") or breach_categories.get("next_step") or "Сначала снимите hard breach.").strip()
    elif scorecard_status in {"exit_in_progress", "not_ready"} or contract_status in {"transitional_contract", "compatibility_contract"}:
        status = "guarded"
        detail = "Projection-runtime gate is still guarded while compatibility debt is being reduced."
        next_step = str(scorecard.get("next_step") or contract.get("next_step") or "Сначала закройте remaining exit blockers.").strip()
    else:
        status = "observe"
        detail = "Projection-runtime gate is not decisive yet in the current read model."
        next_step = "Продолжайте наблюдать governance contract и exit scorecard."

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "contract_status": contract_status,
        "scorecard_status": scorecard_status,
        "enforcement_status": enforcement_status,
        "breach_status": breach_status,
        "shell_role": shell_role or None,
        "shell_stage": shell_stage or None,
    }


def build_compatibility_shrink_decision_summary(
    *,
    projection_runtime_gate: dict[str, Any],
    legacy_path_controls: dict[str, Any],
    runtime_risk_register: dict[str, Any],
) -> dict[str, Any]:
    gate = dict(projection_runtime_gate or {})
    controls = dict(legacy_path_controls or {})
    risk_register = dict(runtime_risk_register or {})

    gate_status = str(gate.get("status") or "").strip().lower()
    controls_status = str(controls.get("status") or "").strip().lower()
    risk_status = str(risk_register.get("status") or "").strip().lower()
    shell_role = str(gate.get("shell_role") or controls.get("shell_role") or risk_register.get("shell_role") or "").strip().lower()
    shell_stage = str(gate.get("shell_stage") or controls.get("shell_stage") or risk_register.get("shell_stage") or "").strip().lower()

    artifact_tail_ready = (
        shell_role == "runtime_shell_artifact"
        and gate_status == "guarded"
        and controls_status == "transition_controls"
        and risk_status == "low"
    )

    if gate_status == "open" and controls_status == "projection_controls" and risk_status == "low":
        status = "shrink_now"
        detail = "Server is a clean candidate for the next controlled compatibility-path shrinking step."
        next_step = "Можно планировать следующий bounded bridge-shrinking step для этого сервера."
    elif artifact_tail_ready:
        status = "shrink_now"
        detail = "Only runtime-shell-artifact tail remains, so the next bounded shrinking step can target it directly."
        next_step = "Планируйте следующий bounded shrink step прямо на runtime shell artifact tail."
    elif gate_status == "guarded" and controls_status in {"transition_controls", "projection_controls"} and risk_status in {"medium", "low"}:
        status = "shrink_after_stabilization"
        detail = "Server is close to bridge shrinking, but still needs stabilization before the next control step."
        next_step = str(gate.get("next_step") or controls.get("next_step") or "Сначала закройте remaining transitional gaps.").strip()
    elif gate_status == "blocked" or controls_status == "compatibility_controls" or risk_status in {"critical", "high"}:
        status = "hold_compatibility"
        detail = "Server should remain on the current compatibility path until risks and control gaps are reduced."
        next_step = str(risk_register.get("next_step") or gate.get("next_step") or "Сначала снимите runtime risks и allowances.").strip()
    else:
        status = "observe"
        detail = "Compatibility-shrinking decision is not decisive yet in the current read model."
        next_step = "Продолжайте наблюдать gate, controls и runtime risks."

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "gate_status": gate_status,
        "controls_status": controls_status,
        "risk_status": risk_status,
        "shell_role": shell_role or None,
        "shell_stage": shell_stage or None,
    }


def build_runtime_exception_register_summary(
    *,
    legacy_path_allowance: dict[str, Any],
    runtime_policy_violations: dict[str, Any],
    runtime_breach_categories: dict[str, Any],
    compatibility_exit_scorecard: dict[str, Any],
) -> dict[str, Any]:
    allowance = dict(legacy_path_allowance or {})
    violations = dict(runtime_policy_violations or {})
    breach_categories = dict(runtime_breach_categories or {})
    scorecard = dict(compatibility_exit_scorecard or {})

    items: list[dict[str, str]] = []
    allowance_status = str(allowance.get("status") or "").strip().lower()
    if allowance_status in {"compatibility_allowed", "limited"}:
        for path in list(allowance.get("allowed_paths") or [])[:10]:
            normalized_path = str(path or "").strip().lower()
            if normalized_path == "runtime_shell_artifact":
                continue
            items.append({"kind": "legacy_path", "detail": normalized_path})

    for item in list(violations.get("items") or [])[:10]:
        detail = str((item or {}).get("detail") or "").strip()
        if detail:
            items.append({"kind": "policy_violation", "detail": detail})

    for item in list(breach_categories.get("items") or [])[:10]:
        detail = str((item or {}).get("detail") or "").strip()
        category = str((item or {}).get("category") or "breach")
        if detail:
            items.append({"kind": category, "detail": detail})

    scorecard_status = str(scorecard.get("status") or "").strip().lower()
    if scorecard_status in {"not_ready", "exit_in_progress"}:
        items.append({"kind": "exit_scorecard", "detail": str(scorecard.get("detail") or "").strip()})

    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (str(item.get("kind") or "").strip().lower(), str(item.get("detail") or "").strip())
        if not key[0] or not key[1] or key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    if deduped:
        status = "open"
        detail = f"{len(deduped)} runtime exception(s) are still explicitly carried by this server."
        next_step = str(
            scorecard.get("next_step")
            or breach_categories.get("next_step")
            or allowance.get("next_step")
            or "Постепенно закрывайте explicit runtime exceptions."
        ).strip()
    else:
        status = "clear"
        detail = "No explicit runtime exceptions are visible in the current read model."
        next_step = "Явных runtime exceptions не видно."

    shell_role = str(allowance.get("shell_role") or breach_categories.get("shell_role") or "").strip().lower()
    shell_stage = str(allowance.get("shell_stage") or breach_categories.get("shell_stage") or "").strip().lower()

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "count": len(deduped),
        "items": deduped[:10],
        "shell_role": shell_role or None,
        "shell_stage": shell_stage or None,
    }


def build_compatibility_path_matrix_summary(
    *,
    legacy_path_controls: dict[str, Any],
    runtime_resolution_policy: dict[str, Any],
    runtime_exception_register: dict[str, Any],
) -> dict[str, Any]:
    controls = dict(legacy_path_controls or {})
    resolution = dict(runtime_resolution_policy or {})
    exception_register = dict(runtime_exception_register or {})

    control_items = list(controls.get("items") or [])
    exception_items = list(exception_register.get("items") or [])
    resolution_status = str(resolution.get("status") or "").strip().lower()
    shell_role = str(controls.get("shell_role") or exception_register.get("shell_role") or "").strip().lower()
    shell_stage = str(controls.get("shell_stage") or exception_register.get("shell_stage") or "").strip().lower()
    config_path_role = str(resolution.get("path_role") or "").strip().lower()
    config_path_stage = str(resolution.get("path_stage") or "").strip().lower()

    def _find_control(path: str) -> dict[str, Any]:
        for item in control_items:
            if str((item or {}).get("path") or "").strip().lower() == path:
                return dict(item or {})
        return {}

    def _has_exception_fragment(fragment: str) -> bool:
        normalized_fragment = fragment.strip().lower()
        return any(normalized_fragment in str((item or {}).get("detail") or "").strip().lower() for item in exception_items)

    paths: list[dict[str, str]] = []

    for path_name in ("neutral_fallback", "bootstrap_pack", "runtime_shell_artifact"):
        control = _find_control(path_name)
        control_status = str(control.get("status") or "observe").strip().lower()
        detail = str(control.get("detail") or "").strip()

        if path_name == "neutral_fallback" and resolution_status == "compatibility_exception":
            path_status = "active_exception"
        elif path_name == "bootstrap_pack" and resolution_status == "transitional_bootstrap":
            path_status = "transition_path"
        elif path_name == "runtime_shell_artifact" and control_status == "allowed":
            path_status = "transition_path"
        elif control_status == "allowed":
            path_status = "active_exception"
        elif control_status == "transition_only":
            path_status = "transition_path"
        elif control_status == "blocked":
            path_status = "blocked"
        else:
            path_status = "observe"

        if path_name == "neutral_fallback" and _has_exception_fragment("fallback"):
            detail = detail or "Neutral fallback still appears in the carried runtime exceptions."
        if path_name == "bootstrap_pack" and _has_exception_fragment("bootstrap"):
            detail = detail or "Bootstrap pack still appears in the carried runtime exceptions."
        if path_name == "runtime_shell_artifact" and (_has_exception_fragment("legacy") or _has_exception_fragment("shell")):
            detail = detail or "Runtime shell artifact still appears in the carried runtime exceptions."

        paths.append(
            {
                "path": path_name,
                "status": path_status,
                "detail": detail or "No explicit detail is available for this compatibility path.",
            }
        )

    blocked_count = sum(1 for item in paths if item["status"] == "blocked")
    transition_count = sum(1 for item in paths if item["status"] == "transition_path")
    exception_count = sum(1 for item in paths if item["status"] == "active_exception")

    if exception_count > 0:
        status = "compatibility_matrix"
        detail = "Some compatibility paths are still active exceptions for this server."
        next_step = str(exception_register.get("next_step") or controls.get("next_step") or "Сначала снимите active exceptions из runtime paths.").strip()
    elif transition_count > 0:
        status = "transition_matrix"
        detail = "Compatibility paths are limited to bounded transitional use."
        next_step = str(controls.get("next_step") or "Доведите transitional paths до blocked state.").strip()
    elif blocked_count > 0:
        status = "projection_matrix"
        detail = "Compatibility paths are already blocked by the current runtime contract."
        next_step = "Поддерживайте blocked matrix и отслеживайте regressions."
    else:
        status = "observe"
        detail = "Compatibility-path matrix is not decisive yet in the current read model."
        next_step = "Продолжайте наблюдать compatibility-path controls."

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "blocked_count": blocked_count,
        "transition_count": transition_count,
        "exception_count": exception_count,
        "items": paths,
        "shell_role": shell_role or None,
        "shell_stage": shell_stage or None,
        "config_path_role": config_path_role or None,
        "config_path_stage": config_path_stage or None,
    }


def build_next_shrink_step_summary(
    *,
    compatibility_shrink_decision: dict[str, Any],
    compatibility_path_matrix: dict[str, Any],
    runtime_exception_register: dict[str, Any],
) -> dict[str, Any]:
    decision = dict(compatibility_shrink_decision or {})
    matrix = dict(compatibility_path_matrix or {})
    exception_register = dict(runtime_exception_register or {})

    decision_status = str(decision.get("status") or "").strip().lower()
    matrix_items = list(matrix.get("items") or [])
    exception_count = int(matrix.get("exception_count") or 0)
    transition_count = int(matrix.get("transition_count") or 0)
    shell_role = str(decision.get("shell_role") or matrix.get("shell_role") or "").strip().lower()
    shell_stage = str(decision.get("shell_stage") or matrix.get("shell_stage") or "").strip().lower()

    preferred_path = ""
    if shell_role == "runtime_shell_artifact":
        preferred_path = "runtime_shell_artifact"

    candidate: dict[str, Any] | None = None
    if preferred_path:
        for preferred_status in ("active_exception", "transition_path"):
            for item in matrix_items:
                if (
                    str((item or {}).get("path") or "").strip().lower() == preferred_path
                    and str((item or {}).get("status") or "").strip().lower() == preferred_status
                ):
                    candidate = dict(item or {})
                    break
            if candidate is not None:
                break

    for preferred_status in ("active_exception", "transition_path"):
        if candidate is None:
            for item in matrix_items:
                if str((item or {}).get("status") or "").strip().lower() == preferred_status:
                    candidate = dict(item or {})
                    break
        if candidate is not None:
            break

    if decision_status == "shrink_now" and candidate is not None:
        status = "ready_step"
        target_path = str(candidate.get("path") or "").strip()
        detail = f"Next bounded shrink step should target `{target_path}` first."
        next_step = f"Планируйте следующий bounded shrink step для `{target_path}`."
    elif decision_status == "shrink_after_stabilization" and candidate is not None:
        status = "stabilize_then_step"
        target_path = str(candidate.get("path") or "").strip()
        detail = f"Next shrink target is already visible, but `{target_path}` still needs stabilization first."
        next_step = str(decision.get("next_step") or matrix.get("next_step") or "Сначала стабилизируйте transitional path.").strip()
    elif decision_status == "hold_compatibility":
        status = "hold"
        target_path = ""
        detail = "No bounded shrink step should be taken yet while compatibility must still be held."
        next_step = str(decision.get("next_step") or exception_register.get("next_step") or "Сначала снимите compatibility hold.").strip()
    else:
        status = "observe"
        target_path = ""
        detail = "Next shrink step is not decisive yet in the current read model."
        next_step = "Продолжайте наблюдать matrix и shrink decision."

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "target_path": target_path,
        "exception_count": exception_count,
        "transition_count": transition_count,
        "shell_role": shell_role or None,
        "shell_stage": shell_stage or None,
    }


def build_shrink_sequence_summary(
    *,
    compatibility_path_matrix: dict[str, Any],
    next_shrink_step: dict[str, Any],
) -> dict[str, Any]:
    matrix = dict(compatibility_path_matrix or {})
    next_step = dict(next_shrink_step or {})

    matrix_items = list(matrix.get("items") or [])
    ordered_paths: list[dict[str, str]] = []
    for status_name in ("active_exception", "transition_path", "blocked", "observe"):
        for item in matrix_items:
            if str((item or {}).get("status") or "").strip().lower() != status_name:
                continue
            ordered_paths.append(
                {
                    "path": str((item or {}).get("path") or "").strip(),
                    "status": status_name,
                    "detail": str((item or {}).get("detail") or "").strip(),
                }
            )

    blocked_count = sum(1 for item in ordered_paths if item["status"] == "blocked")
    total_count = len(ordered_paths)
    ready_count = blocked_count
    shell_role = str(matrix.get("shell_role") or next_step.get("shell_role") or "").strip().lower()
    shell_stage = str(matrix.get("shell_stage") or next_step.get("shell_stage") or "").strip().lower()

    next_target = str(next_step.get("target_path") or "").strip()
    if next_target:
        detail = f"Shrink sequence is ordered and the next bounded target is `{next_target}`."
    else:
        detail = "Shrink sequence is ordered from carried exceptions to blocked paths."

    if total_count > 0 and ready_count == total_count:
        status = "complete"
        next_step_text = "Совместимость уже сведена к blocked paths в текущей матрице."
    elif next_target:
        status = "planned"
        next_step_text = str(next_step.get("next_step") or "Следуйте следующему bounded shrink step из sequence.").strip()
    elif any(item["status"] in {"active_exception", "transition_path"} for item in ordered_paths):
        status = "queued"
        next_step_text = str(matrix.get("next_step") or "Сначала соберите bounded shrink step по открытым paths.").strip()
    else:
        status = "observe"
        next_step_text = "Продолжайте наблюдать shrink sequence."

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step_text,
        "ready_count": ready_count,
        "total_count": total_count,
        "items": ordered_paths[:10],
        "shell_role": shell_role or None,
        "shell_stage": shell_stage or None,
    }


def build_server_laws_summary_payload(
    *,
    server_code: str,
    runtime_servers_store: RuntimeServersStore,
    law_sets_store: RuntimeLawSetsStore,
    source_sets_store: LawSourceSetsStore,
    projections_store: ServerEffectiveLawProjectionsStore,
    versions_store: CanonicalLawDocumentVersionsStore,
) -> dict[str, Any]:
    normalized_server = normalize_runtime_server_code(server_code)
    server = runtime_servers_store.get_server(code=normalized_server)
    if server is None:
        raise KeyError("server_not_found")
    health_payload = build_runtime_server_health_payload(
        server_code=normalized_server,
        runtime_servers_store=runtime_servers_store,
        law_sets_store=law_sets_store,
        source_sets_store=source_sets_store,
        projections_store=projections_store,
    )
    bindings_check = dict(((health_payload.get("checks") or {}).get("bindings") or {}))
    bindings = [
        _serialize_binding(item)
        for item in source_sets_store.list_bindings(server_code=normalized_server)
    ]
    current_run, previous_run = _latest_projection_runs(projections_store, server_code=normalized_server)
    _, fill_summary = _effective_items_payload(
        projections_store=projections_store,
        versions_store=versions_store,
        run=current_run,
    )
    current_items = projections_store.list_items(projection_run_id=int(current_run.id)) if current_run is not None else []
    previous_items = projections_store.list_items(projection_run_id=int(previous_run.id)) if previous_run is not None else []
    active_law_set_id = int(((health_payload.get("runtime_alignment") or {}).get("active_law_set_id") or 0))
    active_runtime_items = _active_runtime_law_items_payload(
        law_sets_store=law_sets_store,
        active_law_set_id=active_law_set_id or None,
    )
    runtime_item_parity = _runtime_item_parity_summary(
        active_runtime_items=active_runtime_items,
        projection_items=current_items,
    )
    runtime_version_parity = _runtime_version_parity_summary(health_payload=health_payload)
    projection_bridge_lifecycle = _projection_bridge_lifecycle_summary(health_payload=health_payload)
    bridge_readiness = build_projection_bridge_readiness_summary(
        binding_count=len(bindings),
        projection_bridge_lifecycle=projection_bridge_lifecycle,
        runtime_version_parity=runtime_version_parity,
        fill_summary=fill_summary,
        latest_projection_run=_serialize_run(current_run) or {},
    )
    diff_summary = _diff_summary(current_items, previous_items)
    diff_summary["current_run_id"] = int(current_run.id) if current_run is not None else None
    diff_summary["baseline_run_id"] = int(previous_run.id) if previous_run is not None else None
    promotion_candidate = build_promotion_candidate_summary(
        diff_summary=diff_summary,
        fill_summary=fill_summary,
        projection_bridge_readiness=bridge_readiness,
        runtime_version_parity=runtime_version_parity,
        latest_projection_run=_serialize_run(current_run) or {},
    )
    promotion_delta = build_promotion_delta_summary(
        diff_summary=diff_summary,
        fill_summary=fill_summary,
        latest_projection_run=_serialize_run(current_run) or {},
        projection_bridge_readiness=bridge_readiness,
    )
    promotion_blockers = build_promotion_blockers_summary(
        projection_bridge_readiness=bridge_readiness,
        promotion_candidate=promotion_candidate,
        promotion_delta=promotion_delta,
        runtime_item_parity=runtime_item_parity,
        runtime_version_parity=runtime_version_parity,
        projection_bridge_lifecycle=projection_bridge_lifecycle,
    )
    promotion_review_signal = build_promotion_review_signal_summary(
        promotion_candidate=promotion_candidate,
        promotion_delta=promotion_delta,
        promotion_blockers=promotion_blockers,
    )
    activation_gap = build_activation_gap_summary(
        projection_bridge_readiness=bridge_readiness,
        runtime_version_parity=runtime_version_parity,
        projection_bridge_lifecycle=projection_bridge_lifecycle,
        promotion_blockers=promotion_blockers,
    )
    runtime_shell_debt = build_runtime_shell_debt_summary(
        runtime_provenance=dict(health_payload.get("runtime_provenance") or {}),
        runtime_version_parity=runtime_version_parity,
        projection_bridge_lifecycle=projection_bridge_lifecycle,
        onboarding=dict(health_payload.get("onboarding") or {}),
    )
    runtime_convergence = build_runtime_convergence_summary(
        promotion_blockers=promotion_blockers,
        activation_gap=activation_gap,
        runtime_shell_debt=runtime_shell_debt,
    )
    cutover_readiness = build_cutover_readiness_summary(
        projection_bridge_readiness=bridge_readiness,
        runtime_convergence=runtime_convergence,
        runtime_shell_debt=runtime_shell_debt,
        activation_gap=activation_gap,
    )
    config_debt = dict((health_payload.get("runtime_config_debt") or {}))
    if not config_debt:
        config_debt = build_runtime_config_debt_summary(health_payload=health_payload)
    runtime_config_posture = dict((health_payload.get("runtime_config_posture") or {}))
    if not runtime_config_posture:
        runtime_config_posture = build_runtime_config_posture_summary(health_payload=health_payload)
    runtime_resolution_policy = dict((health_payload.get("runtime_resolution_policy") or {}))
    if not runtime_resolution_policy:
        runtime_resolution_policy = build_runtime_resolution_policy_summary(health_payload=health_payload)
    runtime_cutover_mode = build_runtime_cutover_mode_summary(
        cutover_readiness=cutover_readiness,
        runtime_convergence=runtime_convergence,
        runtime_shell_debt=runtime_shell_debt,
        runtime_config_debt=config_debt,
    )
    runtime_bridge_policy = build_runtime_bridge_policy_summary(
        runtime_resolution_policy=runtime_resolution_policy,
        runtime_cutover_mode=runtime_cutover_mode,
        cutover_readiness=cutover_readiness,
    )
    runtime_operating_mode = build_runtime_operating_mode_summary(
        runtime_bridge_policy=runtime_bridge_policy,
        runtime_config_posture=runtime_config_posture,
        runtime_provenance=dict(health_payload.get("runtime_provenance") or {}),
        runtime_cutover_mode=runtime_cutover_mode,
    )
    runtime_policy_violations = build_runtime_policy_violations_summary(
        runtime_bridge_policy=runtime_bridge_policy,
        runtime_operating_mode=runtime_operating_mode,
        runtime_config_posture=runtime_config_posture,
        runtime_provenance=dict(health_payload.get("runtime_provenance") or {}),
        runtime_shell_debt=runtime_shell_debt,
        cutover_readiness=cutover_readiness,
    )
    cutover_guardrails = build_cutover_guardrails_summary(
        runtime_bridge_policy=runtime_bridge_policy,
        runtime_operating_mode=runtime_operating_mode,
        runtime_policy_violations=runtime_policy_violations,
        cutover_readiness=cutover_readiness,
    )
    runtime_policy_enforcement = build_runtime_policy_enforcement_summary(
        runtime_bridge_policy=runtime_bridge_policy,
        runtime_operating_mode=runtime_operating_mode,
        runtime_policy_violations=runtime_policy_violations,
        cutover_guardrails=cutover_guardrails,
    )
    policy_breach_summary = build_policy_breach_summary(
        runtime_bridge_policy=runtime_bridge_policy,
        runtime_operating_mode=runtime_operating_mode,
        runtime_policy_violations=runtime_policy_violations,
        runtime_policy_enforcement=runtime_policy_enforcement,
    )
    runtime_risk_register = build_runtime_risk_register_summary(
        runtime_config_debt=config_debt,
        runtime_shell_debt=runtime_shell_debt,
        runtime_policy_violations=runtime_policy_violations,
        runtime_policy_enforcement=runtime_policy_enforcement,
        policy_breach_summary=policy_breach_summary,
        cutover_guardrails=cutover_guardrails,
    )
    bridge_shrink_checklist = build_bridge_shrink_checklist_summary(
        projection_bridge_readiness=bridge_readiness,
        activation_gap=activation_gap,
        runtime_shell_debt=runtime_shell_debt,
        runtime_convergence=runtime_convergence,
        cutover_readiness=cutover_readiness,
    )
    cutover_blockers_breakdown = build_cutover_blockers_breakdown_summary(
        promotion_blockers=promotion_blockers,
        runtime_shell_debt=runtime_shell_debt,
        activation_gap=activation_gap,
        cutover_readiness=cutover_readiness,
    )
    runtime_governance_contract = build_runtime_governance_contract_summary(
        runtime_bridge_policy=runtime_bridge_policy,
        runtime_operating_mode=runtime_operating_mode,
        runtime_policy_enforcement=runtime_policy_enforcement,
        runtime_resolution_policy=runtime_resolution_policy,
    )
    legacy_path_allowance = build_legacy_path_allowance_summary(
        runtime_governance_contract=runtime_governance_contract,
        runtime_resolution_policy=runtime_resolution_policy,
        runtime_config_posture=runtime_config_posture,
        runtime_operating_mode=runtime_operating_mode,
        runtime_shell_debt=runtime_shell_debt,
    )
    compatibility_exit_scorecard = build_compatibility_exit_scorecard_summary(
        bridge_shrink_checklist=bridge_shrink_checklist,
        cutover_blockers_breakdown=cutover_blockers_breakdown,
        runtime_risk_register=runtime_risk_register,
        policy_breach_summary=policy_breach_summary,
        legacy_path_allowance=legacy_path_allowance,
    )
    runtime_breach_categories = build_runtime_breach_categories_summary(
        runtime_policy_violations=runtime_policy_violations,
        runtime_risk_register=runtime_risk_register,
        policy_breach_summary=policy_breach_summary,
        legacy_path_allowance=legacy_path_allowance,
        cutover_blockers_breakdown=cutover_blockers_breakdown,
    )
    legacy_path_controls = build_legacy_path_controls_summary(
        legacy_path_allowance=legacy_path_allowance,
        runtime_resolution_policy=runtime_resolution_policy,
        runtime_operating_mode=runtime_operating_mode,
        runtime_governance_contract=runtime_governance_contract,
    )
    projection_runtime_gate = build_projection_runtime_gate_summary(
        runtime_governance_contract=runtime_governance_contract,
        compatibility_exit_scorecard=compatibility_exit_scorecard,
        runtime_policy_enforcement=runtime_policy_enforcement,
        runtime_breach_categories=runtime_breach_categories,
    )
    compatibility_shrink_decision = build_compatibility_shrink_decision_summary(
        projection_runtime_gate=projection_runtime_gate,
        legacy_path_controls=legacy_path_controls,
        runtime_risk_register=runtime_risk_register,
    )
    runtime_exception_register = build_runtime_exception_register_summary(
        legacy_path_allowance=legacy_path_allowance,
        runtime_policy_violations=runtime_policy_violations,
        runtime_breach_categories=runtime_breach_categories,
        compatibility_exit_scorecard=compatibility_exit_scorecard,
    )
    compatibility_path_matrix = build_compatibility_path_matrix_summary(
        legacy_path_controls=legacy_path_controls,
        runtime_resolution_policy=runtime_resolution_policy,
        runtime_exception_register=runtime_exception_register,
    )
    next_shrink_step = build_next_shrink_step_summary(
        compatibility_shrink_decision=compatibility_shrink_decision,
        compatibility_path_matrix=compatibility_path_matrix,
        runtime_exception_register=runtime_exception_register,
    )
    shrink_sequence = build_shrink_sequence_summary(
        compatibility_path_matrix=compatibility_path_matrix,
        next_shrink_step=next_shrink_step,
    )
    return {
        "server_code": normalized_server,
        "bindings": bindings,
        "binding_count": len(bindings),
        "binding_source": str(bindings_check.get("binding_source") or ""),
        "canonical_binding_ready": bool(bindings_check.get("canonical_ready")),
        "health": dict((health_payload.get("checks") or {}).get("health") or {}),
        "projection_bridge": dict(health_payload.get("projection_bridge") or {}),
        "runtime_provenance": dict(health_payload.get("runtime_provenance") or {}),
        "runtime_alignment": dict(health_payload.get("runtime_alignment") or {}),
        "runtime_item_parity": runtime_item_parity,
        "runtime_version_parity": runtime_version_parity,
        "projection_bridge_lifecycle": projection_bridge_lifecycle,
        "projection_bridge_readiness": bridge_readiness,
        "runtime_resolution_policy": runtime_resolution_policy,
        "promotion_candidate": promotion_candidate,
        "promotion_delta": promotion_delta,
        "promotion_blockers": promotion_blockers,
        "promotion_review_signal": promotion_review_signal,
        "activation_gap": activation_gap,
        "runtime_shell_debt": runtime_shell_debt,
        "runtime_convergence": runtime_convergence,
        "cutover_readiness": cutover_readiness,
        "runtime_cutover_mode": runtime_cutover_mode,
        "runtime_bridge_policy": runtime_bridge_policy,
        "runtime_operating_mode": runtime_operating_mode,
        "runtime_policy_violations": runtime_policy_violations,
        "cutover_guardrails": cutover_guardrails,
        "runtime_policy_enforcement": runtime_policy_enforcement,
        "policy_breach_summary": policy_breach_summary,
        "runtime_risk_register": runtime_risk_register,
        "runtime_governance_contract": runtime_governance_contract,
        "legacy_path_allowance": legacy_path_allowance,
        "compatibility_exit_scorecard": compatibility_exit_scorecard,
        "runtime_breach_categories": runtime_breach_categories,
        "legacy_path_controls": legacy_path_controls,
        "projection_runtime_gate": projection_runtime_gate,
        "compatibility_shrink_decision": compatibility_shrink_decision,
        "runtime_exception_register": runtime_exception_register,
        "compatibility_path_matrix": compatibility_path_matrix,
        "next_shrink_step": next_shrink_step,
        "shrink_sequence": shrink_sequence,
        "bridge_shrink_checklist": bridge_shrink_checklist,
        "cutover_blockers_breakdown": cutover_blockers_breakdown,
        "latest_projection_run": _serialize_run(current_run),
        "fill_check": fill_summary,
        "diff": diff_summary,
    }


def build_server_effective_laws_payload(
    *,
    server_code: str,
    runtime_servers_store: RuntimeServersStore,
    projections_store: ServerEffectiveLawProjectionsStore,
    versions_store: CanonicalLawDocumentVersionsStore,
) -> dict[str, Any]:
    normalized_server = normalize_runtime_server_code(server_code)
    server = runtime_servers_store.get_server(code=normalized_server)
    if server is None:
        raise KeyError("server_not_found")
    current_run, _ = _latest_projection_runs(projections_store, server_code=normalized_server)
    items, summary = _effective_items_payload(
        projections_store=projections_store,
        versions_store=versions_store,
        run=current_run,
    )
    return {
        "server_code": normalized_server,
        "run": summary.get("run"),
        "items": items,
        "count": int(summary.get("count") or 0),
        "summary": {
            "with_content": int(summary.get("with_content") or 0),
            "missing_content": int(summary.get("missing_content") or 0),
            "error_count": int(summary.get("error_count") or 0),
            "last_updated_at": str(summary.get("last_updated_at") or ""),
        },
    }


def run_server_laws_refresh_preview_payload(
    *,
    server_code: str,
    runtime_servers_store: RuntimeServersStore,
    source_sets_store: LawSourceSetsStore,
    projections_store: ServerEffectiveLawProjectionsStore,
    versions_store: CanonicalLawDocumentVersionsStore,
    trigger_mode: str = "manual",
    safe_rerun: bool = True,
) -> dict[str, Any]:
    normalized_server = normalize_runtime_server_code(server_code)
    server = runtime_servers_store.get_server(code=normalized_server)
    if server is None:
        raise KeyError("server_not_found")
    previous_run, _ = _latest_projection_runs(projections_store, server_code=normalized_server)
    result = preview_server_effective_law_projection_payload(
        source_sets_store=source_sets_store,
        versions_store=versions_store,
        projections_store=projections_store,
        server_code=normalized_server,
        trigger_mode=trigger_mode,
        safe_rerun=safe_rerun,
    )
    current_run_id = int(((result.get("run") or {}).get("id") or 0))
    current_items = projections_store.list_items(projection_run_id=current_run_id) if current_run_id > 0 else []
    previous_items = (
        projections_store.list_items(projection_run_id=int(previous_run.id))
        if previous_run is not None and int(previous_run.id) != current_run_id
        else []
    )
    diff_summary = _diff_summary(current_items, previous_items)
    diff_summary["current_run_id"] = current_run_id or None
    diff_summary["baseline_run_id"] = int(previous_run.id) if previous_run is not None and int(previous_run.id) != current_run_id else None
    return {
        **result,
        "server_code": normalized_server,
        "diff": diff_summary,
    }


def build_server_laws_recheck_payload(
    *,
    server_code: str,
    runtime_servers_store: RuntimeServersStore,
    projections_store: ServerEffectiveLawProjectionsStore,
    versions_store: CanonicalLawDocumentVersionsStore,
) -> dict[str, Any]:
    normalized_server = normalize_runtime_server_code(server_code)
    server = runtime_servers_store.get_server(code=normalized_server)
    if server is None:
        raise KeyError("server_not_found")
    current_run, _ = _latest_projection_runs(projections_store, server_code=normalized_server)
    items, summary = _effective_items_payload(
        projections_store=projections_store,
        versions_store=versions_store,
        run=current_run,
    )
    return {
        "server_code": normalized_server,
        "run": summary.get("run"),
        "summary": {
            "count": int(summary.get("count") or 0),
            "with_content": int(summary.get("with_content") or 0),
            "missing_content": int(summary.get("missing_content") or 0),
            "error_count": int(summary.get("error_count") or 0),
            "last_updated_at": str(summary.get("last_updated_at") or ""),
        },
        "items": items,
    }


def build_server_laws_diff_payload(
    *,
    server_code: str,
    runtime_servers_store: RuntimeServersStore,
    law_sets_store: RuntimeLawSetsStore,
    source_sets_store: LawSourceSetsStore,
    projections_store: ServerEffectiveLawProjectionsStore,
) -> dict[str, Any]:
    normalized_server = normalize_runtime_server_code(server_code)
    server = runtime_servers_store.get_server(code=normalized_server)
    if server is None:
        raise KeyError("server_not_found")
    health_payload = build_runtime_server_health_payload(
        server_code=normalized_server,
        runtime_servers_store=runtime_servers_store,
        law_sets_store=law_sets_store,
        source_sets_store=source_sets_store,
        projections_store=projections_store,
    )
    bindings_check = dict(((health_payload.get("checks") or {}).get("bindings") or {}))
    canonical_bindings = list(source_sets_store.list_bindings(server_code=normalized_server))
    current_run, previous_run = _latest_projection_runs(projections_store, server_code=normalized_server)
    current_items = projections_store.list_items(projection_run_id=int(current_run.id)) if current_run is not None else []
    previous_items = projections_store.list_items(projection_run_id=int(previous_run.id)) if previous_run is not None else []
    active_law_set_id = int(((health_payload.get("runtime_alignment") or {}).get("active_law_set_id") or 0))
    active_runtime_items = _active_runtime_law_items_payload(
        law_sets_store=law_sets_store,
        active_law_set_id=active_law_set_id or None,
    )
    runtime_item_parity = _runtime_item_parity_summary(
        active_runtime_items=active_runtime_items,
        projection_items=current_items,
    )
    runtime_version_parity = _runtime_version_parity_summary(health_payload=health_payload)
    projection_bridge_lifecycle = _projection_bridge_lifecycle_summary(health_payload=health_payload)
    bridge_readiness = build_projection_bridge_readiness_summary(
        binding_count=len(canonical_bindings),
        projection_bridge_lifecycle=projection_bridge_lifecycle,
        runtime_version_parity=runtime_version_parity,
        fill_summary={},
        latest_projection_run=_serialize_run(current_run) or {},
    )
    diff_summary = _diff_summary(current_items, previous_items)
    diff_summary["current_run_id"] = int(current_run.id) if current_run is not None else None
    diff_summary["baseline_run_id"] = int(previous_run.id) if previous_run is not None else None
    promotion_candidate = build_promotion_candidate_summary(
        diff_summary=diff_summary,
        fill_summary={},
        projection_bridge_readiness=bridge_readiness,
        runtime_version_parity=runtime_version_parity,
        latest_projection_run=_serialize_run(current_run) or {},
    )
    promotion_delta = build_promotion_delta_summary(
        diff_summary=diff_summary,
        fill_summary={},
        latest_projection_run=_serialize_run(current_run) or {},
        projection_bridge_readiness=bridge_readiness,
    )
    promotion_blockers = build_promotion_blockers_summary(
        projection_bridge_readiness=bridge_readiness,
        promotion_candidate=promotion_candidate,
        promotion_delta=promotion_delta,
        runtime_item_parity=runtime_item_parity,
        runtime_version_parity=runtime_version_parity,
        projection_bridge_lifecycle=projection_bridge_lifecycle,
    )
    promotion_review_signal = build_promotion_review_signal_summary(
        promotion_candidate=promotion_candidate,
        promotion_delta=promotion_delta,
        promotion_blockers=promotion_blockers,
    )
    activation_gap = build_activation_gap_summary(
        projection_bridge_readiness=bridge_readiness,
        runtime_version_parity=runtime_version_parity,
        projection_bridge_lifecycle=projection_bridge_lifecycle,
        promotion_blockers=promotion_blockers,
    )
    runtime_shell_debt = build_runtime_shell_debt_summary(
        runtime_provenance=dict(health_payload.get("runtime_provenance") or {}),
        runtime_version_parity=runtime_version_parity,
        projection_bridge_lifecycle=projection_bridge_lifecycle,
        onboarding=dict(health_payload.get("onboarding") or {}),
    )
    runtime_convergence = build_runtime_convergence_summary(
        promotion_blockers=promotion_blockers,
        activation_gap=activation_gap,
        runtime_shell_debt=runtime_shell_debt,
    )
    cutover_readiness = build_cutover_readiness_summary(
        projection_bridge_readiness=bridge_readiness,
        runtime_convergence=runtime_convergence,
        runtime_shell_debt=runtime_shell_debt,
        activation_gap=activation_gap,
    )
    config_debt = dict((health_payload.get("runtime_config_debt") or {}))
    if not config_debt:
        config_debt = build_runtime_config_debt_summary(health_payload=health_payload)
    runtime_config_posture = dict((health_payload.get("runtime_config_posture") or {}))
    if not runtime_config_posture:
        runtime_config_posture = build_runtime_config_posture_summary(health_payload=health_payload)
    runtime_resolution_policy = dict((health_payload.get("runtime_resolution_policy") or {}))
    if not runtime_resolution_policy:
        runtime_resolution_policy = build_runtime_resolution_policy_summary(health_payload=health_payload)
    runtime_cutover_mode = build_runtime_cutover_mode_summary(
        cutover_readiness=cutover_readiness,
        runtime_convergence=runtime_convergence,
        runtime_shell_debt=runtime_shell_debt,
        runtime_config_debt=config_debt,
    )
    runtime_bridge_policy = build_runtime_bridge_policy_summary(
        runtime_resolution_policy=runtime_resolution_policy,
        runtime_cutover_mode=runtime_cutover_mode,
        cutover_readiness=cutover_readiness,
    )
    runtime_operating_mode = build_runtime_operating_mode_summary(
        runtime_bridge_policy=runtime_bridge_policy,
        runtime_config_posture=runtime_config_posture,
        runtime_provenance=dict(health_payload.get("runtime_provenance") or {}),
        runtime_cutover_mode=runtime_cutover_mode,
    )
    runtime_policy_violations = build_runtime_policy_violations_summary(
        runtime_bridge_policy=runtime_bridge_policy,
        runtime_operating_mode=runtime_operating_mode,
        runtime_config_posture=runtime_config_posture,
        runtime_provenance=dict(health_payload.get("runtime_provenance") or {}),
        runtime_shell_debt=runtime_shell_debt,
        cutover_readiness=cutover_readiness,
    )
    cutover_guardrails = build_cutover_guardrails_summary(
        runtime_bridge_policy=runtime_bridge_policy,
        runtime_operating_mode=runtime_operating_mode,
        runtime_policy_violations=runtime_policy_violations,
        cutover_readiness=cutover_readiness,
    )
    runtime_policy_enforcement = build_runtime_policy_enforcement_summary(
        runtime_bridge_policy=runtime_bridge_policy,
        runtime_operating_mode=runtime_operating_mode,
        runtime_policy_violations=runtime_policy_violations,
        cutover_guardrails=cutover_guardrails,
    )
    policy_breach_summary = build_policy_breach_summary(
        runtime_bridge_policy=runtime_bridge_policy,
        runtime_operating_mode=runtime_operating_mode,
        runtime_policy_violations=runtime_policy_violations,
        runtime_policy_enforcement=runtime_policy_enforcement,
    )
    runtime_risk_register = build_runtime_risk_register_summary(
        runtime_config_debt=config_debt,
        runtime_shell_debt=runtime_shell_debt,
        runtime_policy_violations=runtime_policy_violations,
        runtime_policy_enforcement=runtime_policy_enforcement,
        policy_breach_summary=policy_breach_summary,
        cutover_guardrails=cutover_guardrails,
    )
    bridge_shrink_checklist = build_bridge_shrink_checklist_summary(
        projection_bridge_readiness=bridge_readiness,
        activation_gap=activation_gap,
        runtime_shell_debt=runtime_shell_debt,
        runtime_convergence=runtime_convergence,
        cutover_readiness=cutover_readiness,
    )
    cutover_blockers_breakdown = build_cutover_blockers_breakdown_summary(
        promotion_blockers=promotion_blockers,
        runtime_shell_debt=runtime_shell_debt,
        activation_gap=activation_gap,
        cutover_readiness=cutover_readiness,
    )
    runtime_governance_contract = build_runtime_governance_contract_summary(
        runtime_bridge_policy=runtime_bridge_policy,
        runtime_operating_mode=runtime_operating_mode,
        runtime_policy_enforcement=runtime_policy_enforcement,
        runtime_resolution_policy=runtime_resolution_policy,
    )
    legacy_path_allowance = build_legacy_path_allowance_summary(
        runtime_governance_contract=runtime_governance_contract,
        runtime_resolution_policy=runtime_resolution_policy,
        runtime_config_posture=runtime_config_posture,
        runtime_operating_mode=runtime_operating_mode,
        runtime_shell_debt=runtime_shell_debt,
    )
    compatibility_exit_scorecard = build_compatibility_exit_scorecard_summary(
        bridge_shrink_checklist=bridge_shrink_checklist,
        cutover_blockers_breakdown=cutover_blockers_breakdown,
        runtime_risk_register=runtime_risk_register,
        policy_breach_summary=policy_breach_summary,
        legacy_path_allowance=legacy_path_allowance,
    )
    runtime_breach_categories = build_runtime_breach_categories_summary(
        runtime_policy_violations=runtime_policy_violations,
        runtime_risk_register=runtime_risk_register,
        policy_breach_summary=policy_breach_summary,
        legacy_path_allowance=legacy_path_allowance,
        cutover_blockers_breakdown=cutover_blockers_breakdown,
    )
    legacy_path_controls = build_legacy_path_controls_summary(
        legacy_path_allowance=legacy_path_allowance,
        runtime_resolution_policy=runtime_resolution_policy,
        runtime_operating_mode=runtime_operating_mode,
        runtime_governance_contract=runtime_governance_contract,
    )
    projection_runtime_gate = build_projection_runtime_gate_summary(
        runtime_governance_contract=runtime_governance_contract,
        compatibility_exit_scorecard=compatibility_exit_scorecard,
        runtime_policy_enforcement=runtime_policy_enforcement,
        runtime_breach_categories=runtime_breach_categories,
    )
    compatibility_shrink_decision = build_compatibility_shrink_decision_summary(
        projection_runtime_gate=projection_runtime_gate,
        legacy_path_controls=legacy_path_controls,
        runtime_risk_register=runtime_risk_register,
    )
    runtime_exception_register = build_runtime_exception_register_summary(
        legacy_path_allowance=legacy_path_allowance,
        runtime_policy_violations=runtime_policy_violations,
        runtime_breach_categories=runtime_breach_categories,
        compatibility_exit_scorecard=compatibility_exit_scorecard,
    )
    compatibility_path_matrix = build_compatibility_path_matrix_summary(
        legacy_path_controls=legacy_path_controls,
        runtime_resolution_policy=runtime_resolution_policy,
        runtime_exception_register=runtime_exception_register,
    )
    next_shrink_step = build_next_shrink_step_summary(
        compatibility_shrink_decision=compatibility_shrink_decision,
        compatibility_path_matrix=compatibility_path_matrix,
        runtime_exception_register=runtime_exception_register,
    )
    shrink_sequence = build_shrink_sequence_summary(
        compatibility_path_matrix=compatibility_path_matrix,
        next_shrink_step=next_shrink_step,
    )
    return {
        "server_code": normalized_server,
        "binding_count": len(canonical_bindings),
        "binding_source": str(bindings_check.get("binding_source") or ""),
        "canonical_binding_ready": bool(bindings_check.get("canonical_ready")),
        "current_run": _serialize_run(current_run),
        "baseline_run": _serialize_run(previous_run),
        "runtime_alignment": dict(health_payload.get("runtime_alignment") or {}),
        "runtime_item_parity": runtime_item_parity,
        "runtime_version_parity": runtime_version_parity,
        "projection_bridge_lifecycle": projection_bridge_lifecycle,
        "projection_bridge_readiness": bridge_readiness,
        "runtime_resolution_policy": runtime_resolution_policy,
        "promotion_candidate": promotion_candidate,
        "promotion_delta": promotion_delta,
        "promotion_blockers": promotion_blockers,
        "promotion_review_signal": promotion_review_signal,
        "activation_gap": activation_gap,
        "runtime_shell_debt": runtime_shell_debt,
        "runtime_convergence": runtime_convergence,
        "cutover_readiness": cutover_readiness,
        "runtime_cutover_mode": runtime_cutover_mode,
        "runtime_bridge_policy": runtime_bridge_policy,
        "runtime_operating_mode": runtime_operating_mode,
        "runtime_policy_violations": runtime_policy_violations,
        "cutover_guardrails": cutover_guardrails,
        "runtime_policy_enforcement": runtime_policy_enforcement,
        "policy_breach_summary": policy_breach_summary,
        "runtime_risk_register": runtime_risk_register,
        "runtime_governance_contract": runtime_governance_contract,
        "legacy_path_allowance": legacy_path_allowance,
        "compatibility_exit_scorecard": compatibility_exit_scorecard,
        "runtime_breach_categories": runtime_breach_categories,
        "legacy_path_controls": legacy_path_controls,
        "projection_runtime_gate": projection_runtime_gate,
        "compatibility_shrink_decision": compatibility_shrink_decision,
        "runtime_exception_register": runtime_exception_register,
        "compatibility_path_matrix": compatibility_path_matrix,
        "next_shrink_step": next_shrink_step,
        "shrink_sequence": shrink_sequence,
        "bridge_shrink_checklist": bridge_shrink_checklist,
        "cutover_blockers_breakdown": cutover_blockers_breakdown,
        "summary": diff_summary,
    }

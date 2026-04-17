from __future__ import annotations

from typing import Any

from ogp_web.services.admin_law_projection_service import (
    preview_server_effective_law_projection_payload,
)
from ogp_web.services.admin_runtime_servers_service import (
    build_runtime_config_debt_summary,
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
    if status in {"drift", "legacy_only", "pending_activation"}:
        drift_parts: list[str] = []
        if active_law_version_id > 0:
            drift_parts.append(f"active_version={active_law_version_id}")
        if projected_law_version_id > 0:
            drift_parts.append(f"projected_version={projected_law_version_id}")
        if active_law_set_id > 0:
            drift_parts.append(f"active_law_set={active_law_set_id}")
        if projected_law_set_id > 0:
            drift_parts.append(f"projected_law_set={projected_law_set_id}")
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
        "matches_active_law_set": (
            projected_law_set_id > 0 and active_law_set_id > 0 and projected_law_set_id == active_law_set_id
        ),
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
        detail = "Projection bridge materialized a runtime law_set shell, but no active runtime law_version is aligned yet."
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
        next_step = "Legacy runtime shell dependence is not currently a visible blocker."
    elif provenance_mode == "legacy_runtime_shell" or version_status == "legacy_only":
        status = "high"
        detail = "Runtime still depends heavily on the legacy shell path."
        next_step = "Сведите зависимость к projection-backed runtime shell и controlled activation path."
    else:
        status = "medium"
        detail = "Runtime still carries compatibility shell debt that deserves follow-up."
        next_step = "Сведите activation/provenance drift и проверьте shell dependence через безопасный recheck."

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "reason_count": len(deduped_reasons),
        "reasons": deduped_reasons[:8],
        "provenance_mode": provenance_mode,
        "version_status": version_status,
        "lifecycle_status": lifecycle_status,
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

    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "count": len(deduped),
        "category_counts": category_counts,
        "items": deduped[:10],
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
        projections_store=projections_store,
    )
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
    runtime_cutover_mode = build_runtime_cutover_mode_summary(
        cutover_readiness=cutover_readiness,
        runtime_convergence=runtime_convergence,
        runtime_shell_debt=runtime_shell_debt,
        runtime_config_debt=config_debt,
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
    return {
        "server_code": normalized_server,
        "bindings": bindings,
        "binding_count": len(bindings),
        "health": dict((health_payload.get("checks") or {}).get("health") or {}),
        "projection_bridge": dict(health_payload.get("projection_bridge") or {}),
        "runtime_provenance": dict(health_payload.get("runtime_provenance") or {}),
        "runtime_alignment": dict(health_payload.get("runtime_alignment") or {}),
        "runtime_item_parity": runtime_item_parity,
        "runtime_version_parity": runtime_version_parity,
        "projection_bridge_lifecycle": projection_bridge_lifecycle,
        "projection_bridge_readiness": bridge_readiness,
        "promotion_candidate": promotion_candidate,
        "promotion_delta": promotion_delta,
        "promotion_blockers": promotion_blockers,
        "promotion_review_signal": promotion_review_signal,
        "activation_gap": activation_gap,
        "runtime_shell_debt": runtime_shell_debt,
        "runtime_convergence": runtime_convergence,
        "cutover_readiness": cutover_readiness,
        "runtime_cutover_mode": runtime_cutover_mode,
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
        projections_store=projections_store,
    )
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
        binding_count=int(((health_payload.get("checks") or {}).get("bindings") or {}).get("count") or 0),
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
    runtime_cutover_mode = build_runtime_cutover_mode_summary(
        cutover_readiness=cutover_readiness,
        runtime_convergence=runtime_convergence,
        runtime_shell_debt=runtime_shell_debt,
        runtime_config_debt=config_debt,
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
    return {
        "server_code": normalized_server,
        "current_run": _serialize_run(current_run),
        "baseline_run": _serialize_run(previous_run),
        "runtime_alignment": dict(health_payload.get("runtime_alignment") or {}),
        "runtime_item_parity": runtime_item_parity,
        "runtime_version_parity": runtime_version_parity,
        "projection_bridge_lifecycle": projection_bridge_lifecycle,
        "projection_bridge_readiness": bridge_readiness,
        "promotion_candidate": promotion_candidate,
        "promotion_delta": promotion_delta,
        "promotion_blockers": promotion_blockers,
        "promotion_review_signal": promotion_review_signal,
        "activation_gap": activation_gap,
        "runtime_shell_debt": runtime_shell_debt,
        "runtime_convergence": runtime_convergence,
        "cutover_readiness": cutover_readiness,
        "runtime_cutover_mode": runtime_cutover_mode,
        "bridge_shrink_checklist": bridge_shrink_checklist,
        "cutover_blockers_breakdown": cutover_blockers_breakdown,
        "summary": diff_summary,
    }

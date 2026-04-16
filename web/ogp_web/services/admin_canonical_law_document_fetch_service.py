from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Callable

import httpx

from ogp_web.storage.canonical_law_document_versions_store import (
    CanonicalLawDocumentVersionRecord,
    CanonicalLawDocumentVersionsStore,
)
from ogp_web.storage.law_source_discovery_store import LawSourceDiscoveryStore

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _checksum(text: str) -> str:
    payload = str(text or "").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:24]


def _extract_title(*, html_text: str, fallback: str) -> str:
    match = _TITLE_RE.search(str(html_text or ""))
    if match:
        title = re.sub(r"\s+", " ", str(match.group(1) or "")).strip()
        if title:
            return title
    return str(fallback or "").strip()


def _default_fetcher(normalized_url: str, timeout_sec: int) -> dict[str, Any]:
    with httpx.Client(timeout=float(timeout_sec), follow_redirects=True) as client:
        response = client.get(str(normalized_url or "").strip())
        response.raise_for_status()
        return {
            "status_code": int(response.status_code),
            "url": str(response.url),
            "text": str(response.text or ""),
            "headers": dict(response.headers),
        }


def _build_success_metadata(
    *,
    record: CanonicalLawDocumentVersionRecord,
    existing_metadata: dict[str, Any],
    fetched_payload: dict[str, Any],
    timeout_sec: int,
) -> dict[str, Any]:
    metadata = dict(existing_metadata or {})
    headers = dict(fetched_payload.get("headers") or {})
    metadata.update(
        {
            "fetch_mode": "manual_admin_fetch",
            "fetch_requested_at": _utc_now(),
            "fetch_timeout_sec": int(timeout_sec),
            "fetch_source_url": str(record.normalized_url or ""),
            "fetch_final_url": str(fetched_payload.get("url") or record.normalized_url or ""),
            "fetch_status_code": int(fetched_payload.get("status_code") or 200),
            "fetch_content_type": str(headers.get("content-type") or ""),
            "fetch_bytes": len(str(fetched_payload.get("text") or "").encode("utf-8")),
            "fetch_error": "",
        }
    )
    return metadata


def _build_failure_metadata(
    *,
    record: CanonicalLawDocumentVersionRecord,
    existing_metadata: dict[str, Any],
    error: Exception,
    timeout_sec: int,
) -> dict[str, Any]:
    metadata = dict(existing_metadata or {})
    metadata.update(
        {
            "fetch_mode": "manual_admin_fetch",
            "fetch_requested_at": _utc_now(),
            "fetch_timeout_sec": int(timeout_sec),
            "fetch_source_url": str(record.normalized_url or ""),
            "fetch_final_url": "",
            "fetch_status_code": 0,
            "fetch_content_type": "",
            "fetch_bytes": 0,
            "fetch_error": str(error or "").strip() or "fetch_failed",
        }
    )
    return metadata


def fetch_discovery_run_document_versions_payload(
    *,
    discovery_store: LawSourceDiscoveryStore,
    versions_store: CanonicalLawDocumentVersionsStore,
    run_id: int,
    safe_rerun: bool = True,
    timeout_sec: int = 15,
    fetcher: Callable[[str, int], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if int(run_id) <= 0:
        raise ValueError("source_discovery_run_id_required")
    normalized_timeout = int(timeout_sec or 0)
    if normalized_timeout < 1:
        raise ValueError("canonical_law_document_fetch_timeout_invalid")
    run = discovery_store.get_run(run_id=int(run_id))
    if run is None:
        raise KeyError("source_discovery_run_not_found")
    versions = versions_store.list_versions_for_run(source_discovery_run_id=int(run_id))
    if not versions:
        raise ValueError("source_discovery_run_has_no_document_versions")

    fetch_impl = fetcher or _default_fetcher
    fetched_versions = 0
    failed_versions = 0
    reused_versions = 0
    items: list[dict[str, Any]] = []

    for version in versions:
        if safe_rerun and str(version.fetch_status or "").strip().lower() == "fetched" and str(version.body_text or "").strip():
            reused_versions += 1
            current = versions_store.get_version(version_id=int(version.id)) or version
            items.append(
                {
                    "id": current.id,
                    "canonical_law_document_id": current.canonical_law_document_id,
                    "canonical_identity_key": current.canonical_identity_key,
                    "normalized_url": current.normalized_url,
                    "fetch_status": current.fetch_status,
                    "parse_status": current.parse_status,
                    "content_checksum": current.content_checksum,
                    "raw_title": current.raw_title,
                }
            )
            continue
        try:
            fetched_payload = dict(fetch_impl(version.normalized_url, normalized_timeout) or {})
            body_text = str(fetched_payload.get("text") or "").strip()
            raw_title = _extract_title(html_text=body_text, fallback=version.raw_title or version.display_title)
            updated = versions_store.update_fetch_result(
                version_id=int(version.id),
                fetch_status="fetched",
                content_checksum=_checksum(body_text),
                raw_title=raw_title,
                body_text=body_text,
                metadata_json=_build_success_metadata(
                    record=version,
                    existing_metadata=version.metadata_json,
                    fetched_payload=fetched_payload,
                    timeout_sec=normalized_timeout,
                ),
            )
            fetched_versions += 1
        except Exception as exc:
            updated = versions_store.update_fetch_result(
                version_id=int(version.id),
                fetch_status="failed",
                content_checksum=version.content_checksum,
                raw_title=version.raw_title or version.display_title,
                body_text=version.body_text,
                metadata_json=_build_failure_metadata(
                    record=version,
                    existing_metadata=version.metadata_json,
                    error=exc,
                    timeout_sec=normalized_timeout,
                ),
            )
            failed_versions += 1
        items.append(
            {
                "id": updated.id,
                "canonical_law_document_id": updated.canonical_law_document_id,
                "canonical_identity_key": updated.canonical_identity_key,
                "normalized_url": updated.normalized_url,
                "fetch_status": updated.fetch_status,
                "parse_status": updated.parse_status,
                "content_checksum": updated.content_checksum,
                "raw_title": updated.raw_title,
            }
        )

    return {
        "ok": True,
        "changed": bool(fetched_versions or failed_versions),
        "run": {
            "id": run.id,
            "source_set_revision_id": run.source_set_revision_id,
            "source_set_key": run.source_set_key,
            "revision": run.revision,
            "trigger_mode": run.trigger_mode,
            "status": run.status,
            "summary_json": dict(run.summary_json),
            "error_summary": run.error_summary,
        },
        "items": items,
        "count": len(items),
        "fetched_versions": fetched_versions,
        "failed_versions": failed_versions,
        "reused_versions": reused_versions,
    }

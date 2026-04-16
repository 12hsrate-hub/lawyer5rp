from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any

from ogp_web.storage.canonical_law_document_versions_store import CanonicalLawDocumentVersionsStore
from ogp_web.storage.law_source_discovery_store import LawSourceDiscoveryStore

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = str(data or "")
        if text.strip():
            self.parts.append(text)


def _extract_title(*, raw_html: str, fallback: str) -> str:
    match = _TITLE_RE.search(str(raw_html or ""))
    if match:
        title = re.sub(r"\s+", " ", html.unescape(str(match.group(1) or ""))).strip()
        if title:
            return title
    return str(fallback or "").strip()


def _extract_body_text(*, raw_html: str) -> str:
    parser = _TextExtractor()
    parser.feed(str(raw_html or ""))
    parser.close()
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


def _build_success_metadata(*, existing_metadata: dict[str, Any], parsed_title: str, parsed_body: str) -> dict[str, Any]:
    metadata = dict(existing_metadata or {})
    metadata.update(
        {
            "parse_mode": "manual_admin_parse",
            "parse_requested_at": _utc_now(),
            "parse_title_source": "html_title_or_fallback",
            "parse_body_chars": len(str(parsed_body or "")),
            "parse_error": "",
            "parse_title_preview": str(parsed_title or "")[:200],
        }
    )
    return metadata


def _build_failure_metadata(*, existing_metadata: dict[str, Any], error: Exception) -> dict[str, Any]:
    metadata = dict(existing_metadata or {})
    metadata.update(
        {
            "parse_mode": "manual_admin_parse",
            "parse_requested_at": _utc_now(),
            "parse_body_chars": 0,
            "parse_error": str(error or "").strip() or "parse_failed",
        }
    )
    return metadata


def parse_discovery_run_document_versions_payload(
    *,
    discovery_store: LawSourceDiscoveryStore,
    versions_store: CanonicalLawDocumentVersionsStore,
    run_id: int,
    safe_rerun: bool = True,
) -> dict[str, Any]:
    if int(run_id) <= 0:
        raise ValueError("source_discovery_run_id_required")
    run = discovery_store.get_run(run_id=int(run_id))
    if run is None:
        raise KeyError("source_discovery_run_not_found")
    versions = versions_store.list_versions_for_run(source_discovery_run_id=int(run_id))
    if not versions:
        raise ValueError("source_discovery_run_has_no_document_versions")

    parsed_versions = 0
    failed_versions = 0
    reused_versions = 0
    items: list[dict[str, Any]] = []

    for version in versions:
        if safe_rerun and str(version.parse_status or "").strip().lower() == "parsed" and str(version.parsed_title or "").strip():
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
                    "parsed_title": current.parsed_title,
                }
            )
            continue
        try:
            if str(version.fetch_status or "").strip().lower() != "fetched":
                raise ValueError("canonical_law_document_version_not_fetched")
            raw_html = str(version.body_text or "").strip()
            if not raw_html:
                raise ValueError("canonical_law_document_version_body_missing")
            parsed_title = _extract_title(raw_html=raw_html, fallback=version.raw_title or version.display_title)
            parsed_body = _extract_body_text(raw_html=raw_html)
            if not parsed_body:
                raise ValueError("canonical_law_document_version_parse_empty")
            updated = versions_store.update_parse_result(
                version_id=int(version.id),
                parse_status="parsed",
                parsed_title=parsed_title,
                body_text=parsed_body,
                metadata_json=_build_success_metadata(
                    existing_metadata=version.metadata_json,
                    parsed_title=parsed_title,
                    parsed_body=parsed_body,
                ),
            )
            parsed_versions += 1
        except Exception as exc:
            updated = versions_store.update_parse_result(
                version_id=int(version.id),
                parse_status="failed",
                parsed_title=version.parsed_title,
                body_text=version.body_text,
                metadata_json=_build_failure_metadata(existing_metadata=version.metadata_json, error=exc),
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
                "parsed_title": updated.parsed_title,
            }
        )

    return {
        "ok": True,
        "changed": bool(parsed_versions or failed_versions),
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
        "parsed_versions": parsed_versions,
        "failed_versions": failed_versions,
        "reused_versions": reused_versions,
    }

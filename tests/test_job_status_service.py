from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.job_status_service import enrich_job_status, normalize_job_status


def test_normalize_job_status_maps_known_async_variants():
    assert normalize_job_status("pending", subsystem="async_job") == "queued"
    assert normalize_job_status("processing", subsystem="async_job") == "running"
    assert normalize_job_status("dead_lettered", subsystem="async_job") == "failed"
    assert normalize_job_status("completed", subsystem="exam_import") == "succeeded"
    assert normalize_job_status("finished", subsystem="admin_task") == "succeeded"


def test_enrich_job_status_adds_raw_and_canonical_fields():
    payload = enrich_job_status({"status": "processing", "job_type": "document_export"}, subsystem="async_job")

    assert payload["status"] == "processing"
    assert payload["raw_status"] == "processing"
    assert payload["canonical_status"] == "running"

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.generation_snapshot_schema_service import (
    build_snapshot_summary,
    build_workflow_linkage,
    extract_provenance_ai,
    extract_provenance_config,
)


def test_generation_snapshot_schema_helper_builds_shared_views():
    snapshot_payload = {
        "context_snapshot": {
            "template_version": {"id": "complaint_template_v1", "hash": "abc"},
            "law_version_set": {"hash": "laws@35"},
            "validation_rules_version": {"rule_set_key": "publication_workflow_v1"},
            "content_workflow": {"procedure": "complaint_law_index", "prompt_version": "prompt_ctx_v1"},
            "effective_versions": {"law_version_id": 35},
            "ai": {"provider": "openai", "model": "gpt-5.4"},
        },
        "effective_config_snapshot": {
            "server_config_version": "blackberry@2026-04-15",
            "law_set_version": {"law_set_key": "laws@35"},
        },
        "content_workflow_ref": {
            "procedure": {"procedure_code": "complaint_law_index"},
            "template": {"template_code": "complaint_template_v1"},
            "prompt_version": "complaint_prompt_v4",
        },
    }

    summary = build_snapshot_summary(snapshot_payload)
    linkage = build_workflow_linkage(
        snapshot_payload,
        document_version_id=77,
        generation_snapshot_id=501,
        latest_validation_run_id=3001,
    )
    config = extract_provenance_config(snapshot_payload)
    ai = extract_provenance_ai(snapshot_payload)

    assert summary["template_version"] == "complaint_template_v1"
    assert summary["law_version_set"] == "laws@35"
    assert summary["validation_rules_version"] == "publication_workflow_v1"
    assert linkage["procedure_ref"] == "complaint_law_index"
    assert linkage["template_ref"] == "complaint_template_v1"
    assert linkage["document_version_id"] == 77
    assert config["server_config_version"] == "blackberry@2026-04-15"
    assert config["law_version_id"] == 35
    assert ai["provider"] == "openai"
    assert ai["prompt_version"] == "complaint_prompt_v4"

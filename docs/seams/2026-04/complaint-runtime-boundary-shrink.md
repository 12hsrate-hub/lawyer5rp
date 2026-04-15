# Compatibility Seam Note

- Seam ID: `seam-2026-04-complaint-runtime-boundary`
- Area: `web/ogp_web/routes/complaint.py` <-> `web/ogp_web/services/complaint_runtime_service.py`
- Reason this seam exists: complaint runtime still preserves route-level compatibility aliases and monkeypatch targets while legacy route orchestration is being extracted into a dedicated service without breaking request/response contracts or existing regression tests.
- Current source of truth: `web/ogp_web/services/complaint_runtime_service.py` for complaint runtime execution, generation-boundary persistence, and law-QA persistence/validation glue; `web/ogp_web/routes/complaint.py` remains a transport-first adapter with compatibility aliases.
- Target source of truth: complaint runtime orchestration should live entirely in dedicated complaint runtime services, with the route reduced to transport/auth/serialization only.
- What changed in this task: `shrink`
- Why this was necessary: `K.1a` through `K.1c` removed real route-local orchestration for suggest concurrency/threadpool flow, complaint+rehab generation bridge/validation, and law-QA citation/retrieval/run persistence while preserving API and test compatibility.
- Rollback path: revert PRs `#294`, `#295`, and `#297` or temporarily route back through the old inline `routes/complaint.py` helpers if a production regression appears before the seam is fully removed.
- Removal gate: remove the route-level compatibility aliases once complaint route tests no longer need to monkeypatch route module symbols and no remaining complaint endpoints keep business orchestration in `routes/complaint.py`.
- Tests covering this seam:
  - `python -m pytest tests/test_web_api.py -q -k "(suggest_endpoint or law_qa_test_endpoint or generate_uses_adapter_snapshot_without_legacy_context_build_when_adapter_active or document_version_provenance_endpoint_returns_trace or generate_rehab or generate_)"`
- Remaining risks:
  - some compatibility imports still stay on the route module because existing tests patch route-level symbols directly
  - `law_qa_test` still keeps response shaping and metrics logging in the route, so the seam is reduced but not fully removed

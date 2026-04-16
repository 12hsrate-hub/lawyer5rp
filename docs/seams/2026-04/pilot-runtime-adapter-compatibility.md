# Compatibility Seam Note

- Seam ID: `seam-2026-04-pilot-runtime-adapter`
- Area: `web/ogp_web/services/pilot_runtime_adapter.py`
- Reason this seam exists: the pilot runtime adapter still preserves a blackberry-only complaint bridge while published workflow-backed runtime context replaces the older complaint runtime path incrementally instead of in one cutover.
- Current source of truth: `web/ogp_web/services/pilot_runtime_adapter.py` resolves the pilot complaint runtime context for `blackberry + complaint`, using published workflow versions when available and `effective_server_pack(...)` plus law bundle metadata as transitional support inputs.
- Target source of truth: complaint runtime resolution should become workflow/config-driven without a pilot-specific adapter module or a hard-coded `blackberry` pilot gate.
- What changed in this task: `unchanged`
- Why this was necessary: the seam is active and review-relevant today, but it was not documented in `docs/seams/2026-04/` even though the governance audit identified it as a live transitional bridge.
- Rollback path: if the adapter path regresses before removal, keep routing `blackberry` complaint generation through `supports_pilot_runtime_adapter(...)` and `resolve_pilot_complaint_runtime_context(...)` until the workflow-backed replacement path is stable again.
- Removal gate: remove the module once complaint runtime generation no longer requires a pilot-only `blackberry` gate, the published workflow path is the only active path for that document kind, and route/service tests no longer rely on adapter-specific compatibility behavior.
- Tests covering this seam:
  - `python -m pytest tests/test_pilot_runtime_adapter.py -q`
  - `python -m pytest tests/test_web_api.py -q -k "generate_uses_adapter_snapshot_without_legacy_context_build_when_adapter_active"`
- Remaining risks:
  - `PILOT_SERVER_CODE = "blackberry"` is still a hard compatibility boundary inside the service
  - the seam still depends on `effective_server_pack(...)` and law-bundle fallback metadata while the workflow-backed complaint runtime is not yet the sole runtime source

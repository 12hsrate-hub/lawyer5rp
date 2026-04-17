# Compatibility Seam Note

- Seam ID: `seam-2026-04-pilot-runtime-adapter`
- Area: `web/ogp_web/services/pilot_runtime_adapter.py`
- Reason this seam exists: the pilot runtime adapter still preserves a complaint-only compatibility bridge while published workflow-backed runtime context replaces the older complaint runtime path incrementally instead of in one cutover.
- Current source of truth: `web/ogp_web/services/pilot_runtime_adapter.py` resolves the complaint runtime context only for servers that expose an explicit complaint template binding in the effective server pack, using published workflow versions when available and `effective_server_pack(...)` plus law bundle metadata as transitional support inputs.
- Target source of truth: complaint runtime resolution should become workflow/config-driven without a pilot-specific adapter module or a hard-coded `blackberry` pilot gate.
- What changed in this task: `shrunk`
- Why this was necessary: adapter support had already been widened beyond the old `blackberry` hard gate, but it still treated any explicit complaint server as adapter-eligible even when the server pack had no complaint template binding. The seam now stays bounded to servers with an explicit complaint template binding instead of creating a false compatibility path for arbitrary servers.
- Rollback path: if the adapter path regresses before removal, keep routing complaint generation only through flagged servers that still require `supports_pilot_runtime_adapter(...)` and `resolve_pilot_complaint_runtime_context(...)` until the workflow-backed replacement path is stable again.
- Removal gate: remove the module once complaint runtime generation no longer requires a complaint-only adapter gate, the published workflow path is the only active path for that document kind, and route/service tests no longer rely on adapter-specific compatibility behavior.
- Tests covering this seam:
  - `python -m pytest tests/test_pilot_runtime_adapter.py -q`
  - `python -m pytest tests/test_web_api.py -q -k "generate_uses_adapter_snapshot_without_legacy_context_build_when_adapter_active"`
- Remaining risks:
  - complaint runtime still depends on an adapter-specific gate before the workflow-backed path becomes the only active path
  - rollout safety still depends on feature-flag scoping plus server-pack complaint template binding rather than the workflow-backed path being the only path
  - the seam still depends on `effective_server_pack(...)` and law-bundle fallback metadata while the workflow-backed complaint runtime is not yet the sole runtime source

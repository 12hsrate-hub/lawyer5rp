# Compatibility Seam Note

- Seam ID: `seam-2026-04-ai-service-server-config-wrapper`
- Area: `web/ogp_web/services/ai_service.py` (`get_server_config` compatibility wrapper)
- Reason this seam exists: `ai_service.py` still exposes a local `get_server_config(...)` wrapper so older retrieval/test seams and direct service callers can keep patching the historical symbol while runtime resolution has already moved to the shared server-context layer.
- Current source of truth: `web/ogp_web/services/server_context_service.py::resolve_server_config(...)` owns effective server-config resolution; `web/ogp_web/services/ai_service.py::get_server_config(...)` is a compatibility shim that forwards to it.
- Target source of truth: AI flows should call shared server-context helpers directly, with no local `ai_service.py` wrapper kept only for patching or backward-compatible import paths.
- What changed in this task: `unchanged`
- Why this was necessary: the wrapper is intentionally small and compatibility-only, but it remained undocumented even though the service code explicitly marks it as a local compatibility wrapper.
- Rollback path: if direct server-context resolution causes regressions in retrieval/test seams, keep callers pointed at `ai_service.get_server_config(...)` until those call sites and tests are updated to patch/use shared server-context helpers directly.
- Removal gate: remove the wrapper once suggest/law-QA/principal-scan callers and tests no longer import or monkeypatch `ai_service.get_server_config(...)` and all server-config access in AI flows is routed through shared server-context helpers.
- Tests covering this seam:
  - `python -m pytest tests/test_ai_pipeline_refactoring_contracts.py -q`
  - `python -m pytest tests/test_web_services.py -q -k "suggest_text or law_qa"`
- Remaining risks:
  - test and caller expectations may still patch the historical `ai_service.get_server_config(...)` symbol rather than shared server-context helpers
  - the wrapper is harmless at runtime, but it can hide whether AI call sites are fully converged on the shared server-context layer

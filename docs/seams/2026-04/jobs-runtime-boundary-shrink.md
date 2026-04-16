# Compatibility Seam Note

- Seam ID: `seam-2026-04-jobs-runtime-boundary`
- Area: `web/ogp_web/routes/jobs.py` <-> `web/ogp_web/services/jobs_runtime_service.py`
- Reason this seam exists: jobs routes still need to preserve the existing request/response contract while route-local service construction, actor resolution, service-error translation, and async-job payload assembly move into a dedicated runtime service.
- Current source of truth: `web/ogp_web/services/jobs_runtime_service.py` for async job service wiring, actor lookup, error translation, and canonical payload assembly; `web/ogp_web/routes/jobs.py` remains the transport layer.
- Target source of truth: jobs orchestration should live in dedicated services, with routes reduced to auth/deps, request payload parsing, and response model serialization only.
- What changed in this task: `shrink`
- Why this was necessary: `jobs.py` still owned `AsyncJobService` construction, actor resolution, service-error translation, idempotency defaults, and route-local payload assembly for create/retry/cancel/list flows. Extracting those pieces removes a real route-local orchestration layer without changing route contracts.
- Rollback path: revert the extraction commit/PR or temporarily restore the inline helpers in `routes/jobs.py` if async job create/list/action behavior regresses.
- Removal gate: remove any remaining route-local compatibility glue once jobs API tests no longer need route-level dependency overrides and no remaining jobs route owns business orchestration.
- Tests covering this seam:
  - `python -m py_compile web/ogp_web/routes/jobs.py web/ogp_web/services/jobs_runtime_service.py web/ogp_web/dependencies.py`
  - `python -m pytest tests/test_jobs_runtime_service.py tests/test_async_jobs_layer.py -q`
  - `python -m pytest tests/test_web_api.py -q -k "jobs_list_route_uses_jobs_runtime_service or generate_async_route_uses_jobs_runtime_service_payload or admin_reindex_route_uses_jobs_runtime_service_defaults or admin_import_route_uses_jobs_runtime_service_validation"`
- Remaining risks:
  - `routes/jobs.py` still performs request-model parsing and response-model serialization by design
  - export and worker-specific behavior still depends on `AsyncJobService` and downstream worker handlers remaining contract-stable

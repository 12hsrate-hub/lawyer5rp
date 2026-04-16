# Compatibility Seam Note

- Seam ID: `seam-2026-04-exam-import-legacy-runner`
- Area: `web/ogp_web/services/exam_import_tasks.py` (`execute_transitional_runner`)
- Reason this seam exists: exam-import background tasks still support both the older runner contract without a progress callback and the newer runner contract that accepts one, so the task registry can keep executing legacy runners during the staged extraction of exam-import runtime orchestration.
- Current source of truth: `web/ogp_web/services/exam_import_tasks.py::execute_transitional_runner(...)` is the compatibility adapter for invoking exam-import runners regardless of whether they accept `progress_callback`.
- Target source of truth: exam-import background runners should converge on a single callback-aware contract so task execution no longer needs the transitional invocation shim.
- What changed in this task: `unchanged`
- Why this was necessary: the legacy runner adapter is active and tested today, but it was not documented separately from the broader exam-import route-boundary seam.
- Rollback path: if callback-aware runners regress, continue invoking background runners through `execute_transitional_runner(...)` and keep the current fallback-to-no-arg behavior until all callers are compatible again.
- Removal gate: remove the adapter once every exam-import background runner uses the callback-aware contract, no task path relies on `TypeError` fallback invocation, and async job tests no longer depend on the legacy invocation shape.
- Tests covering this seam:
  - `python -m pytest tests/test_async_jobs_layer.py -q -k "execute_transitional_runner"`
  - `python -m pytest tests/test_web_api.py -q -k "exam_import_background_tasks_support_row_and_bulk_scoring or exam_import_task_concurrency_limit_is_enforced or exam_import_background_task_returns_readable_error_details"`
- Remaining risks:
  - background task execution still tolerates two runner signatures, which can hide incomplete convergence on the callback-aware contract
  - the adapter is intentionally narrow, but it should not quietly expand beyond exam-import runner invocation

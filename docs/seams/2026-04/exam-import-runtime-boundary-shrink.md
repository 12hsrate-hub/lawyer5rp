# Compatibility Seam Note

- Seam ID: `seam-2026-04-exam-import-runtime-boundary`
- Area: `web/ogp_web/routes/exam_import.py` <-> `web/ogp_web/services/exam_import_runtime_service.py`
- Reason this seam exists: exam import routes still preserve route-level monkeypatch targets for scoring helpers while route-local scoring wrapper orchestration is being extracted into a dedicated runtime service without changing task/status or scoring response contracts.
- Current source of truth: `web/ogp_web/services/exam_import_runtime_service.py` for scoring wrapper lock and proxy-scoring monkeypatch orchestration; `web/ogp_web/routes/exam_import.py` remains the transport layer with compatibility wrappers.
- Target source of truth: exam import runtime scoring orchestration should live in dedicated services, with routes reduced to auth/deps, task boundary calls, and response serialization only.
- What changed in this task: `shrink`
- Why this was necessary: `exam_import.py` still contained route-local lock/monkeypatch orchestration for bulk scoring, row scoring, and failed rescoring. Extracting it removes real route orchestration without breaking existing monkeypatch-based API tests.
- Rollback path: revert the extraction commit/PR or temporarily restore the inline scoring wrappers in `routes/exam_import.py` if scoring or background-task behavior regresses.
- Removal gate: remove the route-level scoring wrapper aliases once exam import tests and task runners no longer patch route module symbols directly and no remaining exam-import route logic owns business orchestration.
- Tests covering this seam:
  - `python -m pytest tests/test_web_api.py -q -k "exam_import_page_imports_new_rows_and_supports_row_scoring or exam_import_background_tasks_support_row_and_bulk_scoring or exam_import_task_concurrency_limit_is_enforced or exam_import_background_task_returns_readable_error_details or exam_import_score_returns_readable_error_when_batch_fails"`
- Remaining risks:
  - task creation and entry/detail endpoints still live fully in `routes/exam_import.py`
  - route-level helper aliases are still required for current monkeypatch-driven regression tests

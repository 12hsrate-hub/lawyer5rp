# Exam Scoring Incident Runbook

## Scope
- Flow: exam import scoring (`ai_exam_scoring`).
- Components: `web/ogp_web/services/exam_import_service.py`, `shared/ogp_ai.py`, `web/ogp_web/storage/admin_metrics_store.py`.
- Primary symptoms: mass rescoring failures, rising retry chains, empty/invalid batch outputs, long scoring latency.

## Fast Triage (5-10 min)
1. Confirm current blast radius in admin metrics:
   - `ai_exam_failure_total`
   - `ai_exam_invalid_batch_items_total`
   - `ai_exam_retry_single_calls_total`
   - `ai_exam_scoring_ms_p95`
2. Check latest failed rows:
   - `exam_import_score_failures`
   - `exam_import_row_score_error`
3. Validate OpenAI connectivity and route behavior:
   - `OPENAI_API_KEY`
   - `OPENAI_PROXY_URL`
   - `OPENAI_ROUTE_POLICY`
4. Validate prompt mode and rollback file:
   - `OPENAI_EXAM_SCORING_PROMPT_MODE`
   - `OPENAI_EXAM_SCORING_PROMPT_MODE_FILE`

## Diagnosis Matrix
- High `invalid_batch_item_count`, normal latency:
  - Likely response-shape drift or prompt/output mismatch.
  - Verify `prompt_mode`, `prompt_version`, `single_prompt_version` in `ai_exam_scoring` meta.
- High `retry_single_calls_total` with high latency:
  - Batch output unstable; single fallback doing most work.
  - Check model health and temporary overload.
- Spikes in `exam_import_score_failures`:
  - Infra or provider outage, invalid credentials, timeout/network failures.
- Sudden score drift without failure spikes:
  - Prompt-mode/config change or model route change.
  - Validate against golden baseline tests.

## Immediate Stabilization
1. Switch to stable full prompt mode (no redeploy):
   - Set override file content to `full`.
2. If proxy path is unstable, switch route policy:
   - `OPENAI_ROUTE_POLICY=direct_first` (or `proxy_first` when direct is blocked).
3. Reduce concurrent pressure:
   - Lower `OPENAI_EXAM_SINGLE_MAX_CONCURRENCY`.
   - Lower `OPENAI_EXAM_BATCH_MAX_CONCURRENCY`.
4. Pause bulk rescoring jobs; process critical rows manually first.

## Rollback Actions
- Prompt rollback:
  - `OPENAI_EXAM_SCORING_PROMPT_MODE=full`
  - or override file with `full`.
- Route rollback:
  - `OPENAI_ROUTE_POLICY=proxy_only|proxy_first|direct_first` per incident.
- Capacity rollback:
  - reduce concurrency env values and restart service.

## Recovery Validation Checklist
1. `ai_exam_failure_total` stops increasing.
2. `ai_exam_retry_single_calls_total / ai_exam_llm_calls_total` returns to baseline.
3. `ai_exam_scoring_ms_p95` returns below agreed threshold.
4. Random sample of rescored rows has consistent rationale quality.
5. Golden regression tests pass:
   - `python -m pytest tests/test_exam_scoring_golden.py`

## Post-Incident Follow-up
- Capture root cause and change summary.
- Add/adjust guard test reproducing the incident.
- Revisit thresholds in rollout-gates doc.

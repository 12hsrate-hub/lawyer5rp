# Exam Scoring Rollout Gates and KPIs

## Objective
Define stop/go criteria for safe rollout of exam scoring changes (prompt mode, retry policy, retrieval/mapping updates).

## Rollout Phases
1. Phase A: internal validation (0% user impact)
2. Phase B: canary 10%
3. Phase C: canary 50%
4. Phase D: full rollout 100%

## Hard Stop Gates (No-Go)
- `ai_exam_failure_total` trend increases continuously for 15+ minutes.
- `ai_exam_scoring_ms_p95` exceeds baseline by more than 35%.
- `retry_single_rate` exceeds threshold:
  - `ai_exam_retry_single_calls_total / max(ai_exam_llm_calls_total, 1) > 0.35`
- Golden regression gate fails:
  - `python -m pytest tests/test_exam_scoring_golden.py` not green.

## Soft Warning Gates (Investigate Before Progress)
- `invalid_batch_rate` rises:
  - `ai_exam_invalid_batch_items_total / max(ai_exam_scoring_answers, 1) > 0.15`
- `cache_hit_share` drops abruptly vs baseline.
- `llm_calls_per_1000_items` grows more than 20% vs baseline.

## Core KPIs
- Reliability:
  - `wrong-law rate` (from feedback labels)
  - `wrong-fact rate` (from feedback labels)
  - `guard pass rate`
- Efficiency:
  - `median total tokens`
  - `p95 total tokens`
  - `cost per successful scored row`
- Latency:
  - `ai_exam_scoring_ms_p50`
  - `ai_exam_scoring_ms_p95`

## Target Thresholds (Initial)
- `ai_exam_scoring_ms_p95` <= 1.35x baseline.
- `retry_single_rate` <= 0.35.
- `invalid_batch_rate` <= 0.15.
- Golden regression failures <= configured baseline threshold.

## Stop/Go Decision Template
- Decision: `go` / `hold` / `rollback`
- Phase: A/B/C/D
- Key metrics snapshot:
  - failures:
  - retry_single_rate:
  - invalid_batch_rate:
  - p95 latency:
  - golden result:
- Action owner:
- Timestamp:

## Required Evidence Before 100%
1. Canary 10% passed.
2. Canary 50% passed.
3. Golden baseline stable.
4. Incident runbook reviewed and current.
5. Rollback switch verified (`prompt_mode`, `route_policy`, concurrency caps).

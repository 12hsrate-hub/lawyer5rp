# Suggest Rollout Safety Runbook

This runbook defines how to enable suggest optimizations in stages, what artifacts must be reviewed at each stage, and how to roll back safely if latency or collateral impact regresses.

## Suggested feature flags

Use server-level feature flags or environment toggles with the same intent:

- `suggest_retrieval_lightweight`
  Enable the lighter retrieval query for suggest retrieval only.
- `suggest_retrieval_two_stage`
  Enable cheap prefilter + bounded rerank for suggest retrieval.
- `suggest_route_limits`
  Enforce overload protection and 429 handling for `/api/ai/suggest`.

## Rollout order

### 1. `telemetry_only`

Goal:

- keep current behavior
- collect timings, usage, and load-test artifacts

Required checks:

- single-profile report is healthy
- parallel-profile report passes SLA
- mixed-load report shows acceptable Group B impact

Do not enable:

- `suggest_retrieval_lightweight`
- `suggest_retrieval_two_stage`
- `suggest_route_limits`

### 2. `optimization`

Goal:

- enable retrieval optimizations without changing overload policy

Enable:

- `suggest_retrieval_lightweight`
- `suggest_retrieval_two_stage`

Keep disabled:

- `suggest_route_limits`

Required checks:

- compare fresh single-profile result against telemetry-only baseline
- compare parallel-profile result against telemetry-only baseline
- mixed-load collateral impact remains within allowed growth

### 3. `limits`

Goal:

- keep optimized retrieval
- add overload protection for production safety

Enable:

- `suggest_retrieval_lightweight`
- `suggest_retrieval_two_stage`
- `suggest_route_limits`

Required checks:

- single-profile and parallel-profile overload behavior is intentional
- mixed-load result still protects non-AI endpoints
- admin telemetry shows overloads stay within acceptable rate

## Operational thresholds

Recommended starting thresholds:

- single-profile `p95 <= 2500 ms`
- single-profile `error_rate <= 0.05`
- parallel summary: `all_sla_pass == true`
- mixed-load collateral impact:
  - Group B `p95` growth `<= 0.25`
  - Group B `p99` growth `<= 0.25`

If these thresholds need to move, change them explicitly in the run config and note the reason in the rollout ticket.

## Required artifact set

Before advancing a stage, collect:

- one single-profile summary
- one parallel-profile summary
- one mixed-load summary
- optional server telemetry summaries when `--sample-server` is used

Then evaluate them together:

```powershell
py scripts/evaluate_suggest_rollout.py `
  --single-summary artifacts/load/<single_run>/<profile>/summary.json `
  --parallel-summary artifacts/load/<parallel_run>/parallel/summary.json `
  --mixed-summary artifacts/load/<mixed_run>/mixed/summary.json `
  --stage telemetry_only `
  --output-dir artifacts/load/<evaluation_run>/rollout `
  --fail-on-blockers
```

Artifacts written by the evaluator:

- `rollout_summary.json`
- `rollout_report.md`

## Rollback steps

If latency, cost, or collateral impact regresses:

1. Disable `suggest_route_limits` first if user-visible overload behavior is too aggressive.
2. Disable `suggest_retrieval_two_stage` if relevance or latency worsens after rerank changes.
3. Disable `suggest_retrieval_lightweight` if retrieval quality drops due to query compression.
4. Return to `telemetry_only` and rerun single / parallel / mixed validation.

## When to hold rollout

Do not advance the stage if:

- single-profile summary breaches its p95 or error thresholds
- parallel summary has any failing profile
- mixed summary breaches collateral-impact growth limits
- server telemetry shows sustained CPU / memory pressure that correlates with degraded Group B latency

## Notes

- Treat `telemetry_only` as the default safe state.
- Promote only one stage at a time.
- Keep the previous stage's artifacts for comparison so regressions stay visible.

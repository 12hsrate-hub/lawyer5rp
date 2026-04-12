# Model Policy And SLO

## Baseline KPI Bands

| Metric | Green | Yellow | Red |
| --- | --- | --- | --- |
| `guard_fail_rate` (24h) | `< 1.5%` | `1.5-3.0%` | `> 3.0%` |
| `guard_warn_rate` (24h) | `< 8%` | `8-15%` | `> 15%` |
| `wrong_law_rate` | `< 2.0%` | `2.0-4.0%` | `> 4.0%` |
| `hallucination_rate` | `< 0.8%` | `0.8-1.5%` | `> 1.5%` |
| `unclear_answer_rate` | `< 5%` | `5-9%` | `> 9%` |
| `p95_latency_law_qa` | `< 7s` | `7-10s` | `> 10s` |
| `p95_latency_suggest` | `< 9s` | `9-13s` | `> 13s` |
| `avg_cost_per_req_law_qa` | target | `+15%` | `+30%` |
| `avg_cost_per_req_suggest` | target | `+15%` | `+30%` |

## Automatic Policy Actions

- Any `guard_fail` on a single generation: retry immediately on the next stronger tier (`nano -> mini`, `mini -> full`).
- `guard_fail_rate > 3%` over 1h: force minimum tier `mini`, disable `nano` for 6h.
- `wrong_law_rate > 4%` over 24h: force `full` for `law_qa` for 24h.
- `hallucination_rate > 1.5%`: enable strict mode and force `full` on low-confidence requests for 24h.
- `p95_latency` in red while quality stays green: lower tier for the simple segment for 2h.
- Cost uplift above 30% with green quality: increase cheap-tier share by 15% until next review.

## Routing Rules

### Law QA
- Default: `gpt-5.4-mini`
- If `retrieval_confidence=low` or `context_compacted=true`: `gpt-5.4`
- If `retrieval_confidence=high` and the question is short and there is no history warning: `gpt-5.4-nano` only behind a feature flag
- On `guard_fail`: escalate by one tier and retry once

### Suggest
- Default: `gpt-5.4-mini`
- If `low_confidence_context` or there is prior `wrong_fact` / `wrong_law` history for the user or scenario: `gpt-5.4`
- For short editorial rewrite or cleanup requests: `gpt-5.4-nano`
- If critical `guard_warn` happens twice in a row: disable `nano`, use `mini/full` for 24h

## Cheap-Tier Rollout

- Stage 1: 10% traffic, promote after 3 days if quality is no worse than baseline by more than 10%
- Stage 2: 30% traffic, promote after 7 days if `wrong_law` and `hallucination` stay in green/yellow
- Stage 3: 60% traffic, promote after 7 days if stable cost win is at least 25%
- Stage 4: 100% traffic, promote after 14 days with no red incidents

Immediate rollback if:
- `guard_fail_rate` stays red for 2h
- `wrong_law_rate > 5%` over 24h
- inaccuracy complaints grow more than 2x baseline

## Daily Admin Checklist

- Quality: `guard_fail_rate`, `guard_warn_rate`, `wrong_law_rate`, `hallucination_rate`, `unclear_answer_rate`
- Cost: `avg_cost_per_req` by flow/model, `estimated_cost_total_usd` day-to-date
- Stability: `p95 latency`, `p99 latency`, `fallback_rate`
- Accuracy drill-down: top `generation_id` for `wrong_law` and `hallucination`, answer/source/guard/feedback comparison

## Recommended Defaults

- Default tier: `gpt-5.4-mini`
- `nano` only on 10% of simple cases
- Auto-escalation: enabled
- Manual model selection in UI: disabled
- Review cadence: daily operational review, weekly policy review

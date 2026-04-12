# Point3 Legal Mode Rollout

## Stages
1. 10%
2. 25%
3. 50%
4. 100%

Advance only after at least 24 hours of stable behavior on each stage, except the 100% stage which requires 48 hours of stable behavior before final confirmation.

## Promotion Criteria
- `factual_integrity >= 1.00`
- `style_contract >= 0.995`
- `legal_linkage_high_relevance >= 0.85`
- `retry_rate <= 0.12`
- `max_cost_uplift <= 0.35`

## Auto-Rollback Conditions
- `retry_rate > 0.12`
- `cost_uplift > 0.35`
- any drop in `factual_integrity`

## Immediate Rollback Actions
- set `rollout_legal_mode.emergency_off=true`
- set `rollout_legal_mode.force_mode=factual_only`


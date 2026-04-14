# Point3 Legal Mode Rollout

> Scope: rollout gating for point3 legal mode.
> Start from [`OPERATIONS_INDEX.md`](./OPERATIONS_INDEX.md) for related rollback/deploy docs.

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

## Cutover Rollback Window
- Rollback procedure must be prepared and validated before production cutover.
- Rollback window remains active for **7 calendar days after release**.
- During rollback window, each production issue in critical flows is assessed against rollback triggers before applying forward fixes.

## Required Regression After Every Sprint
- registration/login
- complaint generation
- admin review
- exam import

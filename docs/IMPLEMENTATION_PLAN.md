# Point3 Legal Mode Rollout Plan

## Scope
This phase establishes the baseline prompt contract and quality gates for point3 legal mode rollout.

## Active Modes
- `factual_only`
- `factual_plus_legal`

## Execution Order
1. Lock the prompt contract and quality gates.
2. Add relevance routing and feature flags.
3. Limit retries and document non-retryable failures.
4. Add a single checks entrypoint.
5. Add focused point3 tests.
6. Prepare rollout and incident docs.

## Guardrails
- Do not add new facts, dates, documents, numbers, or links.
- Keep responses in one neutral business paragraph.
- On weak context, force `factual_only`.
- Allow at most one retry.
- On metric degradation, roll back to `factual_only`.

## Current Fallback Policy
- `factual_integrity` failure must immediately fall back to `factual_only`.
- Relevance and cost degradations must trigger rollback controls.


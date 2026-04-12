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
7. Before Sprint 1, capture baseline metrics for:
   - login success rate
   - `/health` availability and status code stability
   - latency of key endpoints (`/login`, `/complaint`, `/admin`, `/exam_import`)
8. After each sprint, run regression for critical flows:
   - registration/login
   - complaint generation
   - admin review
   - exam import
9. Before cutover, prepare rollback procedure and rollback validity window (default: 7 days after release).
10. Fix owners for DB migrations, runtime stores, scripts, tests, and release.

## Guardrails
- Do not add new facts, dates, documents, numbers, or links.
- Keep responses in one neutral business paragraph.
- On weak context, force `factual_only`.
- Allow at most one retry.
- On metric degradation, roll back to `factual_only`.

## Current Fallback Policy
- `factual_integrity` failure must immediately fall back to `factual_only`.
- Relevance and cost degradations must trigger rollback controls.

## Ownership Matrix
- DB migrations — **TBD (assign before Sprint 1)**
- Runtime stores — **TBD (assign before Sprint 1)**
- Scripts — **TBD (assign before Sprint 1)**
- Tests — **TBD (assign before Sprint 1)**
- Release — **TBD (assign before Sprint 1)**

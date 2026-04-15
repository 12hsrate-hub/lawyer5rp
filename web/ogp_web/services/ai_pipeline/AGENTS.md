# Scoped instructions: web/ogp_web/services/ai_pipeline

## Role of this layer
- Own AI orchestration logic, retries, guardrails, context assembly, and telemetry contracts.

## Must do
- Keep `ai_service.py` as a facade; put orchestration changes here.
- Preserve facade compatibility contracts and telemetry/provenance fields.
- Keep retry/idempotency and failure behavior explicit and test-covered.
- Run ai_pipeline contract/orchestration checks from `TESTING_RULES.md`.

## Must not do
- No route-layer logic leakage into pipeline modules.
- No hidden model/provider branching without contract updates.
- No undocumented seam expansion between legacy and new orchestration paths.

## Coordination
- Follow root `AGENTS.md`, `ARCHITECTURE_RULES.md`, and `TESTING_RULES.md`.
- If a compatibility seam is touched, create or update a note at `docs/seams/YYYY-MM/<slug>.md` using `docs/templates/COMPATIBILITY_SEAM_NOTE.md` as the template source.

# Scoped instructions: web/ogp_web/services

## Role of this layer
- Services own business logic, orchestration, and domain policy composition.

## Must do
- Prefer extraction of orchestration from legacy routes when touching those flows.
- Keep service contracts stable or explicitly version/announce contract changes.
- Keep server-specific behavior driven by config/workflow/capabilities.
- Run service-level checks required by `TESTING_RULES.md`.

## Must not do
- No direct UI/template concerns in service logic.
- No persistence schema mutations without migration discipline.
- No undocumented compatibility seam expansion.

## Coordination
- `services/ai_pipeline/AGENTS.md` takes precedence for files in that subtree.
- Follow root governance docs.
- If a compatibility seam is touched, create or update a note at `docs/seams/YYYY-MM/<slug>.md` using `docs/templates/COMPATIBILITY_SEAM_NOTE.md` as the template source, and reference that path in the summary.

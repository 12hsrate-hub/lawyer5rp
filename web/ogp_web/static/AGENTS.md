# Scoped instructions: web/ogp_web/static

## Role of this layer
- Frontend scripts/styles provide presentation and client interaction behavior.

## Must do
- Keep client logic aligned with server/API contracts.
- Preserve admin/user terminology consistency.
- Keep module boundaries clear (`pages/` page glue, `shared/` reusable helpers).
- Run relevant frontend syntax/contract checks when touched.

## Must not do
- No hidden business-policy forks in client code.
- No hardcoded server-specific business logic in UI scripts.

## Coordination
- Follow root `AGENTS.md`, `ARCHITECTURE_RULES.md`, and `TESTING_RULES.md`.
- If a compatibility seam is touched, create or update a note at `docs/seams/YYYY-MM/<slug>.md` using `docs/templates/COMPATIBILITY_SEAM_NOTE.md` as the template source.

# Scoped instructions: web/ogp_web/workers

## Role of this layer
- Workers execute async tasks and lifecycle transitions safely.

## Must do
- Keep task lifecycle states explicit.
- Preserve idempotency and retry discipline.
- Keep job status visibility intact for API/admin consumers.
- Run worker/async checks required by `TESTING_RULES.md`.

## Must not do
- No business workflow decisions hidden only in worker code.
- No non-audited state mutation shortcuts.
- No server-specific branching shortcuts for behavior.

## Coordination
- Follow root `AGENTS.md`, `ARCHITECTURE_RULES.md`, and `TESTING_RULES.md`.
- If a compatibility seam is touched, create or update a note at `docs/seams/YYYY-MM/<slug>.md` using `docs/templates/COMPATIBILITY_SEAM_NOTE.md` as the template source.

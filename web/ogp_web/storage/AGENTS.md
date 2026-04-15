# Scoped instructions: web/ogp_web/storage

## Role of this layer
- Storage/repositories implement data access and persistence mapping only.

## Must do
- Keep methods deterministic and focused on read/write operations.
- Keep schema/persistence concerns explicit.
- Preserve backward-compatible read paths when legacy data may exist.
- Run persistence checks required by `TESTING_RULES.md`.

## Must not do
- No domain orchestration, policy decisions, or route concerns.
- No server-specific branching shortcuts for business behavior.
- No workflow bypass for law/template/rule runtime-effective state.

## Coordination
- Follow root `AGENTS.md`, `ARCHITECTURE_RULES.md`, and `LAW_PLATFORM_RULES.md`.
- If a compatibility seam is touched, create or update a note at `docs/seams/YYYY-MM/<slug>.md` using `docs/templates/COMPATIBILITY_SEAM_NOTE.md` as the template source.

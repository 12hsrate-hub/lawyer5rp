# Scoped instructions: web/ogp_web/db

## Role of this layer
- Provide database backend integration and migration framework wiring.

## Must do
- Keep backend behavior deterministic and environment-explicit.
- Preserve backward-compatible read/write behavior during transitions.
- Run persistence and migration checks per `TESTING_RULES.md` when touched.

## Must not do
- No domain business policy in db adapters.
- No schema-changing behavior without migration plan/rollback implications.

## Coordination
- `web/ogp_web/db/migrations/AGENTS.md` takes precedence in the migrations subtree.
- Follow root `AGENTS.md` and `ARCHITECTURE_RULES.md`.

# Scoped instructions: web/ogp_web/db/migrations

## Role of this layer
- Encode schema/data transition steps with clear forward and rollback implications.

## Must do
- Keep migrations idempotent where practical and safe to re-run in controlled environments.
- Document assumptions and rollback implications in migration/task summary.
- Ensure migration ordering and compatibility with existing production state.

## Must not do
- No hidden runtime behavior changes without corresponding service/route contract review.
- No irreversible data operations without explicit rollback/containment note.

## Coordination
- Follow root `AGENTS.md`, `TESTING_RULES.md`, and operational migration docs.

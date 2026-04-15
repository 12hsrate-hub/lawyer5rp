# Scoped instructions: scripts

## Role of this layer
- Operational and maintenance scripts for deploy, migration, validation, and support tasks.

## Must do
- Keep scripts safe-by-default and explicit about side effects.
- Preserve deploy flow expectations from root `AGENTS.md`.
- Document required env vars/inputs and failure modes.

## Must not do
- No bypass of canonical deploy path by ad hoc file copying.
- No destructive operations without clear confirmation or containment guidance.

## Coordination
- Follow root governance docs.
- If a compatibility seam is touched, create or update a note at `docs/seams/YYYY-MM/<slug>.md` using `docs/templates/COMPATIBILITY_SEAM_NOTE.md` as the template source, and reference that path in the summary.

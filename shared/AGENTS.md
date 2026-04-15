# Scoped instructions: shared

## Role of this layer
- Shared modules provide reusable cross-surface logic and contracts.

## Must do
- Keep public interfaces stable or document contract changes explicitly.
- Keep behavior framework-agnostic where possible.
- Add or update tests for shared contract changes.

## Must not do
- No web-route specific orchestration in shared utilities.
- No hidden compatibility seam expansion.

## Coordination
- Follow root governance docs and `TESTING_RULES.md`.
- If a compatibility seam is touched, create or update a note at `docs/seams/YYYY-MM/<slug>.md` using `docs/templates/COMPATIBILITY_SEAM_NOTE.md` as the template source.

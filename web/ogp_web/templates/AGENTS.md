# Scoped instructions: web/ogp_web/templates

## Role of this layer
- Templates are presentation-only.

## Must do
- Keep rendering logic minimal and readable.
- Keep terminology consistent with user/admin language.
- Delegate domain decisions to routes/services.

## Must not do
- No persistence or domain orchestration in templates.
- No server-specific branching logic in template markup.
- No business-policy drift from service contracts.

## Coordination
- Follow root `AGENTS.md` and `ARCHITECTURE_RULES.md`.
- If template changes touch a compatibility seam, create or update a note at `docs/seams/YYYY-MM/<slug>.md` using `docs/templates/COMPATIBILITY_SEAM_NOTE.md` as the template source.

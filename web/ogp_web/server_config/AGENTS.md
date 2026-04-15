# Scoped instructions: web/ogp_web/server_config

## Role of this layer
- Define server identity, capability resolution, and runtime-effective server configuration.

## Must do
- Keep server behavior config/workflow-driven where possible.
- Keep bootstrap/fallback logic explicit and auditable.
- Document why fallback paths remain necessary when touched.
- Run `server_config/*` checks required by `TESTING_RULES.md`.

## Must not do
- No ad hoc server-specific business branching outside defined capability/config surfaces.
- No hidden single-server assumptions.

## Coordination
- Follow root `AGENTS.md`, `ARCHITECTURE_RULES.md`, `NEW_SERVER_CHECKLIST.md`, and `LAW_PLATFORM_RULES.md`.
- If a compatibility seam is touched, create or update a note at `docs/seams/YYYY-MM/<slug>.md` using `docs/templates/COMPATIBILITY_SEAM_NOTE.md` as the template source.

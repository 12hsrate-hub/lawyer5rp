# Scoped instructions: web/ogp_web/routes

## Role of this layer
- Routes are transport-first adapters.
- Routes may parse/validate request payloads, resolve auth/dependencies, call services, and serialize responses.

## Must do
- Keep business rules and orchestration in services.
- Do not add new orchestration in routes.
- When touching legacy-heavy route logic, prefer extracting orchestration into services.
- Keep persistence access behind storage/repository/service boundaries.
- Preserve route/API compatibility unless explicitly documented.
- Run route-relevant checks from `TESTING_RULES.md`.

## Must not do
- No direct multi-store orchestration in route handlers.
- No ad hoc server-specific business branching that bypasses config/workflow/bindings/capabilities.
- Legitimate permission/ownership/scope guards are allowed.
- No hidden compatibility seam expansion.

## Coordination
- Follow root `AGENTS.md`, `ARCHITECTURE_RULES.md`, and `TESTING_RULES.md`.
- If a compatibility seam is touched, create or update a note at `docs/seams/YYYY-MM/<slug>.md` using `docs/templates/COMPATIBILITY_SEAM_NOTE.md` as the template source.

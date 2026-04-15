# Scoped instructions: web/ogp_web/providers

## Role of this layer
- Provider adapters encapsulate external system integration details.

## Must do
- Keep provider behavior behind explicit adapter interfaces.
- Keep error/retry behavior explicit and predictable.
- Preserve provider contract compatibility for service callers.
- Run relevant provider-facing checks from `TESTING_RULES.md`.

## Must not do
- No domain business policy in provider adapters.
- No ad hoc server-specific business branching that bypasses config/workflow/capabilities.

## Coordination
- Follow root governance docs and service boundary rules.
- If a compatibility seam is touched, create or update a note at `docs/seams/YYYY-MM/<slug>.md` using `docs/templates/COMPATIBILITY_SEAM_NOTE.md` as the template source.

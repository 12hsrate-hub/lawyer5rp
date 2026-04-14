# Code quality audit — 2026-04-14

## Scope and approach

- Ran project-wide static checks and a targeted cleanup pass.
- Prioritized safe readability and maintainability improvements that do not change business logic.

## Current status (after this pass)

- `ruff --select F401,F541,F841,E731,F811,F821` now passes on the whole repository.
- Remaining lint debt is concentrated in `E402` (`module import not at top of file`) for bootstrap scripts/tests where `sys.path` and env are configured before imports.

## Signals found

### 1) Readability / architecture pressure points

- `web/ogp_web/routes/admin.py` remains oversized and combines API endpoints with task persistence, KPI aggregation, caching, and policy logic.
- `web/ogp_web/routes/complaint.py` still mixes endpoint orchestration with feature-flag and validation concerns.

**Recommendation (next iterations):**
- Extract admin task persistence into a dedicated module (e.g., `services/admin_tasks_service.py`).
- Extract admin KPI aggregations into pure functions under `services/admin_dashboard_metrics.py`.
- Keep route files as thin controller layers.

### 2) Duplication candidates

- Repeated `TemplateResponse(..., _build_page_context(...))` flows in page routes are structural duplication.
- Repeated metrics payload construction patterns in multiple route handlers.

**Recommendation:**
- Introduce helper factories for page rendering and metrics payload normalization.

### 3) Unused / stale code indicators fixed

This pass removed or corrected high-signal issues:

1. Unused imports in scripts/tests/services (`F401`).
2. Duplicate or dead local variables in tests (`F841`, `F811`).
3. Non-placeholder f-strings (`F541`).
4. Lambda assignment in task runner replaced with named local callback (`E731`).
5. Missing helper reference and undefined-name issues (`F821`).

### 4) Outdated patterns still present

- Many entrypoints/tests intentionally mutate `sys.path` before imports. This triggers `E402` globally.
- Pattern is functional, but should be reduced over time with package-aware runners and cleaner bootstrap modules.

## Follow-up backlog

- Split `admin.py` by domain (catalog, runtime servers, law sets, metrics).
- Introduce project-level lint configuration to scope/document intentional `E402` in bootstraps.
- Add dead-code scan stage (e.g., `vulture`) with baseline/allowlist.

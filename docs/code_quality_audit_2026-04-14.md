# Code quality audit — 2026-04-14

## Scope and approach

- Ran static checks to detect readability issues and obvious dead code signals.
- Focused this pass on low-risk cleanup that improves maintainability without changing business behavior.

## Signals found

### 1) Readability / architecture pressure points

- `web/ogp_web/routes/admin.py` is very large and combines API endpoints with task persistence, KPI aggregation, cache logic, and policy helpers.
- `web/ogp_web/routes/complaint.py` mixes endpoint orchestration, feature-flag metrics, and validation logic in long handlers.

**Recommendation (next iterations):**
- Extract admin task persistence into a dedicated module (e.g., `services/admin_tasks_service.py`).
- Extract admin KPI aggregations into pure functions under `services/admin_dashboard_metrics.py`.
- Keep route files as thin controller layers.

### 2) Duplication candidates

- Repeated `TemplateResponse(..., _build_page_context(...))` flows in page routes are mostly structural duplication.
- Repeated metrics event payload construction patterns in route handlers.

**Recommendation:**
- Introduce small helper factories for templated page rendering and metrics payload normalization.

### 3) Unused / stale code indicators

- Static lint sweep showed several unused imports and one missing helper reference.
- This pass fixed the missing helper reference and several high-signal cleanup items listed below.

### 4) Outdated patterns

- Multiple modules intentionally manipulate `sys.path` before imports; lint marks these as `E402`.
- This is workable for script entrypoints/tests, but should be replaced gradually with package-aware runners.

## Changes implemented in this pass

1. Added explicit public re-export contract in `web/ogp_web/auth.py` via `__all__` for clarity and tooling compatibility.
2. Added missing `_load_admin_tasks()` helper in `web/ogp_web/routes/admin.py` to support `/api/admin/law-jobs/overview` reliably.
3. Removed unused feature-flag local variable in `web/ogp_web/routes/complaint.py`.
4. Improved `web/ogp_web/services/law_version_service.py` readability (spacing) and fixed forward type annotation (`LawChunk`) to avoid undefined-name lint errors.

## Follow-up backlog

- Split `admin.py` by domain (catalog, runtime servers, law sets, metrics).
- Add project-level lint configuration so intentional `E402` in bootstrap scripts/tests is scoped and documented.
- Run a dedicated dead-code tool (e.g., `vulture`) after introducing baseline ignore list.

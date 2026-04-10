# Frontend Roadmap (SSR-first)

## Strategy

Primary path for this repository:

1. Evolve existing SSR (`FastAPI + Jinja2 + page JS`) as the baseline.
2. Add selective HTMX for screens that need partial dynamic updates.
3. Consider SPA only when product metrics prove a clear need.

## Current baseline

- Backend/web architecture is already SSR-first.
- Main UI entry points are template-based and production-ready.
- Static assets are versioned with `static_asset_version`.

## 6-8 week execution plan

### Weeks 1-2: UI foundation

- Establish design tokens in CSS variables:
  - color, spacing, radius, shadows, typography, focus states.
- Normalize base components:
  - buttons, form controls, panels, alerts, table shell.
- Files:
  - `web/ogp_web/static/styles/base.css`
  - `web/ogp_web/static/styles/legal.css`
  - `web/ogp_web/static/styles/auth.css`

### Weeks 2-4: Core layout refresh

- Refresh shared page structure and section hierarchy.
- Improve visual consistency across legal forms.
- Files:
  - `web/ogp_web/templates/layouts/base.html`
  - `web/ogp_web/templates/partials/page_nav.html`
  - `web/ogp_web/templates/partials/complaint/*.html`
  - `web/ogp_web/templates/profile.html`

### Weeks 4-6: Priority pages

- `complaint` UX pass:
  - reduce friction in long form completion.
- `profile` UX pass:
  - cleaner account and password update flows.
- Add targeted behavior polish in page JS:
  - `web/ogp_web/static/pages/complaint.js`
  - `web/ogp_web/static/pages/profile.js`

### Weeks 6-8: HTMX pilot

- Pick one admin/list screen and replace one JS-heavy refresh path with HTMX.
- Measure response time and implementation complexity before wider rollout.

## KPIs

- LCP on key pages.
- Time-to-complete for complaint submission.
- Validation errors per user on key forms.
- Engineering hours per UI release.

## Delivery rule

No big-bang migration. Ship small, testable increments and keep deploy path:

Local changes -> local tests -> GitHub `main` -> server deploy from GitHub.

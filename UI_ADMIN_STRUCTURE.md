# UI_ADMIN_STRUCTURE.md

Status: active
Date: 2026-04-16
Phase: `Server-centric MVP`

## Purpose

Define the current admin information architecture after the server-centric workspace became the primary operator path.

## Primary entrypoints

The primary admin workspace is:

- `/admin/servers`
- `/admin/servers/{server_code}`

Compatibility and secondary entrypoints remain available:

- `/admin/dashboard`
- `/admin/ops`
- `/admin/users`
- `/admin/audit`
- `/admin/servers`
- `/admin/laws`

Route policy:

- `/admin/servers` is the default starting point for day-to-day admin work.
- `/admin/servers/{server_code}` is the primary workspace for server-specific operations.
- `/admin/laws` remains an advanced diagnostics and compatibility surface.
- `/admin/dashboard` remains the compatibility route for the global ops surface.
- `/admin/ops` is the preferred secondary entrypoint for the global ops surface.
- `/admin/users` remains the compatibility route for the global user/audit surface.
- `/admin/audit` is the preferred secondary entrypoint for the global user/audit surface.
- the primary top-level admin tab strip should point only to `/admin/servers`
- global ops and global users/audit should appear as secondary links, not as competing primary tabs
- `/admin/templates`, `/admin/features`, and `/admin/rules` are no longer primary entrypoints and should not be restored as top-level operator tabs.
- `/admin/laws` must not be used as the primary onboarding or day-to-day configuration entrypoint for a server.

## Migration policy

The current migration mode is:

- `new admin = primary`
- `old law-centric surface = advanced / compatibility`

Operational rule:

- start normal admin work from `/admin/servers`
- open `/admin/servers/{server_code}` for server-specific setup and maintenance
- use `/admin/laws` only when raw law diagnostics or compatibility-backed internals are explicitly needed

## Domain map

### Dashboard / Ops

- Route entry: `/admin/ops`, `/admin/dashboard`
- Primary concerns:
  - system totals
  - performance
  - exam import operations
  - endpoint activity
  - synthetic checks

### Users and audit

- Route entry: `/admin/audit`, `/admin/users`
- Primary concerns:
  - user moderation
  - role history
  - event stream
  - cost / model policy / AI pipeline visibility

### Server-centric workspace

- Route entry:
  - `/admin/servers`
  - `/admin/servers/{server_code}`
- Primary concerns:
  - overview and readiness
  - server laws
  - server features
  - output templates
  - users and access
  - audit and issues
  - diagnostics handoff

### Compatibility / advanced law domain

- Route entry:
  - `/admin/laws`
- Primary concerns:
  - raw law diagnostics
  - legacy/runtime detail
  - compatibility-backed law workflows
  - source-set and binding internals
- Not for:
  - initial server onboarding
  - everyday server setup
  - primary feature/template/access work

## Current operating model

The current operator happy path is:

1. `/admin/servers`
2. open `/admin/servers/{server_code}`
3. work through:
   - `Законы`
   - `Функции`
   - `Шаблоны вывода`
   - `Пользователи`
   - `Роли / Доступ`
   - `Аудит`
   - `Ошибки / Проблемы`

Advanced paths stay secondary and must not compete visually with the server-centric workspace.

### Secondary surfaces

- `/admin/dashboard`
  - global operations, jobs, synthetic, rollout signals
- `/admin/ops`
  - preferred secondary entrypoint for global ops
- `/admin/users`
  - global users, role history, event stream, AI/cost policy
- `/admin/audit`
  - preferred secondary entrypoint for global users and audit
- `/admin/laws`
  - advanced law diagnostics and compatibility-backed internals
  - not a primary operator workspace

## Boundary rules

- Keep runtime behavior unchanged.
- Keep canonical law-domain architecture unchanged.
- Do not restore old law-centric or catalog-centric screens as equal primary paths.
- Prefer server-centric UX for any operator-facing addition that is server-scoped.
- Keep diagnostics and compatibility entrypoints reachable, but visually secondary.
- Do not direct a new operator to `/admin/laws` when `/admin/servers/{server_code}` already covers the task.

## Rendering rules

- Each admin surface must clearly indicate whether it is:
  - primary workspace
  - global ops/global admin
  - advanced diagnostics / compatibility
- Server-specific work must point users back to `/admin/servers/{server_code}`.
- Raw internal identifiers should not be the primary visible label.
- User-facing copy should prefer domain language from `docs/ADMIN_GLOSSARY.md`.

## What this structure does not do

- No full component-library rewrite
- No deletion of legacy backend seams that still back compatibility flows
- No return to flat per-server law source modeling
- No requirement that every global screen be moved into the server card if it is truly global by nature

## Next structural step

After primary/advanced policy is fully stable, the next step is to continue progressive redirect and compatibility reduction without breaking raw diagnostic access.

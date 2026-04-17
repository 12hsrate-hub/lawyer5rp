# Admin Panel

Status: active  
Date: 2026-04-17

## Purpose

This document is the canonical reference for admin information architecture, operator entrypoints, and user-facing terminology.

It replaces the older split between separate admin-structure and admin-glossary docs.

## Primary entrypoints

The primary admin workspace is:

- `/admin/servers`
- `/admin/servers/{server_code}`

Secondary or compatibility entrypoints remain available:

- `/admin/ops`
- `/admin/dashboard` -> compatibility redirect to `/admin/ops`
- `/admin/audit`
- `/admin/users` -> compatibility redirect to `/admin/audit`
- `/admin/laws` -> advanced diagnostics and compatibility surface

## Route policy

- `/admin/servers` is the default starting point for day-to-day admin work.
- `/admin/servers/{server_code}` is the primary workspace for server-specific operations.
- `/admin/laws` must not be used as the primary onboarding or day-to-day configuration entrypoint for a server.
- Global ops and global users/audit should remain visually secondary to the server-centric workspace.
- `/admin/templates`, `/admin/features`, and `/admin/rules` must not return as competing top-level entrypoints.

## Operating model

Normal operator flow:

1. Open `/admin/servers`
2. Open `/admin/servers/{server_code}`
3. Work through the server-scoped tabs for laws, capabilities, templates, users, access, audit, and issues
4. Use `/admin/laws` only when raw diagnostics or compatibility-backed internals are explicitly needed

## Domain map

### Servers

- Route entry:
  - `/admin/servers`
  - `/admin/servers/{server_code}`
- Primary concerns:
  - readiness and overview
  - server laws
  - capabilities
  - document templates
  - users and access
  - audit and issues

### Ops

- Route entry: `/admin/ops`
- Compatibility redirect: `/admin/dashboard`
- Primary concerns:
  - system totals
  - performance
  - async operations
  - exam import operations
  - synthetic checks

### Audit and users

- Route entry: `/admin/audit`
- Compatibility redirect: `/admin/users`
- Primary concerns:
  - user moderation
  - role history
  - event stream
  - AI quality/cost visibility

### Laws diagnostics

- Route entry: `/admin/laws`
- Primary concerns:
  - raw law diagnostics
  - runtime detail
  - compatibility-backed law workflows
  - source-set and binding internals

## Preferred visible language

- `Servers`
  - runtime environments with their own configuration bundle and operational status
- `Law Sources and Law Sets`
  - legal source inputs, processed bundles, and bindings to servers
- `Document Templates`
  - reusable text and structure used by generated outputs
- `Capabilities`
  - runtime switches or platform capabilities visible to admins
- `Validation Rules`
  - checks that gate publishability or runtime behavior
- `Configuration Catalog`
  - the versioned inventory of admin-managed entities
- `Draft, review, publish, rollback`
  - the lifecycle of a configuration change
- `Change History`
  - who changed what and when

## Copy rules

- Prefer human-readable labels over raw entity keys.
- If an internal key must be shown, keep it in secondary text.
- Prefer `Change History` over raw `audit` when the audience is not deeply technical.
- Prefer `Law Sources and Law Sets` over plain `laws` when there is room for a clearer label.
- Avoid raw route names, workflow state ids, and database-shaped labels as primary headings.

## Boundary rules

- Keep runtime behavior unchanged when adjusting admin navigation or wording.
- Keep diagnostics and compatibility entrypoints reachable, but visually secondary.
- Prefer server-centric UX for any operator-facing addition that is server-scoped.
- Do not direct a new operator to `/admin/laws` when `/admin/servers/{server_code}` already covers the task.

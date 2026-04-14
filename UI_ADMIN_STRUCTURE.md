# UI_ADMIN_STRUCTURE.md

Status: draft  
Date: 2026-04-14  
Phase: `Phase C`

## Purpose

Define the first read-only split of the admin UI so the runtime/configuration surface is navigable by domain before editable workflows are expanded.

## Active scope

This first pass covers the catalog-oriented admin pages:

- `/admin/servers`
- `/admin/laws`
- `/admin/templates`
- `/admin/features`
- `/admin/rules`

The goal is separation by domain boundary, not a full frontend rewrite.

## Domain map

### Dashboard

- Route entry: `/admin`, `/admin/dashboard`
- Primary concerns:
  - system totals
  - performance
  - exam import operations
  - endpoint activity
  - synthetic checks

### Users and audit

- Route entry: `/admin/users`
- Primary concerns:
  - user moderation
  - role history
  - event stream
  - cost / model policy / AI pipeline visibility

### Runtime and catalog domain

- Route entry:
  - `/admin/servers`
  - `/admin/laws`
  - `/admin/templates`
  - `/admin/features`
  - `/admin/rules`
- Primary concerns:
  - runtime server inventory
  - law source and law-set bindings
  - catalog entities and versions
  - publication state
  - audit trail

## First read-only slice

The first vertical slice is the runtime and catalog domain because it is directly tied to the migration pilot `blackberry + complaint`.

### Read-only modules inside the slice

1. Domain summary
   - What this page controls
   - Which entities are in scope
   - Whether the current pass is read-only or workflow-enabled
2. Runtime inventory
   - Server list
   - Active/inactive state
   - Health snapshot
3. Catalog inventory
   - Entity list
   - Current status
   - Version history preview
4. Publication and audit context
   - Draft/published state
   - Last change metadata
   - Rollback availability

### Explicit subdomain splits inside the slice

The catalog slice is now separated in the page shell into the following read-only subdomains:

- `Servers`
  - runtime inventory
  - activation state
  - health checks
  - linked configuration boundary
- `Laws`
  - law sources
  - law sets
  - source registry
  - server bindings
- `Templates`
  - document templates
  - preview and version context
- `Features`
  - capability configuration
  - scenario impact labels
- `Rules`
  - validation rules
  - publishability and runtime gating context

These splits are represented in the page shell before any new mutation workflows are introduced.

## Boundary rules

- Keep existing route contracts and admin APIs unchanged in Phase C.
- Do not expand mutation logic while splitting read-only structure.
- Preserve existing catalog modal flows until Phase D replaces them with explicit draft/publish workflows.
- Prefer `admin_focus` domain separation over adding more conditionals inside one mega-section.

## Rendering rules for the first pass

- Each catalog-oriented page must expose:
  - a clear page-domain summary
  - visible boundary labels for runtime inventory vs catalog inventory
  - explicit migration note when a section is still backed by legacy workflow internals
- Raw internal identifiers should not be the primary visible label.
- User-facing copy should prefer domain language from `docs/ADMIN_GLOSSARY.md`.

## What Phase C does not do

- No full component-library rewrite
- No replacement of existing admin mutation handlers
- No new backend orchestration paths
- No cross-domain admin shell redesign

## Next structural step

After the read-only page shells are stable, the next step is to move from page-level domain guidance to clearer per-domain read-only section contracts and then editable workflows in Phase D.

# LAW_PLATFORM_RULES.md

## Core entities
- Law Source
- Law Source Manifest
- Law Bundle
- Law Version
- Law Set
- Server Law Binding

## Source of truth direction
- bootstrap/server_config is transitional
- published workflow-backed data is the target canonical runtime source

## Lifecycle rules

### Law Source / Manifest
`draft -> validated -> published`

### Law Bundle rebuild
`published source manifest -> fetch/parse -> preview/diff -> rebuild -> imported version`

### Law Version
`imported -> available -> active -> superseded`

Rollback returns a previous version to active state with full audit visibility.

## Workflow status vocabulary bridge

Use current workflow status vocabulary when documenting or implementing transitions:
- `draft`
- `in_review`
- `approved`
- `rejected`
- `published`
- `rolled_back`

## Scope model clarification

- `global` entities apply platform-wide and must not silently include server-specific overrides.
- `server` entities must always carry explicit server identity.
- Cross-scope transitions must be explicit and auditable.

## Invariants
- no silent replacement of active law context
- activation and rollback must be auditable
- source validation must happen before publish/rebuild
- per-server effective law state must be explainable from admin/UI
- source parsing should use connector/adapter boundaries, not one hardcoded source type

## Contract requirements
- publish/activation flows must preserve audit trail and actor attribution
- server-scoped and global law artifacts must not be mixed silently
- compatibility transitions must name source-of-truth and rollback trigger
- any law-domain API behavior change must include matching workflow/contract test coverage

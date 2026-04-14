# Feature Flag Matrix

Status: Phase B complete baseline
Date: 2026-04-14
Scope: pilot scenario `blackberry + complaint`

## Purpose
Define the migration rollout states required by `Phase B` and map them to concrete backend flags.

## Canonical rollout states

### `legacy_only`
- current route contract remains active
- pilot adapter read path is disabled
- shadow compare is disabled

### `shadow_compare`
- current route contract remains active
- pilot adapter resolves versioned runtime context in parallel
- adapter output is compared against legacy context
- drift is logged, but runtime still uses legacy path

### `new_runtime_active`
- current route contract remains active
- pilot adapter output becomes the primary runtime context source for the pilot seam
- shadow compare stays enabled during the observation window

## Flag mapping

| Rollout state | `pilot_runtime_adapter_v1` | `pilot_shadow_compare_v1` | Effective behavior |
|---|---|---|---|
| `legacy_only` | `off` | `off` | legacy context only |
| `shadow_compare` | `off` | `internal` / `beta` / `all` | compare adapter vs legacy, keep legacy active |
| `new_runtime_active` | `internal` / `beta` / `all` | `internal` / `beta` / `all` | adapter context active, drift still logged |

## Existing supporting flags

| Flag | Role during pilot |
|---|---|
| `documents_v2` | keeps case/document/version bridge active for generated outputs |
| `validation_gate_v1` | keeps validation execution visible during pilot generation |
| `citations_required` | independent policy gate for citation readiness |
| `async_jobs_v1` | independent async rollout control |

## Pilot rule

For `blackberry + complaint`, `new_runtime_active` must not be enabled until:
- `shadow_compare` has produced stable low-drift results
- route compatibility remains unchanged
- provenance-critical fields still appear in generated document snapshots

## Next extension point

When B.1 table design is finalized, these flags should switch from legacy-seeded adapter reads to DB-backed published entity reads without changing the rollout semantics above.

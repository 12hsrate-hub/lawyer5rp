# Feature Flags

## Rollout states

All domain rollout flags are evaluated **server-side** and support:

- `off` — only legacy/compatibility flow.
- `internal` — only internal cohort.
- `beta` — internal + beta cohorts.
- `all` — all eligible users.

For policy flags we also support enforcement levels:

- `off`
- `warn`
- `hard`

## Cohort resolution

Cohort resolution is done on backend using:

1. internal users/servers (staff/admin and configured sets)
2. beta users/servers
3. default users

Configuration sources (without deploy):

- `OGP_FEATURE_FLAG_<FLAG>_MODE`
- `OGP_FEATURE_FLAG_<FLAG>_ENFORCEMENT`
- `OGP_FEATURE_FLAG_<FLAG>_INTERNAL_USERS`
- `OGP_FEATURE_FLAG_<FLAG>_BETA_USERS`
- `OGP_FEATURE_FLAG_<FLAG>_INTERNAL_SERVERS`
- `OGP_FEATURE_FLAG_<FLAG>_BETA_SERVERS`
- `OGP_FEATURE_FLAGS_JSON` (central JSON override)

## Flag catalog

| Flag | Purpose | Default mode | Owner | Dependencies |
|---|---|---|---|---|
| `cases_v1` | New case lifecycle and case-aware reads/writes | `off` | backend platform | `documents_v2` for full flow |
| `documents_v2` | Versioned documents + bridge from legacy generate | `off` | backend platform | `cases_v1` |
| `citations_required` | Citation policy enforcement in generation/law QA | `off` with enforcement default `warn` | legal AI owner | retrieval/citations |
| `validation_gate_v1` | Validation/readiness gate enforcement | `off` with enforcement default `warn` | quality owner | validation rules + readiness gates |
| `async_jobs_v1` | Async entrypoints for heavy operations | `off` | platform ops | worker pools/queues |
| `pilot_runtime_adapter_v1` | Pilot adapter-backed runtime context resolution for `blackberry + complaint` | `off` | migration/backend | `pilot_shadow_compare_v1` recommended during rollout |
| `pilot_shadow_compare_v1` | Shadow-compare between legacy and adapter runtime context for the pilot scenario | `off` | migration/backend | metrics visibility |

## Regression labels

Rollout decisions and regression metrics must include labels:

- `feature_flag`
- `rollout_mode`
- `rollout_cohort`
- `server_id`
- `flow_type`
- `status`

## Release invariants

A rollout step is blocked unless:

- feature flag exists;
- all rollout modes are supported;
- regression metrics are connected;
- rollback playbook is ready;
- owner and escalation are known;
- legacy fallback path is validated.

## Rollout State Matrix

Status: Phase B complete baseline
Date: 2026-04-14
Scope: pilot scenario `blackberry + complaint`

### Purpose

Define migration rollout states and map them to concrete backend flags.

### Canonical rollout states

#### `legacy_only`

- current route contract remains active
- pilot adapter read path is disabled
- shadow compare is disabled

#### `shadow_compare`

- current route contract remains active
- pilot adapter resolves versioned runtime context in parallel
- adapter output is compared against legacy context
- drift is logged, but runtime still uses legacy path

#### `new_runtime_active`

- current route contract remains active
- pilot adapter output becomes the primary runtime context source for the pilot seam
- shadow compare stays enabled during the observation window

### Flag mapping

| Rollout state | `pilot_runtime_adapter_v1` | `pilot_shadow_compare_v1` | Effective behavior |
| --- | --- | --- | --- |
| `legacy_only` | `off` | `off` | legacy context only |
| `shadow_compare` | `off` | `internal` / `beta` / `all` | compare adapter vs legacy, keep legacy active |
| `new_runtime_active` | `internal` / `beta` / `all` | `internal` / `beta` / `all` | adapter context active, drift still logged |

### Existing supporting flags

| Flag | Role during pilot |
| --- | --- |
| `documents_v2` | keeps case/document/version bridge active for generated outputs |
| `validation_gate_v1` | keeps validation execution visible during pilot generation |
| `citations_required` | independent policy gate for citation readiness |
| `async_jobs_v1` | independent async rollout control |

### Pilot rule

For `blackberry + complaint`, `new_runtime_active` must not be enabled until:

- `shadow_compare` has produced stable low-drift results
- route compatibility remains unchanged
- provenance-critical fields still appear in generated document snapshots

### Historical note

The earlier standalone rollout matrix is preserved only in the April 2026 archive for historical reference.

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

## Phase B rollout mapping

Canonical Phase B rollout states are defined in [`FEATURE_FLAG_MATRIX.md`](./FEATURE_FLAG_MATRIX.md):

- `legacy_only`
- `shadow_compare`
- `new_runtime_active`

For the pilot scenario, these states are implemented through:
- `pilot_runtime_adapter_v1`
- `pilot_shadow_compare_v1`

# JOB_STATE_MATRIX.md

Status: Phase E baseline
Date: 2026-04-15
Scope: async/job state normalization across import/export/law rebuild/generation flows.

## Goal

Lock one canonical state model before changing runtime code or admin UI.

Canonical job states for Phase E:
- `queued`
- `running`
- `succeeded`
- `failed`
- `retry_scheduled`
- `cancelled`

## Current fragmented state models

### AsyncJobService

File: `web/ogp_web/services/async_job_service.py`

Current states:
- `pending`
- `queued`
- `processing`
- `succeeded`
- `dead_lettered`
- `cancelled`

Notes:
- `pending` is currently used for created-but-not-enqueued jobs.
- `processing` is the worker-claimed running state.
- `dead_lettered` is terminal and currently doubles as a failure-class outcome.
- failed attempts are written to `job_attempts`, while the parent job often returns to `queued`.

### ExamImportTaskRegistry

File: `web/ogp_web/services/exam_import_tasks.py`

Current states:
- `queued`
- `running`
- `completed`
- `failed`

Notes:
- `completed` is equivalent to canonical `succeeded`.
- interrupted tasks are force-marked as `failed` on startup.
- no explicit retry-scheduled state exists yet.

### Admin law rebuild tasks

Files:
- `web/ogp_web/routes/admin.py`
- `web/ogp_web/services/law_rebuild_tasks.py`

Current states:
- `queued`
- `running`
- `finished`
- `failed`

Notes:
- task lifecycle is route-local, not on the shared async job service.
- `finished` is equivalent to canonical `succeeded`.
- active-task detection only treats `queued` and `running` as non-terminal.

## Canonical normalization map

### Parent job / operator-facing state map

| Current subsystem | Current state | Canonical state |
| --- | --- | --- |
| AsyncJobService | `pending` | `queued` |
| AsyncJobService | `queued` | `queued` |
| AsyncJobService | `processing` | `running` |
| AsyncJobService | `succeeded` | `succeeded` |
| AsyncJobService | `dead_lettered` | `failed` |
| AsyncJobService | `cancelled` | `cancelled` |
| ExamImportTaskRegistry | `queued` | `queued` |
| ExamImportTaskRegistry | `running` | `running` |
| ExamImportTaskRegistry | `completed` | `succeeded` |
| ExamImportTaskRegistry | `failed` | `failed` |
| Admin law rebuild | `queued` | `queued` |
| Admin law rebuild | `running` | `running` |
| Admin law rebuild | `finished` | `succeeded` |
| Admin law rebuild | `failed` | `failed` |

### Retry semantics

- `retry_scheduled` should become a first-class operator-visible state when a failed job is automatically delayed for another attempt.
- For `AsyncJobService`, this likely means replacing the current `failed -> queued` bounce with an explicit delayed retry state on the parent job.
- For exam import and law rebuild flows, retry scheduling does not exist yet and must be added deliberately, not inferred in UI only.

## Phase E.1 findings

1. We already have one strong persistence boundary in `AsyncJobService`, but its state vocabulary is not aligned with the rest of the product.
2. Exam import and admin law rebuild still expose their own mini state machines.
3. Admin/Ops visibility cannot be coherent until these state names are normalized at least at the read-model layer.

## Next implementation slice

Completed slices:
- shared status normalizer helper for operator-facing views
- admin/ops endpoints now expose canonical status alongside raw status
- admin dashboard now exposes shared async problem jobs with first retry/cancel controls
- the same ops workspace now includes law rebuild failures and running rebuild visibility
- the same ops workspace now includes exam import pending/failed signals and failed-entry visibility

Next implementation slice:
- decide whether the remaining Phase E gap is docs/runbook hardening or one more explicit retry/idempotency matrix slice
- only after that, decide whether to migrate exam import and law rebuild onto the shared async job service

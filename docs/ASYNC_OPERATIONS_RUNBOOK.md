# Async Operations Runbook

## Scope

- Shared async jobs:
  - `document_generation`
  - `document_export`
  - `content_reindex`
  - `content_import`
- Admin law rebuild tasks:
  - `/api/admin/law-sources/rebuild-async`
- Exam import background tasks:
  - bulk scoring
  - failed rescoring
  - row scoring

Primary operator surface:
- `/admin/ops`

Compatibility route:
- `/admin/dashboard` → redirects to `/admin/ops`

Primary ops endpoints:
- `/api/admin/async-jobs/overview`
- `/api/admin/law-jobs/overview`
- `/api/admin/exam-import/overview`
- `/api/jobs/{job_id}`
- `/api/jobs/{job_id}/retry`
- `/api/jobs/{job_id}/cancel`

## What To Check First

1. Open `/admin/ops`.
2. Review three blocks in order:
   - `Async Jobs`
   - `Law rebuild tasks`
   - `Exam import`
3. Classify the issue:
   - shared async retry/failure
   - law runtime rebuild failure
   - exam import/scoring failure

## Shared Async Jobs

### Signals

- `failed`
- `retry_scheduled`
- high `problem_jobs`
- repeated failures for one `job_type`

### Immediate actions

1. If the job is transient and safe to replay, use `Retry`.
2. If the job is stuck in delayed retry and should stop requeueing, use `Cancel retry`.
3. Open `/api/jobs/{job_id}` and `/api/jobs/{job_id}/attempts` for detailed inspection when needed.

### Interpret status

- `queued`: waiting for worker claim
- `running`: worker claimed and executing
- `retry_scheduled`: automatic delayed retry is planned
- `failed`: terminal failed operator-facing state
- `cancelled`: manually stopped

### Escalate when

- the same `job_type` keeps returning to `failed`
- retries do not reduce `problem_jobs`
- multiple jobs fail with the same error code/message

## Law Rebuild Tasks

### Signals

- `failed_tasks > 0`
- non-empty failed rebuild alerts
- rebuild task remains active longer than expected

### Immediate actions

1. Check the failed alert payload in dashboard.
2. If a rebuild is still active, inspect:
   - `/api/admin/law-sources/tasks/{task_id}`
3. Re-run rebuild only after the source issue is understood:
   - invalid source URLs
   - publish/input mismatch
   - runtime law bundle generation failure

### Notes

- Law rebuild is still a route-local task model, not the shared async job service.
- Current operator action is review-first, rerun-second.

## Exam Import

### Signals

- `pending_scores > 0`
- `failed_entries > 0`
- recent import/scoring failure signals in dashboard

### Immediate actions

1. Review failed entries in the dashboard block.
2. If needed, inspect row detail:
   - `/api/exam-import/rows/{source_row}`
3. Re-run the appropriate exam import task from the exam-import surface:
   - bulk score
   - rescore failed
   - row score

### Notes

- Exam import background tasks are still on `ExamImportTaskRegistry`.
- They are visible through the unified ops surface, but not yet migrated to shared async jobs.

## Containment Guidance

### Shared async jobs

- Prefer `Cancel retry` when automatic retries are just adding noise.
- Prefer `Retry` only for transient failures.

### Law rebuild

- Avoid repeated rebuild loops until source/registry issues are understood.
- Keep server-specific scope in mind before rerunning.

### Exam import

- Prefer row-level investigation when failures are narrow.
- Prefer bulk rerun only after confirming provider/config stability.

## Evidence To Capture

- screenshot or export of the affected dashboard block
- job/task id
- canonical status and raw status
- error message / failed entry reason
- whether retry/cancel/rerun was performed
- result after intervention

## Current Limits / Gaps

- Shared async jobs have first-class retry/cancel controls.
- Law rebuild has visibility, but no unified retry/cancel control in dashboard yet.
- Exam import has visibility, but rerun actions still live on the exam-import workflow, not in dashboard.
- Idempotency is explicit for shared async jobs, but not yet unified across exam import and law rebuild.

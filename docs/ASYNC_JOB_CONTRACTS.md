# Async Job Contracts

Status: active  
Date: 2026-04-17

## Purpose

This document is the canonical contract for async job states, retry behavior, and idempotency expectations across shared jobs and still-transitional task models.

It replaces the older split between separate job-state and retry/idempotency docs.

## Canonical operator-facing states

- `queued`
- `running`
- `succeeded`
- `failed`
- `retry_scheduled`
- `cancelled`

## Current subsystem mapping

### Shared async jobs

Source:

- `web/ogp_web/services/async_job_service.py`

Mapping:

| Current state | Canonical state |
| --- | --- |
| `pending` | `queued` |
| `queued` | `queued` |
| `processing` | `running` |
| `succeeded` | `succeeded` |
| `dead_lettered` | `failed` |
| `cancelled` | `cancelled` |

### Exam import tasks

Source:

- `web/ogp_web/services/exam_import_tasks.py`

Mapping:

| Current state | Canonical state |
| --- | --- |
| `queued` | `queued` |
| `running` | `running` |
| `completed` | `succeeded` |
| `failed` | `failed` |

### Admin law rebuild tasks

Sources:

- `web/ogp_web/routes/admin.py`
- `web/ogp_web/services/law_rebuild_tasks.py`

Mapping:

| Current state | Canonical state |
| --- | --- |
| `queued` | `queued` |
| `running` | `running` |
| `finished` | `succeeded` |
| `failed` | `failed` |

## Shared async retry and idempotency policies

| Job type | Max attempts | Base delay seconds | Auto retry | Manual retry | Cancel | Idempotency |
| --- | ---: | ---: | --- | --- | --- | --- |
| `document_generation` | 3 | 10 | yes | yes | yes | yes |
| `document_export` | 3 | 10 | yes | yes | yes | yes |
| `content_reindex` | 4 | 30 | yes | yes | yes | no explicit dedup key |
| `content_import` | 4 | 30 | yes | yes | yes | yes |

## Endpoint-level idempotency

### Shared async endpoints

| Endpoint | Backing job type | Idempotency input | Current note |
| --- | --- | --- | --- |
| `/api/documents/{document_id}/generate-async` | `document_generation` | explicit `idempotency_key` or derived key | covered |
| `/api/document-versions/{version_id}/exports` | `document_export` | explicit `idempotency_key` or derived key | covered |
| `/api/admin/import` | `content_import` | explicit `idempotency_key` or derived key | covered |
| `/api/admin/reindex` | `content_reindex` | explicit `idempotency_key` or default `content_reindex:{scope}` | covered at route level |

### Transitional task models

| Flow | Backing model | Retry model | Idempotency model | Current note |
| --- | --- | --- | --- | --- |
| Law rebuild async | route-local admin task | rerun manually | none | visible in ops surface, not unified |
| Exam import bulk score | `ExamImportTaskRegistry` | rerun manually | none | capacity guard exists, dedup not unified |
| Exam import rescore failed | `ExamImportTaskRegistry` | rerun manually | none | rerun semantics depend on current failed rows |
| Exam import row score | `ExamImportTaskRegistry` | rerun manually | none | row-scoped but not idempotency-keyed |

## Retry guidance

Good retry candidates:

- transient provider or network failures
- queue or worker interruptions
- temporary overload
- temporary dependency unavailability

Bad blind-retry candidates:

- invalid input payload
- missing entity or wrong server scope
- permission failures
- stable content or source validation failures
- known bad registry or source configuration

## Operational implications

- `retry_scheduled` should remain a first-class operator-visible state instead of silently bouncing through `queued`.
- Admin/Ops surfaces should continue to expose canonical status even while some subsystems remain transitional.
- Law rebuild and exam import flows are visible through unified ops surfaces, but they are not yet implemented on the shared async abstraction.

## Next pass

1. Decide whether law rebuild should remain route-local or migrate to shared async jobs.
2. Decide whether exam import tasks should remain on `ExamImportTaskRegistry` or migrate behind the shared async abstraction.
3. If migration is deferred, keep the canonical operator-facing state layer and documented retry/idempotency behavior as the minimum compatibility contract.

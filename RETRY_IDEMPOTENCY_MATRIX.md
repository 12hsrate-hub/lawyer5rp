# Retry And Idempotency Matrix

Status: Phase E hardening baseline  
Date: 2026-04-15

## Goal

Capture the current retry/idempotency contract as implemented today, plus the remaining gaps that still need normalization.

## Shared Async Job Policies

Source:
- `web/ogp_web/services/async_job_service.py`

Current shared policies:

| Job type | Max attempts | Base delay seconds | Auto retry | Manual retry | Cancel | Idempotency |
| --- | --- | ---: | --- | --- | --- | --- |
| `document_generation` | 3 | 10 | yes | yes | yes | yes |
| `document_export` | 3 | 10 | yes | yes | yes | yes |
| `content_reindex` | 4 | 30 | yes | yes | yes | no explicit dedup key |
| `content_import` | 4 | 30 | yes | yes | yes | yes |

## Operator-Facing State Contract

Canonical states:
- `queued`
- `running`
- `succeeded`
- `failed`
- `retry_scheduled`
- `cancelled`

Current shared async mapping:
- `pending -> queued`
- `queued -> queued`
- `processing -> running`
- `succeeded -> succeeded`
- `dead_lettered -> failed`
- `cancelled -> cancelled`

## Endpoint-Level Idempotency

### Shared async endpoints

| Endpoint | Backing job type | Idempotency input | Current note |
| --- | --- | --- | --- |
| `/api/documents/{document_id}/generate-async` | `document_generation` | explicit `idempotency_key` or derived key | covered |
| `/api/document-versions/{version_id}/exports` | `document_export` | explicit `idempotency_key` or derived key | covered |
| `/api/admin/import` | `content_import` | explicit `idempotency_key` or derived key | covered |
| `/api/admin/reindex` | `content_reindex` | explicit `idempotency_key` or default `content_reindex:{scope}` | covered at route level |

### Non-shared task models

| Flow | Backing model | Retry model | Idempotency model | Current note |
| --- | --- | --- | --- | --- |
| Law rebuild async | route-local admin task | rerun manually | none | visible in ops surface, not unified |
| Exam import bulk score | `ExamImportTaskRegistry` | rerun manually | none | capacity guard exists, dedup not unified |
| Exam import rescore failed | `ExamImportTaskRegistry` | rerun manually | none | rerun semantics depend on current failed rows |
| Exam import row score | `ExamImportTaskRegistry` | rerun manually | none | row-scoped but not idempotency-keyed |

## Failure-Class Guidance

### Good candidates for retry

- transient provider/network failures
- queue/worker interruptions
- temporary overload
- temporary dependency unavailability

### Bad candidates for blind retry

- invalid input payload
- missing entity / wrong server scope
- permission failures
- stable content/source validation failures
- known bad registry/source configuration

## Current Gaps

1. Law rebuild tasks are visible in admin ops, but still not on the shared async job service.
2. Exam import tasks are visible in admin ops, but still not on the shared async job service.
3. Non-retryable failure classes are not yet enforced as typed policy in code; they are only documented operationally.

## Recommended Next Pass

1. Decide whether law rebuild should stay route-local or move onto shared async jobs.
2. Decide whether exam import tasks should stay on `ExamImportTaskRegistry` or migrate behind the shared async abstraction.
3. If migration is deferred, keep the operator-facing canonical state layer as the minimum compatibility contract.

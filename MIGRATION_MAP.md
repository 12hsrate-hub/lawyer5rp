# MIGRATION_MAP.md — Baseline route/service/storage map (Phase A start)

Status: initial baseline  
Date: 2026-04-14

## Critical user/admin journeys

1. Authentication: `/login` + profile/session management.
2. Complaint/case flow: complaint creation, validation, document build.
3. Admin review and configuration operations.
4. Exam import processing.
5. Exports/attachments lifecycle.

## Route surface (web/ogp_web/routes)

- `auth.py`
- `profile.py`
- `complaint.py`
- `cases.py`
- `validation.py`
- `document_builder.py`
- `exam_import.py`
- `jobs.py`
- `exports.py`
- `attachments.py`
- `admin.py`
- `pages.py`

## Service surface (web/ogp_web/services)

### Core user/runtime
- `auth_service.py`
- `profile_service.py`
- `complaint_service.py`
- `case_service.py`
- `validation_service.py`
- `document_service.py`
- `generation_orchestrator.py`
- `legal_pipeline_service.py`

### Admin/config/law
- `admin_dashboard_service.py`
- `law_admin_service.py`
- `law_bundle_service.py`
- `law_version_service.py`
- `content_workflow_service.py`
- `content_contracts.py`
- `feature_flags.py`

### Async/jobs/import/export
- `async_job_service.py`
- `exam_import_service.py`
- `exam_import_tasks.py`
- `law_rebuild_tasks.py`
- `export_service.py`
- `attachment_service.py`

### AI/retrieval/citations
- `ai_service.py`
- `point3_pipeline.py`
- `point3_policy_service.py`
- `retrieval_service.py`
- `law_retrieval_service.py`
- `citation_service.py`

## Data/infrastructure anchors

- DB config + backend abstraction: `web/ogp_web/db/config.py`, `web/ogp_web/db/factory.py`
- Migrations: `web/ogp_web/db/migrations/*`
- Storage adapters: `web/ogp_web/storage/*`
- Worker/runtime infra: `web/ogp_web/workers/*`, `web/ogp_web/providers/*`
- Server-aware config baseline: `web/ogp_web/server_config/*`

## Primary migration seams (initial)

1. **Legacy route compatibility seam**: keep route contracts stable; move internals behind adapters.
2. **Scenario feature-flag seam**: `legacy_only` / `shadow_compare` / `new_runtime_active`.
3. **Config-as-data seam**: server/procedure/form/rule/template/law-set versions in DB.
4. **Async reliability seam**: explicit job states + idempotency + retry policy.
5. **Provenance seam**: generation outputs must persist legal/context trace metadata.

## Immediate next actions (Phase A.1 → A.2)

1. Build per-route call graph (route -> service -> store) for:
   - login
   - complaint
   - admin
   - exam import
2. Mark hardcoded server-condition branches and classify by risk.
3. Select reference pilot:
   - one server
   - one procedure
4. Freeze pilot acceptance KPIs and fallback criteria.


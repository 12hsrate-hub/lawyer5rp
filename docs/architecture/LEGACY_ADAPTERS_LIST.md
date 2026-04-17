# LEGACY_ADAPTERS_LIST.md

Status: Phase A baseline complete
Date: 2026-04-14

## Purpose
List where legacy compatibility must be preserved while the new config-driven runtime is introduced behind adapters.

## Adapter-critical surfaces

### 1. Auth/profile route compatibility
- Files:
  - `web/ogp_web/routes/auth.py`
  - `web/ogp_web/routes/profile.py`
  - `web/ogp_web/services/auth_service.py`
  - `web/ogp_web/services/profile_service.py`
- Why preserve:
  - session cookies, login flows, selected-server persistence, and user profile shape are user-facing contracts
- Adapter direction:
  - keep current endpoints and response shapes
  - move future server/procedure resolution behind services rather than route changes

### 2. Complaint generation request/response contract
- Files:
  - `web/ogp_web/routes/complaint.py`
  - `web/ogp_web/services/complaint_service.py`
  - `web/ogp_web/services/generation_orchestrator.py`
- Why preserve:
  - this is the reference pilot runtime journey
  - generation, validation, citations, and persistence already fan out behind the route
- Adapter direction:
  - keep `/api/complaint-draft`, `/api/generate`, and validation/citation reads stable
  - place new runtime resolution behind orchestration/service boundaries

### 3. Admin catalog and publication workflow routes
- Files:
  - `web/ogp_web/routes/admin.py`
  - `web/ogp_web/services/content_workflow_service.py`
  - `web/ogp_web/services/law_admin_service.py`
  - `web/ogp_web/storage/admin_catalog_store.py`
- Why preserve:
  - current admin UI expects these route shapes
  - legacy catalog state and new workflow-backed state may coexist temporarily
- Adapter direction:
  - make legacy store adapter-only where needed
  - new source of truth should converge on workflow-backed persisted entities

### 4. Server config resolution boundary
- Files:
  - `web/ogp_web/server_config/registry.py`
  - `web/ogp_web/server_config/blackberry.py`
  - `web/ogp_web/storage/user_store.py`
  - `web/ogp_web/routes/pages.py`
- Why preserve:
  - current runtime uses this as the canonical server-aware baseline
- Adapter direction:
  - introduce DB/versioned config reads behind this resolution layer first
  - avoid direct route-level knowledge of new config persistence details

### 5. Async jobs, exports, and attachments
- Files:
  - `web/ogp_web/routes/jobs.py`
  - `web/ogp_web/routes/exports.py`
  - `web/ogp_web/routes/attachments.py`
  - `web/ogp_web/services/async_job_service.py`
  - `web/ogp_web/services/export_service.py`
  - `web/ogp_web/services/attachment_service.py`
- Why preserve:
  - these already resemble the target architecture and should not be destabilized during pilot runtime work
- Adapter direction:
  - treat existing repositories and async state model as stable boundaries
  - migrate visibility and policy first, not core contracts

### 6. Exam import processing
- Files:
  - `web/ogp_web/routes/exam_import.py`
  - `web/ogp_web/services/exam_import_service.py`
  - `web/ogp_web/services/exam_import_tasks.py`
- Why preserve:
  - async scoring and retries are operationally sensitive and not ideal as an early migration pilot
- Adapter direction:
  - isolate from early config-runtime changes
  - revisit during async stabilization phase

## Practical rule for future sessions
If a Phase B or Phase C task touches one of the surfaces above:
- preserve the current endpoint or page contract unless the plan explicitly says otherwise
- prefer adapters, service indirection, and feature flags over replacing the route contract directly

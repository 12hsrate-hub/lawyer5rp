# Legacy Compatibility

Status: active  
Date: 2026-04-17

## Purpose

This document is the canonical reference for:

- which legacy and compatibility surfaces must still be preserved
- which transitional seams may become removable later
- what removal preconditions must be met before cleanup

It replaces the older split between separate compatibility-preservation and deprecation-candidate docs.

## Preserve These Compatibility Boundaries

### Auth and profile route compatibility

- Files:
  - `web/ogp_web/routes/auth.py`
  - `web/ogp_web/routes/profile.py`
  - `web/ogp_web/services/auth_service.py`
  - `web/ogp_web/services/profile_service.py`
- Why preserve:
  - session cookies, login flows, selected-server persistence, and user profile shape are user-facing contracts
- Direction:
  - keep current endpoints and response shapes
  - move future server and procedure resolution behind services rather than route changes

### Complaint generation request and response contract

- Files:
  - `web/ogp_web/routes/complaint.py`
  - `web/ogp_web/services/complaint_service.py`
  - `web/ogp_web/services/generation_orchestrator.py`
- Why preserve:
  - this remains the reference pilot runtime journey
- Direction:
  - keep `/api/complaint-draft`, `/api/generate`, and validation/citation reads stable
  - place new runtime resolution behind orchestration and service boundaries

### Admin catalog and publication workflow routes

- Files:
  - `web/ogp_web/routes/admin.py`
  - `web/ogp_web/services/content_workflow_service.py`
  - `web/ogp_web/services/law_admin_service.py`
  - `web/ogp_web/storage/admin_catalog_store.py`
- Why preserve:
  - the admin UI still expects these route shapes during transition
- Direction:
  - keep legacy store behavior adapter-only where needed
  - converge the source of truth on workflow-backed persisted entities

### Server config resolution boundary

- Files:
  - `web/ogp_web/server_config/registry.py`
  - `web/ogp_web/server_config/blackberry.py`
  - `web/ogp_web/storage/user_store.py`
  - `web/ogp_web/routes/pages.py`
- Why preserve:
  - current runtime uses this as the canonical server-aware baseline
- Direction:
  - introduce DB and versioned config reads behind this resolution layer first
  - avoid direct route-level knowledge of new config persistence details

### Async jobs, exports, and attachments

- Files:
  - `web/ogp_web/routes/jobs.py`
  - `web/ogp_web/routes/exports.py`
  - `web/ogp_web/routes/attachments.py`
  - `web/ogp_web/services/async_job_service.py`
  - `web/ogp_web/services/export_service.py`
  - `web/ogp_web/services/attachment_service.py`
- Why preserve:
  - these are already close to the target architecture and should not be destabilized during pilot runtime work
- Direction:
  - migrate visibility and policy first, not the core contract

### Exam import processing

- Files:
  - `web/ogp_web/routes/exam_import.py`
  - `web/ogp_web/services/exam_import_service.py`
  - `web/ogp_web/services/exam_import_tasks.py`
- Why preserve:
  - async scoring and retries are operationally sensitive and should not be an early migration casualty
- Direction:
  - isolate from early config-runtime changes
  - revisit during async stabilization work

## Removal Candidates

### Legacy-only rollout assumptions in admin copy

- Area: dashboard/admin rollout messaging
- Why it may be removable:
  - some wording is intentionally cautious for observation mode and can be simplified after stable activation

### Already removed during previous cleanup passes

- legacy provenance/raw-ref presentation workarounds
- shadow-compare-only metrics plumbing
- pilot adapter fallback-only visibility paths

These are kept here as historical cleanup markers rather than active work items.

## Removal Rule

Do not remove a compatibility candidate until:

- the relevant observation window is accepted
- rollback remains documented
- provenance and async visibility remain equivalent or better after cleanup

## Review Rule

If a task touches one of the preserved compatibility surfaces above:

- preserve the current endpoint or page contract unless the plan explicitly says otherwise
- prefer adapters, service indirection, and feature flags over route-contract replacement

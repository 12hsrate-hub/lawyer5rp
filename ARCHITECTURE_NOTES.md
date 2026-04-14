# ARCHITECTURE_NOTES.md

Status: Phase A baseline complete
Date: 2026-04-14

## Purpose
Capture the repo-aware architecture conclusions from Phase A so Phase B can start without redoing inventory.

## Current architecture shape

### 1. Runtime is a modular monolith with uneven maturity
- App composition remains centralized in `web/ogp_web/app.py`.
- Route surfaces are still broad and legacy-compatible.
- Several services and repositories already form useful domain boundaries.

### 2. Strongest existing boundaries
- Auth/profile persistence around `UserStore`
- Case/document/version persistence around `CaseRepository` and `DocumentRepository`
- Content workflow persistence around `ContentWorkflowRepository`
- Artifact persistence around `ArtifactRepository`
- Async job state machine around `AsyncJobService`

### 3. Largest monolithic hotspots
- `web/ogp_web/routes/admin.py`
- `web/ogp_web/routes/complaint.py`
- parts of `web/ogp_web/services/ai_service.py`

These remain primary coupling zones where route handlers still coordinate too many concerns directly.

## Architectural conclusions for next phase

### A. Keep route contracts stable
Do not start Phase B by changing public endpoint contracts.
The safer path is adapter-first migration:
- route remains stable
- new runtime/config resolution moves behind services/adapters
- drift gets measured before active cutover

### B. Treat `blackberry` bootstrap as seed data, not target architecture
Current repo state still treats `blackberry` as the effective default server across bootstrap config, migrations, and some runtime defaults.
That is acceptable as the first pilot baseline, but it must not remain the implicit pattern for future servers.

### C. Promote repositories and workflow services as future source-of-truth boundaries
The following are the best anchors for Phase B:
- `ContentWorkflowRepository` for versioned admin-managed entities
- `CaseRepository` / `DocumentRepository` for durable generated runtime artifacts
- `ArtifactRepository` for exports/attachments
- `AsyncJobService` for retryable background execution

### D. Split admin by domain, not by one giant page
The code already hints at bounded domains:
- runtime servers
- law sets
- law sources
- content workflow/catalog
- dashboard/quality/performance
- user moderation
- synthetic checks

Phase C should expose these as separate admin modules rather than expanding the current mega-surface.

### E. Async stabilization is not optional side work
Exam import, exports, jobs, admin rebuild tasks, and AI retries are already first-class operational concerns.
Phase E should be treated as product-critical stabilization, not cleanup.

### F. Provenance already has a natural landing zone
The runtime can carry provenance through:
- generation context snapshots
- validation records
- citation rows
- document versions
- admin audit/review surfaces

Phase B and later phases should standardize these fields instead of creating a parallel audit model later.

## Recommended first implementation direction after Phase A

1. Draft versioned config model families around the pilot scenario only.
2. Add read-path adapters for the `blackberry` + `complaint` scenario.
3. Keep legacy route contracts.
4. Introduce shadow-compare logging before any active runtime switch.
5. Avoid expanding `admin.py` or `complaint.py` with new pilot-specific branching.

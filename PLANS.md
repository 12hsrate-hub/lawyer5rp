# PLANS.md — Migration Plan for Multi-Server Legal Platform (Staged, Repo-Aware)

Status: draft v1 (execution-ready baseline)
Date: 2026-04-14
Scope: staged migration inside current modular monolith (`web/ogp_web` + `shared`) without full rewrite.

## Current Execution State

- Current phase: `Phase I — Runtime/admin convergence wave 1`
- Current task: `Phase I.4 admin analytics convergence wave 1`
- Active execution phase override: `Phase H is accepted; Phase I is now opened as the next execution phase`
- Current micro-step: `I.4d ai-pipeline analytics convergence review after accepted dashboard/overview/performance block`
- Overall status: `in_progress`
- Last updated: `2026-04-15`
- Execution override update:
  - `Phase G` is accepted.
  - `Phase A` through `Phase G` are now complete.
  - The pilot rollout workspace, provenance review, and post-pilot cleanup backlog are live.
  - Next work should start from `Phase H.1`, not by reopening earlier phases.
  - `H.1b` runtime catalog verification has now been executed on production for `blackberry + rehab`.
  - `H.1c` is now complete: rehab template binding, published validation rule, and pack validation profile are aligned in production.
  - Production verifier now returns `PASS` for rehab catalog coverage.
  - `H.1d` is now complete: rehab remains on the bounded transitional runtime path, and admin review/provenance parity is covered by runtime code plus API tests.
  - `Phase H.1` is accepted as the first post-pilot bounded candidate checkpoint.
  - `H.2` wave 1 has started with two accepted cleanup slices already deployed on production.
  - review-context refs are now normalized on the server side and the client-side legacy raw-ref compaction path has been removed.
  - pilot adapter fallback-only `source_of_truth` visibility metadata has been removed without changing adapter behavior.
  - shadow-compare-only telemetry plumbing has now been removed from complaint generation and pilot adapter support code.
  - compare-only pilot drift helper scripts have been removed and archived as historical observation tooling.
  - pilot adapter runtime snapshots no longer expose fallback-only `seeded/published` visibility markers or `content_item_id` noise.
  - the rollout workspace is now renamed away from pilot/preflight-only wording where the underlying state machine already stays the same.
  - `Phase H.2 wave 1` is accepted as complete.
  - `H.3a` through `H.3l` are accepted on production.
  - `H.3` is accepted: no further meaningful complaint-path transitional seams remain that can be removed as small safe slices without inventing artificial refactors.
  - `Phase H` is accepted as complete.
  - `Phase I` is opened as the next execution phase.
  - `I.1a` is now complete on production commit `1b071bd`: shared user server-context resolution is extracted and reused by `pages.py` plus bounded `admin.py` paths.
  - `I.1b` is now complete on production commit `436fba9`: the same shared user server-context helper now also covers user-bound `complaint.py` and `profile.py` server-config reads.
  - `I.1c` is now complete on production commit `d740b24`: public/default server-config reads in `pages.py` now reuse a shared resolver for login, verify-email, and reset-password surfaces.
  - `I.1d` is now complete on production commit `bc161e1`: `law_admin_service.py` now reuses shared server-config resolution across effective, sync, and rebuild paths.
  - `I.1e` is now complete on production commit `a562afc`: `complaint_service.build_generation_context_snapshot(...)` now reuses shared server-config resolution.
  - `I.1f` is now complete on production commit `a562afc`: bounded `ai_service` suggest/law helper paths now reuse shared server-config resolution instead of direct service-level reads.
  - `I.1g` is now complete on production commit `3ae4349`: shared law-context helper functions now centralize `law_qa_bundle_path` and normalized `law_qa_sources` reads across bounded service paths.
  - `I.1h` is now complete on production commit `bd4e104`: `law_retrieval_service.py` now reuses shared extracted law-context settings instead of local per-field server-config shaping.
  - `I.1i` is now complete on production commit `ef329f4`: `law_qa_test` page rendering now reuses shared law-context helpers instead of direct `server_config.law_qa_*` reads.
  - `I.1j` is now complete on production commit `6ca518f`: `ai_service` now reuses shared extracted AI-context settings for law-QA/suggest shadow profiles and suggest-mode policy shaping.
  - `I.1k` is now complete on production commit `7026994`: shared server identity extraction now backs `law_retrieval_service` result shaping and complaint generation snapshot server metadata.
  - `I.1l` is now complete on production commit `7026994`: shared normalized feature-flag extraction now backs complaint snapshot feature flags and `ai_service` feature checks.
  - `I.1m` is now complete on production commit `078350d`: shared page/admin shell context extraction now backs `pages.py` and `admin.py` instead of local server-config presentation shaping.
  - `I.1n` is now complete on production commit `4b64c12`: shared complaint/page server settings now back complaint payload validation plus complaint-test and exam-import page rendering.
  - `I.1o` is now complete on production commit `ff9be09`: shared user-permissions resolution now backs admin cross-server law-sources permission checks, and the `complaint_test_page` settings regression is fixed in production.
  - `I.1p` is now complete on production commit `9c83be7`: shared user-server config resolution now backs `profile.py` selected-server switching and complaint route config reads.
  - `I.1q` is now complete on production commit `9c83be7`: shared law-QA server availability/identity helpers now back `pages.py` and law-sources dependency reporting.
  - `I.1r` is now complete on production commit `adb09aa`: `law_qa_test_page` now reuses shared server identity for source loading instead of repeated direct `server_config.code` reads.
  - `I.1s` is now complete on production commit `adb09aa`: law-sources dependency reporting no longer re-resolves server identity after the shared law-QA availability helper already supplied it.
  - `I.1t` is now complete on production commit `adb09aa`: dead `resolve_server_config(...)` reads were removed from bounded law-QA admin/AI helper paths without changing runtime contracts.
  - `I.1u` is now complete on production commit `8395223`: repeated request-default server-config lookup in `pages.py` is centralized behind `_request_server_config(...)` for login, verify-email, and reset-password flows.
  - `I.1v` is now complete on production commit `8395223`: tiny dead cleanup leftovers were removed from bounded page/law-admin paths, and stale `law_admin_service` tests were aligned with the shared server-context helpers.
  - `I.1w` is now complete on production commit `304d9d6`: shared `resolve_server_ai_context_settings(...)` now backs bounded AI law-QA and suggest call sites instead of local extract-only seams.
  - `I.1x` is now complete on production commit `304d9d6`: shared `resolve_server_identity(...)` and `resolve_server_feature_flags(...)` now back bounded complaint generation snapshot assembly and related server-context tests.
  - `I.1y` is now complete on production commit `c7be298`: shared user-level resolvers now back complaint route identity/settings checks and remove the last local `_server_config_for_user(...)` wrapper.
  - `I.1z` is now complete on production commit `c7be298`: verify-email page server selection now reuses a single page-level resolver for request-default and username-bound rendering paths.
  - `I.1` is accepted: no further meaningful runtime/admin shared server-context seams remain that can be removed as small safe slices without inventing artificial helper layers.
  - `I.2a` is now complete on production commit `6844864`: shared generation snapshot schema helpers now back admin review-context summary/linkage shaping and provenance extraction without changing route payloads.
  - `I.2b` is now complete on production commit `81faa7b`: shared generation-context schema blocks now back legacy complaint snapshots and pilot adapter snapshots for server/effective-config/content-workflow assembly.
  - `I.2c` is now complete on production commit `81faa7b`: `generation_orchestrator` now reuses the shared persistence-block extractor for `effective_config_snapshot` and `content_workflow` instead of inline schema checks.
  - `I.2d` is now complete on production commit `81faa7b`: shared provenance lookup by `generation_snapshot_id` now backs generated-document snapshot and admin provenance bridge paths.
  - `I.2e` is now complete on production commit `33533e0`: generated-document trace bundle resolution is now centralized behind a shared helper reused by user snapshot, admin provenance, and admin review-context paths.
  - `I.2f` is now complete on production commit `33533e0`: shared generated-document provenance and review-context builders now own the remaining route-local payload assembly for complaint/admin generated-document trace surfaces.
  - `I.2g` is now complete on production commit `15def5a`: user generated-document snapshot and history reads now resolve through shared store/service helpers instead of the read-only `GenerationOrchestrator` bridge path.
  - `I.2h` is now complete on production commit `15def5a`: generation-snapshot row decoding is now centralized inside `UserStore` for user/admin generated-document snapshot readers.
  - `I.2i` is now complete on production commit `15def5a`: dead read-only generated-document snapshot/history methods were removed from `GenerationOrchestrator` after the store-backed read path took ownership.
  - `I.2j` is now complete on production commit `ed75805`: `ProvenanceService` now builds traces directly from a provided `document_version` row, so generation-snapshot provenance no longer re-fetches the same document version.
  - `I.2k` is now complete on production commit `ed75805`: the store-backed provenance service factory is now centralized in `provenance_service` instead of being redefined in generated-document helper code.
  - `I.2l` is now complete on production commit `ed75805`: complaint/admin generated-document provenance routes now reuse bundle-based provenance resolution instead of passing split `generation_snapshot_id/version_row` args.
  - `I.2m` is now complete on production commit `ff6884f`: generated-document review-context supporting data now resolves through a shared helper instead of route-local service wiring inside the payload builder.
  - `I.2n` is now complete on production commit `ff6884f`: bbcode preview truncation is now centralized in a dedicated generated-document helper instead of inline review-context formatting.
  - `I.2o` is now complete on production commit `ff6884f`: admin generated-document review-context now uses a bundle-based wrapper helper for naming parity with the provenance path.
  - `I.2p` is now complete on production commit `c1fdaa9`: shared admin/user generated-document bundle require helpers now own route-appropriate 404 handling instead of route-local bundle guards.
  - `I.2q` is now complete on production commit `c1fdaa9`: the user generated-document snapshot route now uses a shared snapshot payload wrapper instead of inline `snapshot + provenance` response assembly.
  - `I.2r` is now complete on production commit `c1fdaa9`: complaint/admin generated-document routes now follow one consistent bundle-guard/wrapper pattern across snapshot, provenance, and review-context surfaces.
  - `I.2s` is now complete on production commit `d8dd0d8`: document-version provenance server-access and payload resolution now converge behind a shared `provenance_service` helper instead of route-local target checks plus route-local service wiring.
  - `I.2t` is now complete on production commit `d8dd0d8`: `GeneratedDocumentTraceBundle` now exposes normalized generated-document/server/version metadata accessors, and review/support builders consume those bundle-backed fields instead of re-decoding raw snapshot/version rows inline.
  - `I.2u` is now complete on production commit `d8dd0d8`: generated-document snapshot payload assembly now converges behind a shared builder reused by the bundle-backed snapshot wrapper instead of keeping the merge shape inline.
  - `I.2v` is now complete on production commit `62c2d5d`: generated-document list item normalization now converges behind shared helpers instead of route-local timestamp and field shaping.
  - `I.2w` is now complete on production commit `62c2d5d`: the user generated-document history route now reads through a shared generated-document list helper instead of a route-local normalizer layered over raw store output.
  - `I.2x` is now complete on production commit `62c2d5d`: the admin recent generated-documents route now reuses the same shared generated-document list helper layer with normalized `generation_snapshot_id` and `username` shaping.
  - `I.2` is accepted: no further meaningful snapshot/provenance convergence seams remain that remove real duplicated logic without drifting into wrapper-only reshuffling.
  - `I.3a` is now complete on production commit `2b70af8`: `exam_import` overview payload assembly is now centralized behind a shared admin overview helper reused by both the standalone `/api/admin/exam-import/overview` route and the main admin dashboard assembly.
  - `I.3b` is now complete on production commit `e83b789`: `law-jobs` overview payload assembly is now centralized behind a shared admin overview helper instead of remaining route-local inside `routes/admin.py`.
  - `I.3c` is now complete on production commit `e83b789`: `async-jobs` overview payload assembly is now centralized behind the same shared admin overview helper layer instead of route-local status bucketing and grouping logic.
  - `I.3d` is now complete on production commit `1c532df`: runtime-server CRUD payload assembly now converges behind a dedicated admin runtime-server helper layer instead of staying route-local across list/create/update/activate/deactivate endpoints.
  - `I.3e` is now complete on production commit `1c532df`: runtime-server health payload assembly now converges behind the same admin runtime-server helper layer instead of route-local dependency orchestration inside `routes/admin.py`.
  - `I.3f` is now complete on production commit `dcd6adc`: runtime-server law-sets and law-bindings payload assembly now converges behind a shared admin law-management helper layer instead of staying route-local in `routes/admin.py`.
  - `I.3g` is now complete on production commit `dcd6adc`: law-set rebuild and rollback context resolution now converges behind the same helper layer instead of route-local store orchestration.
  - `I.3h` is now complete on production commit `dcd6adc`: law-source registry payload assembly now converges behind the same admin law-management helper layer instead of route-local shaping in `routes/admin.py`.
  - `I.3i` is now complete on production commit `5035570`: law-sources status, sync, rebuild, save, preview, history, and dependency payload orchestration now converges behind a shared admin law-sources helper layer instead of route-local `LawAdminService` wiring in `routes/admin.py`.
  - `I.3j` is now complete on production commit `5035570`: permission-aware target server resolution for law-sources operations now converges behind the same helper layer instead of route-local cross-server permission checks.
  - `I.3k` is now complete on production commit `5035570`: law-sources task-status guarding and canonical payload shaping now converge behind the same helper layer instead of route-local task validation in `routes/admin.py`.
  - `I.3l` is now complete on production commit `d660d7f`: catalog audit/list/get/versions payload assembly now converges behind a shared admin catalog helper layer instead of route-local workflow-service orchestration in `routes/admin.py`.
  - `I.3m` is now complete on production commit `d660d7f`: catalog workflow action dispatch and change-request review/validate payload shaping now converge behind the same helper layer instead of route-local action branching.
  - `I.3n` is now complete on production commit `d660d7f`: catalog item create/update/rollback payload configuration and active change-request resolution now converge behind the same helper layer instead of route-local config shaping in `routes/admin.py`.
  - `I.3o` is now complete on production commit `2bed351`: admin users list payload assembly now converges behind a shared admin users helper layer instead of route-local metrics/user overview shaping in `routes/admin.py`.
  - `I.3p` is now complete on production commit `2bed351`: admin user details payload assembly now converges behind the same helper layer instead of route-local permission snapshot and activity summary shaping.
  - `I.3q` is now complete on production commit `2bed351`: role-history and users.csv reporting now converge behind the same helper layer instead of route-local overview/export wiring.
  - `I.3r` is now complete on production commit `024c3e2`: user verify/block/unblock mutation payload assembly now converges behind a shared admin user-mutations helper layer instead of route-local store-call wiring in `routes/admin.py`.
  - `I.3s` is now complete on production commit `024c3e2`: tester/gka role toggles and email/password update payload assembly now converge behind the same helper layer instead of route-local per-endpoint mutation shaping.
  - `I.3t` is now complete on production commit `024c3e2`: deactivate/reactivate and daily-quota payload assembly now converge behind the same helper layer instead of route-local write-path handling.
  - `I.3u` is now complete on production commit `f9d34a8`: bulk user-mutation dispatch now converges behind the same shared admin user-mutations helper layer instead of route-local action branching and duplicated metrics meta in `routes/admin.py`.
  - `I.3` is accepted: the remaining admin endpoints are now mostly task boundaries or larger analytics contracts rather than another high-value route decomposition seam inside the old admin decomposition wave.
  - `I.4a` is now complete on production commit `c9ad609`: `/api/admin/dashboard` KPI, alerts, quick-links, and recent-event aggregation now converge behind a shared admin analytics service instead of route-local assembly in `routes/admin.py`.
  - `I.4b` is now complete on production commit `c9ad609`: `/api/admin/overview` metrics, model-policy, error-explorer, synthetic summary, and partial-error orchestration now converge behind the same shared analytics service instead of route-local glue.
  - `I.4c` is now complete on production commit `c9ad609`: `/api/admin/performance` caching, latency/rates/totals shaping, and snapshot metadata now converge behind the same shared analytics service instead of route-local cache and formatting helpers.
  - immediate next step is `I.4d ai-pipeline analytics convergence review after accepted dashboard/overview/performance block`.
- Notes:
  - `PLANS.md` is the single canonical execution plan.
  - Progress must be recorded here after each completed micro-task.
  - `MIGRATION_MAP.md` should track confirmed inventory slices and migration seams as they are verified.
  - Completed slices: `5/5 initial critical journeys`
  - Reference pilot fixed: `blackberry` + `complaint`

## 0) Goals and boundaries

### Business goal
Build a multi-server legal platform where non-technical admins configure server-specific behavior via visual admin UI, while runtime stays stable for current users.

### Hard constraints
- No big-bang rewrite.
- No new scattered server-specific `if/else` logic in runtime routes/services.
- Preserve current production behavior during migration via adapters and feature flags.
- New model must support draft/publish/rollback/audit/versioning for key admin-managed entities.

### Current architecture anchors in repo
- Runtime entry and app composition: `web/ogp_web/app.py`.
- Legacy route surface: `web/ogp_web/routes/*.py` (auth/profile/complaint/cases/validation/exam_import/jobs/document_builder/attachments/exports/admin/pages).
- Current service layer: `web/ogp_web/services/*.py` including legal + generation + async + retrieval concerns.
- Data/runtime infra: `web/ogp_web/db/*`, `web/ogp_web/storage/*`, `web/ogp_web/workers/*`, `web/ogp_web/providers/*`.
- Server-aware baseline: `web/ogp_web/server_config/*`.

---

## 1) Target architecture (controlled rebuild inside modular monolith)

### 1.1 Platform Core (shared runtime machine)
Common, reusable engine layers:
- workflow engine
- form processing
- validation framework
- generation pipeline
- document lifecycle
- export pipeline
- permissions/audit/publication pipeline

### 1.2 Server configuration as data (not hardcoded code branches)
Server-specific content moved to versioned configuration models:
- process types
- BB catalogs
- forms
- validation rules
- templates
- law sets
- terminology/capabilities

### 1.3 Visual Admin first-class surface
Bounded modules (not mega-page):
- Servers
- Process Types
- BB Codes
- Forms
- Validation Rules
- Document Templates
- Law Sets
- Publications
- Audit
- Users & Permissions

### 1.4 Publication model for all critical entities
Every configurable entity: draft -> validate -> publish -> rollback (+ full audit timeline).

### 1.5 Infrastructure direction (incremental)
- PostgreSQL as source of truth.
- Redis for queue/cache/quota/temp state.
- S3-compatible storage for files/exports.
- Worker queue for async jobs.
- AI via adapter/gateway with provenance persistence.

---

## 2) Execution phases (with dependencies, acceptance, rollback)

## Phase A — Baseline inventory + migration map (1 sprint)

Execution status: `done`

### A.1 Codebase inventory
Status: `done`
- Map route -> service -> storage dependencies for all critical flows (`/login`, `/complaint`, `/admin`, `/exam_import`, document build/export).
- Mark hardcoded server-dependent paths.
- Mark async operations and retry/error handling locations.

### A.2 Define "reference pilot"
Status: `done`
- Choose 1 reference server and 1 reference procedure as first migration scenario.
- Fix canonical old-vs-new behavior checklist for this scenario.

### Deliverables
- `MIGRATION_MAP.md`
- `ARCHITECTURE_NOTES.md`
- "legacy adapters list" (where compatibility must stay)

### Acceptance
- Full route/service map for critical user/admin journeys approved.
- Pilot scenario and cutover KPIs fixed.

### Rollback/containment
- No runtime switch yet; documentation-only phase.

Dependencies: none.

---

## Phase B — Runtime model foundation + single source-of-truth contract (1-2 sprints)

Execution status: `done`

### B.1 Data model draft and persistence skeleton
Status: `done`
Introduce versioned DB model families (minimal first):
- server_config_version
- procedure_version
- form_version
- validation_rule_version
- template_version
- law_set_version
- publication/audit events

### B.2 Read-path adapters
Status: `done`
- Keep legacy endpoints.
- Add adapter layer that can resolve config from new model behind feature flags.
- Default remains legacy for all non-pilot scenarios.
- Initial implementation slice complete for `blackberry + complaint` via `pilot_runtime_adapter.py` and `pilot_runtime_adapter_v1`.

### B.3 Drift detection
Status: `done`
- Add shadow compare for pilot scenario: legacy output vs new-runtime-derived output.
- Persist mismatch logs with reason category.
- Initial implementation slice completed during pilot observation; compare-only metrics plumbing was later retired during `Phase H.2`.

### Deliverables
- `DATA_MODEL_DRAFT.md`
- feature flags matrix (`legacy_only`, `shadow_compare`, `new_runtime_active`)
- historical drift-report instrumentation for the pilot observation window
- Implemented pilot adapter seam with workflow-backed published reads + legacy fallback for `blackberry + complaint`

### Acceptance
- Pilot scenario can run in `shadow_compare` mode with measurable drift report.
- No regression in current production route contracts.

### Rollback/containment
- One-flag instant revert to `legacy_only` per scenario.

Dependencies: Phase A.

---

## Phase C — Visual Admin read-only modules (1 sprint)

### C.1 Read-only domain slices
Status: `done`
Build separate admin views (read-only first):
- Servers
- Procedures
- Forms
- Rules
- Templates
- Law sets
- Publications/Audit

### C.2 UX language baseline
Status: `done`
- Human-readable naming dictionary (user/admin-facing).
- Ban raw internal identifiers in visible labels by default.

### Deliverables
- `UI_ADMIN_STRUCTURE.md`
- read-only pages for pilot domain entities
- initial glossary
- `docs/ADMIN_GLOSSARY.md`

Current Phase C progress:
- catalog-domain read-only shell added for `/admin/servers|laws|templates|features|rules`
- first explicit law-domain submodule shell added for `Law Sources`, `Law Sets`, `Source Registry`, and `Server Bindings`
- page-shell domain maps added for `Servers`, `Templates`, `Capabilities`, and `Validation Rules`
- `Phase C` acceptance reached via separated read-only page shells and initial glossary-backed labeling

### Acceptance
- Admin can navigate pilot scenario config end-to-end without code.
- UI modules are separated by domain boundaries.

### Rollback/containment
- Read-only surface only; no mutation risk.

Dependencies: Phase B.

---

## Phase D — Editable admin + draft/publish/rollback/audit (2 sprints)

### D.1 Editable workflows
Status: `done`
For pilot entities, implement:
- create draft
- validate draft
- publish version
- rollback to previous version
- audit event timeline

Current D.1 progress:
- server-side `validate_change_request` added for workflow-backed pilot entities
- submit-for-review and publish now revalidate candidate versions before state transition
- `EDITABLE_WORKFLOW_CHECKLIST.md` added as the first editable workflow contract
- existing catalog workflow UI now has a `validate draft` action path wired to the validation endpoint
- `PUBLISH_RELEASE_CHECKLIST.md` added as the first publish gate checklist for pilot entities
- high-risk two-person approval gate added for `procedures`, `templates`, and `validation_rules`

### D.2 Publication gates
Status: `done`
- Publish blocked on validation errors.
- Two-person review option for high-risk entities (laws/templates/rules).

### Deliverables
- publication workflow endpoints + UI
- audit ledger for config changes
- release checklist per published bundle
- `EDITABLE_WORKFLOW_CHECKLIST.md`
- `PUBLISH_RELEASE_CHECKLIST.md`

### Acceptance
- Admin can safely change pilot scenario without touching code.
- rollback tested on pilot end-to-end.

### Rollback/containment
- Emergency republish of last known good version.
- Hard lock option on publish for incident mode.

Dependencies: Phase C.

---

## Phase E — Async/jobs stabilization (1 sprint)

Execution status: `done`

### E.1 Job model hardening
Status: `done`
Standardize job states across import/export/law rebuild/generation:
- queued, running, succeeded, failed, retry_scheduled, cancelled.

Current E.1 progress:
- `JOB_STATE_MATRIX.md` added as the canonical async state baseline.
- Current fragmentation documented across:
  - `AsyncJobService`: `pending`, `queued`, `processing`, `succeeded`, `dead_lettered`, `cancelled`
  - `ExamImportTaskRegistry`: `queued`, `running`, `completed`, `failed`
  - admin law rebuild tasks in `admin.py`: `queued`, `running`, `finished`, `failed`
- First implementation slice completed:
  - shared `job_status_service.py` normalizer added
  - canonical status is now exposed alongside raw status for `/api/jobs*`, `/api/exam-import/tasks/*`, `/api/admin/law-sources/tasks/*`, and `/api/admin/tasks/*`
- Second implementation slice completed:
  - `AsyncJobService` now uses `retry_scheduled` for automatic delayed retries instead of collapsing them into plain `queued`
  - worker claim paths now consume `retry_scheduled` jobs when `next_run_at` is due
- Third implementation slice completed:
  - admin dashboard now exposes an `Async Jobs` overview for failed/retry-scheduled background work
  - operator-facing summary counts and problem-job inventory are available through `/api/admin/async-jobs/overview`
- Fourth implementation slice completed:
  - the `Async Jobs` admin block now exposes first operator controls on top of shared `/api/jobs` endpoints
  - `failed` jobs can be retried manually, and `retry_scheduled` jobs can be cancelled from the dashboard surface
- Fifth implementation slice completed:
  - the same ops/dashboard surface now also exposes `law rebuild` task health and failed rebuild alerts
  - `admin/dashboard` can now be used as a single review surface for shared async jobs plus law runtime rebuild failures
- Sixth implementation slice completed:
  - the same ops/dashboard surface now also exposes `exam import` pending scoring, failed entries, and recent import/scoring failures
  - `admin/dashboard` now serves as one operator-facing review surface for shared async jobs, law rebuild alerts, and exam import problem signals
- Phase E.1 acceptance reached.

### E.2 Idempotency + retries
Status: `done`
- Add dedup keys for import/export/generation operations.
- Explicit retry policies by job type.
- Non-retryable failure classes documented.

Current E.2 progress:
- `docs/ASYNC_OPERATIONS_RUNBOOK.md` added as the operator runbook for shared async jobs, law rebuild, and exam import flows.
- `RETRY_IDEMPOTENCY_MATRIX.md` added as the explicit retry/idempotency contract baseline.
- `content_reindex` now has a route-level idempotency contract via `/api/admin/reindex`:
  - explicit `idempotency_key` is accepted
  - default dedup key now resolves to `content_reindex:{scope}`
- Remaining E.2 gaps are now narrowed to non-shared task models (`law rebuild`, `exam import`) rather than the shared async job surface.
- Phase E.2 acceptance reached for the shared async job surface.

### E.3 Ops visibility
Status: `done`
- Admin/Ops screen for failed jobs + retry controls + incident notes.

### Deliverables
- async operations runbook updates
- job observability views
- retry/idempotency matrix
- `JOB_STATE_MATRIX.md`
- `docs/ASYNC_OPERATIONS_RUNBOOK.md`
- `RETRY_IDEMPOTENCY_MATRIX.md`

### Acceptance
- No silent duplicate execution for covered job classes.
- Failed async operations visible and retryable by operators/admins.
- `Phase E` accepted via:
  - canonical operator-facing state layer
  - unified ops/dashboard surface for shared async jobs, law rebuild, and exam import
  - first operator controls for shared async jobs
  - async runbook plus retry/idempotency matrix deliverables

### Rollback/containment
- Per-job-type kill switches / queue pause / fallback to manual ops where needed.

Dependencies: Phase D for admin visibility, but partial hardening can start earlier if needed.

---

## Phase F — Provenance + legal/audit trace closure (1 sprint)

### F.1 Provenance schema
Persist minimum explainability metadata for generated outputs:
- server_id
- server_config_version
- procedure_version
- template_version
- law_set_version
- retrieval/citation fragment ids
- model/provider id
- prompt version
- generation timestamp

Status update:
- `in_progress`
- provenance baseline documented in `PROVENANCE_SCHEMA.md`
- read-only trace assembler implemented for `document_version_id`
- read-only API surface added for `GET /api/document-versions/{version_id}/provenance`
- generated document snapshot now includes provenance as a first traceable read surface
- next micro-step: expose the same trace in a dedicated admin trace section instead of snapshot-only access

### F.2 Admin traceability surface
- Show provenance in document review/admin/audit views.
- Expose why a document used particular law/context inputs.

### Deliverables
- provenance schema doc
- stored trace pipeline
- admin trace view for pilot scenario

### Acceptance
- Pilot generated document can be traced end-to-end through legal/config/model context.

### Rollback/containment
- No cutover to full new runtime active mode without minimum provenance fields present.

Dependencies: Phase B and Phase E.

---

## Phase G — Pilot cutover and measured scale-out (1 sprint + observation window)

Execution status: `done`

### G.1 Pilot activation
- Enable `new_runtime_active` only for reference pilot scenario.
- Keep all others on legacy or shadow mode.

### G.2 Observation window
- Monitor drift, support incidents, admin publish quality, async failures, provenance completeness.

### G.3 Scale-out rules
- Only add next server/procedure after pilot acceptance passes.
- Reuse same migration template for each new scenario.

### Deliverables
- pilot cutover report
- scale-out checklist/template
- deprecation list for removable legacy logic

### Acceptance
- Pilot stable across agreed observation window.
- Next migration candidate selected with evidence, not guesswork.

### Rollback/containment
- Revert pilot to `legacy_only` if drift/support/audit thresholds fail.

Dependencies: Phases B-F.

---

## Phase H — Post-pilot scale-out and legacy reduction (staged follow-up)

Execution status: `done`

### H.1 Next candidate rollout planning
- Select exactly one bounded next server or procedure candidate.
- Reuse the pilot rollout template instead of inventing a parallel migration path.
- Record candidate-specific gates before any activation change.
- Current H.1 recommendation: `blackberry + rehab` as the first same-server / second-procedure candidate.
- `H.1a` complete: code/seed-level rehab inventory verification is documented in `REHAB_ROLLOUT_GAP_MAP.md`.
- `H.1b` complete: runtime verification executed on production and recorded in `REHAB_ROLLOUT_GAP_MAP.md`.
- Runtime verification script: `scripts/verify_rehab_runtime_catalog.py` (DB-backed catalog checks for `blackberry + rehab`).
- `H.1c` complete: production catalog verification now passes after template/validation alignment.
- `H.1d` complete: rehab generation now mirrors complaint post-generation validation and is reviewable through the same admin provenance workspace.
- Current H.1 executable slice: `complete; move to H.2 legacy cleanup wave 1`.

### H.2 Legacy cleanup wave 1
- Remove only those compatibility seams that are already listed in the rollout backlog and have a satisfied removal gate.
- Keep rollback visibility and provenance/admin explainability intact after each cleanup slice.
- Completed H.2 slices:
  - `H.2a` server-side normalization of admin review-context refs plus removal of the client-side legacy raw-ref compaction workaround (`55accd1`)
  - `H.2b` removal of pilot adapter fallback-only `source_of_truth` visibility metadata (`e0098b3`)
  - `H.2c` removal of shadow-compare-only metrics plumbing and snapshot parity helper code (`07f302a`)
  - `H.2d` removal of compare-only pilot drift helper scripts and promotion of their docs to historical status (`c40d859`)
  - `H.2e` removal of fallback-only adapter snapshot visibility fields (`751d0a0`)
  - `H.2f` rollout/admin copy cleanup and remaining backlog tightening (`5fb1671`)
- Current H.2 executable slice: `complete`

### H.3 Runtime source-of-truth tightening
- Reduce transitional reads and legacy fallback assumptions only after the second candidate stabilizes.
- Keep route contracts stable while shrinking adapter-only compatibility paths.

### Deliverables
- next candidate brief and rollout gate
- rehab gap map and inventory verification note
- first accepted legacy cleanup wave
- updated removal checklist for remaining compatibility seams

### Acceptance
- One next candidate is selected with explicit scope, evidence, and rollback gate.
- First cleanup wave removes legacy logic without losing rollback safety or admin visibility.

### Rollback/containment
- Keep all non-selected scenarios on the current stable path.
- Revert the chosen candidate to legacy/shadow mode if rollout evidence regresses.

Dependencies: Phase G.

---

## Phase I — Runtime/admin convergence wave 1

Execution status: `ready_to_start`

### I.1 Shared server-context seam extraction
- Replace repeated direct `get_server_config(...)`/legacy server-context shaping in non-adapter runtime/admin paths with small shared helpers.
- Start only with one bounded seam at a time; do not fan out across unrelated routes in one pass.
- First candidate slice: complaint/admin server-context reads that still duplicate legacy `server_config` access patterns outside the accepted adapter path.
- `I.1a` complete on production commit `1b071bd`: `resolve_user_server_context(...)` now centralizes shared user server-config plus permission resolution for `pages.py` and bounded `admin.py` paths while keeping route contracts stable.
- `I.1b` complete on production commit `436fba9`: user-bound server-config reads in `complaint.py` and `profile.py` now reuse the same shared helper while keeping draft/profile route contracts stable.
- `I.1c` complete on production commit `d740b24`: `resolve_server_config(...)` now centralizes public/default server-config reads for login, verify-email, and reset-password page context assembly.
- `I.1d` complete on production commit `bc161e1`: `law_admin_service.py` now reuses shared server-config resolution in effective source, sync, and rebuild flows.
- `I.1e` complete on production commit `a562afc`: legacy complaint generation snapshot assembly now reuses shared server-config resolution.
- `I.1f` complete on production commit `a562afc`: bounded `ai_service` suggest/law helper paths now reuse shared server-config resolution.
- `I.1g` complete on production commit `3ae4349`: shared law-context helper functions now centralize `law_qa_bundle_path` and normalized `law_qa_sources` reads across bounded service paths.
- `I.1h` complete on production commit `bd4e104`: `law_retrieval_service.py` now reuses shared extracted law-context settings for source URLs, bundle path, and bundle max-age shaping.
- `I.1i` complete on production commit `ef329f4`: `law_qa_test` page rendering now reuses shared law-context helpers for source listing and server availability checks.
- Current I.1 executable slice: `select I.1j after the accepted law-QA page context seam`.

### I.2 Snapshot/provenance schema convergence
- Align legacy and adapter snapshot/provenance internals behind common helper contracts where the payload shape is already the same.
- Keep external route contracts and admin review payloads stable.
- Add parity assertions/tests whenever an internal snapshot block is deduplicated.
- `I.2` accepted on production through `I.2x`.

### I.3 Admin route decomposition wave 1
- Continue shrinking `routes/admin.py` by extracting one bounded server-backed subsection at a time into service/helper seams.
- Prioritize surfaces that already have clear service boundaries underneath them.
- Do not mix UI copy work, route splitting, and domain behavior changes in one slice.
- `I.3` accepted on production through `I.3u`.

### Deliverables
- `Phase I` execution brief with the first accepted bounded seam
- shared runtime/admin context helper map
- first accepted convergence slice on production

### Acceptance
- the first `Phase I` slice removes a real duplicated runtime/admin seam without changing route contracts
- tests cover parity for the extracted helper path
- GitHub, local docs, and server checkout remain synchronized after the slice

### Rollback/containment
- keep changes bounded to one seam per slice
- revert the single slice if parity or admin visibility regresses

Dependencies: Phase H.

---

## 3) What to do first

1. Finish Phase A inventory and lock pilot scenario.
2. Model new versioned config entities only for the pilot path.
3. Add adapter-backed read path for the pilot without changing external route contracts.
4. Add shadow compare before any active cutover.
5. Split admin read-only by domain before expanding mutation workflows.

## 4) What not to do

- Do not rewrite all routes/services at once.
- Do not expand legacy with more server-specific branching.
- Do not build one giant generic admin page/module for all domains.
- Do not migrate async operations invisibly without observability/idempotency.
- Do not activate new runtime for multiple scenarios before pilot evidence.

## 5) What can be postponed

- Full multi-server admin editability for all entities
- Broad server rollout
- Deep infra scaling optimizations
- Full replacement of every legacy path

Only postpone if pilot safety, async stability, and provenance guarantees remain intact.

## 6) Risk Register and Closure Strategy

### Risk 1 — Dual source of truth between legacy logic and new DB-driven workflow
- Priority: `critical`
- Owner area: `backend` + `migration/rollout`
- Trigger / warning signs:
  - conflicting outputs between legacy and new runtime
  - undocumented mixed reads from old config and new tables
- Mitigation:
  - feature-flagged adapter strategy
  - shadow compare before activation
  - explicit per-scenario source-of-truth assignment
- Validation:
  - drift reports for pilot scenario
  - contract regression checks stay green
- Closure milestone:
  - `Phase G` pilot cutover accepted

### Risk 2 — Hardcoded server-specific business logic for new servers
- Priority: `critical`
- Owner area: `backend`
- Trigger / warning signs:
  - new `if server == ...` paths
  - new enum/config hardcoding for server behavior
- Mitigation:
  - configuration-as-data rule
  - review rejection for scattered server conditionals
  - bounded extension points only when configuration is insufficient
- Validation:
  - migration review on pilot changes
  - no new scattered server branching introduced
- Closure milestone:
  - `Phase B` foundation approved, then enforced continuously

### Risk 3 — Frontend admin complexity collapsing into a monolithic admin UI
- Priority: `high`
- Owner area: `admin UI`
- Trigger / warning signs:
  - growth of one mega-page or mega-controller
  - domain state and UI concerns collapsing into one surface
- Mitigation:
  - domain-split read-only modules first
  - reusable UI/shared patterns
  - bounded editable workflows later
- Validation:
  - pilot domain navigation works through separate modules
  - no single admin module owns all new behavior
- Closure milestone:
  - `Phase C` read-only modular admin accepted

### Risk 4 — Transitional instability of background jobs, imports, exports, retries, and async processing
- Priority: `critical`
- Owner area: `infra` + `backend`
- Trigger / warning signs:
  - duplicate execution
  - invisible failed jobs
  - retry storms or dead-letter growth
- Mitigation:
  - explicit job states
  - idempotency keys
  - retry matrix by job type
  - ops/admin visibility
- Validation:
  - failed jobs visible and retryable
  - no silent duplicates for covered flows
- Closure milestone:
  - `Phase E` accepted

### Risk 5 — Incomplete AI / citation provenance for audit and explainability
- Priority: `critical`
- Owner area: `AI / retrieval`
- Trigger / warning signs:
  - generated output cannot be traced to law/config/model context
  - admin review cannot explain legal inputs used
- Mitigation:
  - minimum provenance schema
  - citation trace persistence
  - admin traceability views
- Validation:
  - pilot generated output trace is complete end-to-end
- Closure milestone:
  - `Phase F` accepted before broad activation

## 7) Acceptance gates by phase

- Phase A:
  - critical flow map complete
  - pilot fixed
- Phase B:
  - adapter-backed pilot read path works in shadow compare
- Phase C:
  - modular read-only admin for pilot config domains
- Phase D:
  - publish/rollback/audit works safely for pilot entities
- Phase E:
  - async operations observable, idempotent, retry-controlled
- Phase F:
  - provenance complete for pilot generated outputs
- Phase G:
  - pilot stable in observation window and rollback-ready

## Execution override update

- Current active phase: `Phase I`
- Last completed phase: `Phase H`
- Phase G progress:
  - pilot rollout visibility is now exposed in `admin/dashboard`
  - the ops workspace now includes a `Pilot rollout` block backed by `/api/admin/dashboard/sections/release`
  - the block derives canonical pilot state (`legacy_only` / `shadow_compare` / `new_runtime_active`) from `pilot_runtime_adapter_v1` and `pilot_shadow_compare_v1`
  - fallback and rollback signals are now visible before any pilot activation change
  - `PILOT_ACTIVATION_CHECKLIST.md` added as the first explicit preflight gate for `G.1`
  - the dashboard rollout block now includes an inline activation checklist before cutover
  - `SCALE_OUT_CHECKLIST_TEMPLATE.md` added as the first reusable template for `G.3`
  - `LEGACY_DEPRECATION_CANDIDATES.md` added as the first cleanup list for post-observation removal work
  - `PILOT_CUTOVER_REPORT_TEMPLATE.md` added as the first post-decision record template for `G.2`
  - the dashboard rollout block now includes `Operator playbooks` so preflight, cutover, scale-out, and deprecation references stay visible in one place
  - `PILOT_OBSERVATION_LOG_TEMPLATE.md` added for repeated observation-window checkpoints during `G.2`
  - the dashboard rollout block now includes `Observation guidance` for warning signals, fallback usage, rollback readiness, and review journaling
  - rollout warning signals now expose `severity`, `owner`, and `next action` directly in the dashboard so the observation window has an explicit triage surface
  - the dashboard rollout block now includes a `go / hold / rollback` cutover summary so operators can record an observation-window decision without re-reading every subsection
  - the dashboard rollout block now includes a `scale-out readiness` summary so reuse of the pilot template is gated before the next server or procedure candidate is selected
  - the dashboard rollout block now includes an `observation sign-off` table so cutover approval criteria are visible as `met / not met` checks
  - the dashboard rollout block now includes a human-readable `next candidate recommendation` summary so post-pilot reuse stays blocked or approved with an explicit reason
  - the dashboard rollout block now includes a `legacy cleanup backlog` table so post-pilot removal candidates are visible before any compatibility seam is deleted
- Next phase:
- `Phase H.1` selects one bounded post-pilot candidate and records its rollout gate before any broader scale-out
- initial H.1 recommendation is `blackberry + rehab`, not `strawberry + complaint`
- `H.1a` output is `REHAB_ROLLOUT_GAP_MAP.md`
- `H.1d` is complete on production commit `f7c0bb5`
- `Phase H.1` is accepted
- `H.2a` is complete on production commit `55accd1`
- `H.2b` is complete on production commit `e0098b3`
- `H.2c` is complete on production commit `07f302a`
- `H.2d` is complete on production commit `c40d859`
- `H.2e` is complete on production commit `751d0a0`
- `H.2f` is complete on production commit `5fb1671`
- `H.3a` is complete on production commit `6d21f72`: complaint generate skips the legacy snapshot builder when adapter flow is active
- `H.3b` is complete on production commit `b6b5328`: pilot runtime adapter no longer depends on legacy server-config lookup for law bundle metadata
- `H.3c` is complete on production commit `55a10a7`: complaint adapter snapshots now carry their own `feature_flags` without a route-level legacy server-config read
- `H.3d` is complete on production commit `b7699e7`: adapter snapshots drop the unused internal `runtime_adapter` ID block
- `H.3e` is complete on production commit `85078b2`: adapter fallback template/validation refs now reuse the shared complaint-service helpers instead of duplicating hash logic
- `H.3f` is complete on production commit `246ee73`: complaint form fallback refs now reuse the shared draft-schema helper instead of a second adapter-local hash path
- `H.3g` is complete on production commit `fda2d0f`: complaint adapter published workflow version reads and payload extraction are now centralized behind shared helper paths
- `H.3h` is complete on production commit `429287d`: complaint adapter runtime version dictionaries and feature-flag normalization now reuse strict helper builders instead of repeated inline assembly
- `H.3i` is complete on production commit `6b21e6e`: complaint adapter now caches published payload extraction plus fallback hash/ref helpers inside the resolver instead of recomputing them per version block
- `H.3j` is complete on production commit `4e04822`: complaint generation routes now isolate adapter-vs-legacy context snapshot assembly and shared shadow citations-policy injection behind local helpers
- `H.3k` is complete on production commit `d4170c3`: complaint adapter snapshot internals now use dedicated effective-config, content-workflow, and server snapshot helpers with parity coverage in tests
- `H.3l` is complete on production commit `1695401`: legacy complaint generation snapshots now use the same small helper structure for server/effective-config/content-workflow assembly, with parity coverage keeping content-workflow aligned to effective-config output
- `H.3` is accepted: no further meaningful complaint-path transitional seams remain that can be removed as small safe slices without inventing artificial refactors
- `Phase H` is accepted as complete
- `Phase I` is opened as the next execution phase
- `I.1a` is complete on production commit `1b071bd`: shared user server-context resolution is extracted and reused by `pages.py` plus bounded `admin.py` paths
- `I.1b` is complete on production commit `436fba9`: the same shared helper now also covers user-bound `complaint.py` and `profile.py` server-config reads
- `I.1c` is complete on production commit `d740b24`: public/default server-config reads in `pages.py` now reuse a shared resolver for login, verify-email, and reset-password surfaces
- `I.1d` is complete on production commit `bc161e1`: `law_admin_service.py` now reuses shared server-config resolution across effective, sync, and rebuild paths
- `I.1e` is complete on production commit `a562afc`: `complaint_service.build_generation_context_snapshot(...)` now reuses shared server-config resolution
- `I.1f` is complete on production commit `a562afc`: bounded `ai_service` suggest/law helper paths now reuse shared server-config resolution
- `I.1g` is complete on production commit `3ae4349`: shared law-context helper functions now centralize `law_qa_bundle_path` and normalized `law_qa_sources` reads across bounded service paths
- `I.1h` is complete on production commit `bd4e104`: `law_retrieval_service.py` now reuses shared extracted law-context settings
- `I.1i` is complete on production commit `ef329f4`: `law_qa_test` page rendering now reuses shared law-context helpers instead of direct `server_config.law_qa_*` reads
- immediate next step is `I.1j bounded seam selection after the accepted law-QA page context reuse`
- Phase F completed:
  - provenance baseline documented in `PROVENANCE_SCHEMA.md`
  - read-only provenance assembler implemented for `document_version_id`
  - read-only provenance API added at `/api/document-versions/{id}/provenance`
  - generated document snapshot now includes `generation_snapshot_id` and `provenance`
  - admin dashboard now includes provenance lookup by `document version id` and `generated document id`
  - admin dashboard now includes a recent-generated-documents review surface with one-click `Inspect trace`
  - review context now combines snapshot summary, workflow linkage, validation summary, validation issue preview, content preview, citation drilldown, and artifact/export summary
  - safe review drilldown links now exist for snapshot/validation/citations/exports APIs
- Phase F acceptance:
  - pilot generated output trace is explainable end-to-end from admin UI without direct DB inspection

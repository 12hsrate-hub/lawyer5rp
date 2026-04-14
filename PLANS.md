# PLANS.md — Migration Plan for Multi-Server Legal Platform (Staged, Repo-Aware)

Status: draft v1 (execution-ready baseline)
Date: 2026-04-14
Scope: staged migration inside current modular monolith (`web/ogp_web` + `shared`) without full rewrite.

## Current Execution State

- Current phase: `Phase B — Runtime model foundation + single source-of-truth contract`
- Current task: `Phase C complete`
- Active execution phase override: `Phase C - Visual Admin read-only modules`
- Current micro-step: `Read-only shells and glossary baseline completed for servers, laws, templates, features, and rules`
- Overall status: `done`
- Last updated: `2026-04-14`
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
- Initial implementation slice complete via `pilot_runtime_shadow_compare` metrics events and `scripts/report_pilot_drift.py`.

### Deliverables
- `DATA_MODEL_DRAFT.md`
- feature flags matrix (`legacy_only`, `shadow_compare`, `new_runtime_active`)
- drift-report script/check
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
For pilot entities, implement:
- create draft
- validate draft
- publish version
- rollback to previous version
- audit event timeline

### D.2 Publication gates
- Publish blocked on validation errors.
- Two-person review option for high-risk entities (laws/templates/rules).

### Deliverables
- publication workflow endpoints + UI
- audit ledger for config changes
- release checklist per published bundle

### Acceptance
- Admin can safely change pilot scenario without touching code.
- rollback tested on pilot end-to-end.

### Rollback/containment
- Emergency republish of last known good version.
- Hard lock option on publish for incident mode.

Dependencies: Phase C.

---

## Phase E — Async/jobs stabilization (1 sprint)

### E.1 Job model hardening
Standardize job states across import/export/law rebuild/generation:
- queued, running, succeeded, failed, retry_scheduled, cancelled.

### E.2 Idempotency + retries
- Add dedup keys for import/export/generation operations.
- Explicit retry policies by job type.
- Non-retryable failure classes documented.

### E.3 Ops visibility
- Admin/Ops screen for failed jobs + retry controls + incident notes.

### Deliverables
- async operations runbook updates
- job observability views
- retry/idempotency matrix

### Acceptance
- No silent duplicate execution for covered job classes.
- Failed async operations visible and retryable by operators/admins.

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

# plans.md — Migration Plan for Multi-Server Legal Platform (Staged, Repo-Aware)

Status: draft v1 (execution-ready baseline)  
Date: 2026-04-14  
Scope: staged migration inside current modular monolith (`web/ogp_web` + `shared`) without full rewrite.

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
Every configurable entity: draft → validate → publish → rollback (+ full audit timeline).

### 1.5 Infrastructure direction (incremental)
- PostgreSQL as source of truth.
- Redis for queue/cache/quota/temp state.
- S3-compatible storage for files/exports.
- Worker queue for async jobs.
- AI via adapter/gateway with provenance persistence.

---

## 2) Execution phases (with dependencies, acceptance, rollback)

## Phase A — Baseline inventory + migration map (1 sprint)

### A.1 Codebase inventory
- Map route -> service -> storage dependencies for all critical flows (`/login`, `/complaint`, `/admin`, `/exam_import`, document build/export).
- Mark hardcoded server-dependent paths.
- Mark async operations and retry/error handling locations.

### A.2 Define “reference pilot”
- Choose 1 reference server and 1 reference procedure as first migration scenario.
- Fix canonical old-vs-new behavior checklist for this scenario.

### Deliverables
- `MIGRATION_MAP.md`
- `ARCHITECTURE_NOTES.md`
- “legacy adapters list” (where compatibility must stay)

### Acceptance
- Full route/service map for critical user/admin journeys approved.
- Pilot scenario and cutover KPIs fixed.

### Rollback/containment
- No runtime switch yet; documentation-only phase.

Dependencies: none.

---

## Phase B — Runtime model foundation + single source-of-truth contract (1–2 sprints)

### B.1 Data model draft and persistence skeleton
Introduce versioned DB model families (minimal first):
- server_config_version
- procedure_version
- form_version
- validation_rule_version
- template_version
- law_set_version
- publication/audit events

### B.2 Read-path adapters
- Keep legacy endpoints.
- Add adapter layer that can resolve config from new model behind feature flags.
- Default remains legacy for all non-pilot scenarios.

### B.3 Drift detection
- Add shadow compare for pilot scenario: legacy output vs new-runtime-derived output.
- Persist mismatch logs with reason category.

### Deliverables
- `DATA_MODEL_DRAFT.md`
- feature flags matrix (`legacy_only`, `shadow_compare`, `new_runtime_active`)
- drift-report script/check

### Acceptance
- Pilot scenario can run in `shadow_compare` mode with measurable drift report.
- No regression in current production route contracts.

### Rollback/containment
- One-flag instant revert to `legacy_only` per scenario.

Dependencies: Phase A.

---

## Phase C — Visual Admin read-only modules (1 sprint)

### C.1 Read-only domain slices
Build separate admin views (read-only first):
- Servers
- Procedures
- Forms
- Rules
- Templates
- Law sets
- Publications/Audit

### C.2 UX language baseline
- Human-readable naming dictionary (user/admin-facing).
- Ban raw internal identifiers in visible labels by default.

### Deliverables
- `UI_ADMIN_STRUCTURE.md`
- read-only pages for pilot domain entities
- initial glossary

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
- retry/idempotency policy matrix

### Acceptance
- duplicate prevention verified for pilot async flows.
- failed jobs are visible and recoverable without DB manual edits.

### Rollback/containment
- Per-job kill switch + fallback to legacy execution path where available.

Dependencies: Phase D.

---

## Phase F — AI/retrieval/citation provenance hardening (1 sprint)

### F.1 Mandatory provenance persistence
Persist for every generated legal output:
- server_id
- server config version
- procedure version
- template version
- law_set version
- citation/fragment ids
- model/provider id
- prompt version
- generation timestamp

### F.2 Audit and admin exposure
- Add provenance panel in document review/admin audit views.
- Allow export of provenance trace for incident/legal review.

### Deliverables
- provenance schema + persistence in generation pipeline
- citation trace access in admin

### Acceptance
- Any pilot generated document is explainable from stored provenance.

### Rollback/containment
- If provenance capture fails, block publish-grade output or force fallback policy (configured per risk tolerance).

Dependencies: Phase D (and parallel integration with E).

---

## Phase G — Pilot cutover + staged expansion (ongoing)

### G.1 Cutover for reference scenario
- Move pilot scenario from `shadow_compare` to `new_runtime_active`.
- Keep legacy adapter path for bounded rollback window.

### G.2 Expansion waves
Migrate by scenario batches (not file batches):
- wave 1: nearest-neighbor scenarios
- wave 2: medium complexity
- wave 3: high-variance server-specific scenarios

### Deliverables
- per-wave migration checklists
- deprecation list for legacy-only logic

### Acceptance
- wave-level KPI stability + no critical drift.

### Rollback/containment
- scenario-level rollback to legacy flag.

Dependencies: B–F.

---

## 3) What to do first (next concrete actions)

1. Create `MIGRATION_MAP.md` from current route/service/storage graph for critical flows.
2. Freeze pilot server + pilot procedure + acceptance KPIs.
3. Define initial versioned configuration schema draft.
4. Implement feature-flag skeleton for scenario-level switching.
5. Enable `shadow_compare` for pilot with mismatch logging.

## 4) What not to do

- Do not migrate all servers at once.
- Do not merge admin into one giant module/page.
- Do not encode new server variance via Python enums/branching in route handlers.
- Do not replace legacy async ops silently without observability.
- Do not ship AI-generated legal outputs without provenance fields.

## 5) What can be postponed

- Full editable admin for all domains (read-only first).
- Non-critical scenario migration (after pilot stabilization).
- Advanced plugin extension points (only after config model limits are proven).

---

## Risk Register and Closure Strategy

### Risk 1 — Dual source of truth (legacy vs new runtime)
- Priority: Critical (pre-launch blocker for each cutover scenario)
- Owner area: backend + migration/rollout
- Trigger/warning signs: conflicting outputs between legacy and new path; unknown runtime authority in incidents.
- Why it matters: inconsistent legal/document outcomes and unpredictable behavior.
- Where now/likely: `web/ogp_web/routes/*` calling mixed legacy service logic while new config-driven runtime is introduced.
- Target rule: each migrated scenario has exactly one runtime authority; legacy becomes adapter-only.
- Mitigation:
  - scenario-level feature flags;
  - shadow compare before activation;
  - explicit cutover criteria;
  - post-cutover deprecation milestone.
- Earliest phase: B.
- Validation: drift rate below agreed threshold for pilot + incident playbook tested.
- Fallback/rollback: instant flag revert to `legacy_only`; keep adapter during rollback window.
- Closure milestone: completion of pilot + wave 1 cutovers with adapter demotion complete.

### Risk 2 — Hardcoded server-specific logic
- Priority: Critical (pre-scale blocker)
- Owner area: backend + admin model
- Trigger/warning signs: new `if server == ...` branches in routes/services; enum-driven legal divergence.
- Why it matters: exponential maintenance cost and brittle onboarding of new servers.
- Where now/likely: route/service conditionals in complaint/validation/document generation flows.
- Target rule: server differences live in versioned data/config models; code only interprets model.
- Mitigation:
  - code review gate forbidding new server hardcoding;
  - config schema coverage for procedure/forms/rules/templates/law sets;
  - bounded plugin extension policy when config is insufficient.
- Earliest phase: A (policy), B (implementation).
- Validation: PR checks/review checklist + no new hardcoded server branches in migrated flows.
- Fallback/rollback: if unavoidable hardcoded patch is needed, enforce temporary exception with removal deadline.
- Closure milestone: wave 2 complete with all migrated scenarios config-driven.

### Risk 3 — Monolithic admin UI complexity
- Priority: High (pre-scale blocker)
- Owner area: admin UI
- Trigger/warning signs: one massive page/module owning all admin state/actions.
- Why it matters: slows iteration, increases regression risk, hurts non-technical usability.
- Where now/likely: expansion of existing admin routes/static modules without domain boundaries.
- Target rule: domain-bounded modules + read-only-first + shared UI patterns.
- Mitigation:
  - split by domain sections;
  - route/module boundaries;
  - shared component library for tables/forms/audit timeline.
- Earliest phase: C.
- Validation: separate module ownership and independent deploy/testing paths for admin domains.
- Fallback/rollback: keep risky editable flows disabled; retain read-only visibility until stabilized.
- Closure milestone: D completion for pilot entities with modular UI structure proven.

### Risk 4 — Async/jobs transitional instability
- Priority: Critical (pre-launch blocker for migrated async flows)
- Owner area: infra + backend
- Trigger/warning signs: duplicate imports/exports, silent retries, invisible failed jobs.
- Why it matters: data integrity and operational instability during migration.
- Where now/likely: import/export/job endpoints and task services (`jobs`, `exam_import`, export/build pipelines).
- Target rule: explicit job state machine + idempotency + observable retry semantics.
- Mitigation:
  - standard job states;
  - dedup keys;
  - retry matrix;
  - failure dashboards.
- Earliest phase: E (design prework from B).
- Validation: chaos/retry tests pass; duplicate rate below threshold; failed-job MTTR target achieved.
- Fallback/rollback: kill-switch and legacy execution fallback.
- Closure milestone: E completion + two stable sprints post-pilot cutover.

### Risk 5 — Missing AI/citation provenance
- Priority: Critical (pre-launch blocker for legal-grade generated outputs)
- Owner area: AI/retrieval + audit
- Trigger/warning signs: generated document without traceable law/template/procedure context.
- Why it matters: no audit explainability; legal/compliance risk.
- Where now/likely: generation/retrieval/citation services and document output pipeline.
- Target rule: every generated output stores complete provenance envelope.
- Mitigation:
  - persist mandatory provenance fields;
  - citation fragment tracking;
  - admin/audit provenance views and exports.
- Earliest phase: F (schema hooks can begin in B).
- Validation: provenance completeness checks at generation time; audit export tests pass.
- Fallback/rollback: block publish-grade output or downgrade mode until provenance restored.
- Closure milestone: F completion + acceptance in pilot cutover gate.

---

## 6) Acceptance gates by milestone

### Gate G0 (after A)
- migration map complete
- pilot scenario selected
- risk controls aligned

### Gate G1 (after B+C)
- shadow compare active
- read-only admin visibility complete for pilot

### Gate G2 (after D+E+F)
- editable publish workflow stable
- async reliability controls active
- provenance complete for pilot outputs

### Gate G3 (after G wave 1)
- pilot cutover stable
- first migration wave complete
- legacy deprecation backlog prioritized with deadlines

---

## 7) Documentation strategy

Three layers maintained continuously:
1. Admin/user docs (human terminology and UI flows).
2. Ops docs (runbooks, incident/rollback, async operations).
3. Developer docs (schema, adapters, feature flags, migration boundaries).

Primary docs to keep updated during execution:
- `plans.md` (this file)
- `MIGRATION_MAP.md`
- `DATA_MODEL_DRAFT.md`
- `UI_ADMIN_STRUCTURE.md`
- `docs/OPERATIONS_INDEX.md` and linked runbooks

---

## 8) Ownership bootstrap (fill before Sprint 1)

- Backend migration lead: TBD
- Admin UI lead: TBD
- Infra/async lead: TBD
- AI/provenance lead: TBD
- Rollout/incident lead: TBD


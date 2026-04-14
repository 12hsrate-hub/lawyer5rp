# PLANS.md — Multi-server Legal Platform Staged Migration (Execution-oriented)

## Planning assumptions
- Source inputs read before planning: `AGENTS.md`, `docs/agents.md`, `docs/brief.md`, `docs/IMPLEMENTATION_PLAN.md`.
- `BRIEF.md` and prior root `PLANS.md` were not present; this file is rebuilt as the executable baseline.
- This plan treats the 5 mandatory risks from AGENTS as **binding constraints**.

## Mandatory risk constraints (binding)
1. Dual source of truth between legacy logic and DB-driven runtime.
2. Hardcoded server-specific business logic.
3. Monolithic admin UI complexity.
4. Async/jobs/import/export migration instability.
5. Incomplete AI/citation provenance for audit/explainability.

---

## Phase 1 — Baseline architecture inventory and migration boundaries
**Goal**  
Freeze a repo-aware baseline: current modules, legacy/new boundaries, and first reference migration scenario.

**Why now**  
Without this, subsequent phases risk accidental rewrites and uncontrolled scope.

**Dependencies**  
None.

**Risks**  
R1, R2 (wrong boundaries create long-term drift).

**Acceptance criteria**  
- Migration map exists with explicit "legacy adapter" boundaries.
- First reference scenario selected (1 server + 1 procedure path).
- No ambiguous ownership for runtime decisions.

**Deliverables / artifacts**  
- `PLANS.md` (this file)
- `docs/MIGRATION_MAP.md`
- `docs/ARCHITECTURE_NOTES.md`

**Read-only first vs editable later**  
- Read-only now: discovery and mapping only.
- Editable later: code moves and adapters.

**Legacy compatibility notes**  
All legacy routes/services remain functional; this phase only defines boundaries.

**Proposed task(s)**

### Task P1-T1 — Build current-state module map
- **One-sentence execution goal:** Produce a precise map of backend routes/services/stores/workers and their domain ownership.
- **Scope / boundaries:** Static inventory only; no schema or behavior changes.
- **Files or modules to inspect/change:** `web/ogp_web/routes/*`, `web/ogp_web/services/*`, `web/ogp_web/db/*`, `web/ogp_web/workers/*`, `tests/test_*` (contract tests).
- **Deliverable:** `docs/ARCHITECTURE_NOTES.md` section "Current state map".
- **Validation / acceptance checks:** Every production route maps to a primary service owner and storage dependency.
- **Rollback / containment note:** Documentation-only task; no runtime impact.
- **Blocking dependencies:** None.
- **Priority (P0/P1/P2):** P0.

### Task P1-T2 — Define migration seams and adapter boundaries
- **One-sentence execution goal:** Mark which legacy modules become adapter-only and where new runtime owns decisions.
- **Scope / boundaries:** Decision-boundary design for selected reference scenario.
- **Files or modules to inspect/change:** `web/ogp_web/routes/complaint.py`, `web/ogp_web/routes/validation.py`, `web/ogp_web/services/generation_orchestrator.py`, `web/ogp_web/services/legal_pipeline_service.py`, `docs/MIGRATION_MAP.md`.
- **Deliverable:** `docs/MIGRATION_MAP.md` with seam diagram and cutover criteria.
- **Validation / acceptance checks:** Single source of truth identified for each migrated decision point.
- **Rollback / containment note:** If seam unclear, keep legacy path as default and delay cutover.
- **Blocking dependencies:** P1-T1.
- **Priority (P0/P1/P2):** P0.

---

## Phase 2 — Platform core runtime model (server-aware, versioned)
**Goal**  
Create core runtime entities for server pack, procedures, forms, rules, templates, and capabilities as versioned data.

**Why now**  
This is prerequisite to eliminate server-specific hardcoding and support multiple servers safely.

**Dependencies**  
Phase 1.

**Risks**  
R1, R2.

**Acceptance criteria**  
- Runtime decisions read from versioned DB entities for reference scenario.
- Clear rule for configuration vs plugin extension.

**Deliverables / artifacts**  
- Schema design notes + migration scripts
- Runtime registry services
- Anti-hardcoding review checklist

**Read-only first vs editable later**  
- Read-only first: runtime fetch APIs.
- Editable later: admin CRUD/publish tools.

**Legacy compatibility notes**  
Legacy constants/enums remain until adapter switchover is complete.

**Proposed task(s)**

### Task P2-T1 — Define canonical runtime data contract
- **One-sentence execution goal:** Specify versioned DB contract for server packs and procedure runtime.
- **Scope / boundaries:** Contract and migration design only for initial entities.
- **Files or modules to inspect/change:** `web/ogp_web/db/migrations/versions/postgres/*`, `web/ogp_web/services/server_config_registry.py`, `web/ogp_web/services/runtime_*`.
- **Deliverable:** Contract spec in `docs/DATA_MODEL_DRAFT.md` + migration plan.
- **Validation / acceptance checks:** Contract covers server_id, versions, statuses (draft/published), effective dates.
- **Rollback / containment note:** Keep old contract untouched; deploy new tables side-by-side.
- **Blocking dependencies:** P1-T2.
- **Priority (P0/P1/P2):** P0.

### Task P2-T2 — Implement runtime resolution service behind feature flag
- **One-sentence execution goal:** Build runtime resolver that picks effective versioned config by server and scenario.
- **Scope / boundaries:** Resolver + read APIs; no full admin editing yet.
- **Files or modules to inspect/change:** `web/ogp_web/services/server_config_registry.py`, `web/ogp_web/services/feature_flags.py`, `web/ogp_web/routes/validation.py`.
- **Deliverable:** Resolver service + flag-guarded integration for reference path.
- **Validation / acceptance checks:** Shadow compare reports parity with legacy outputs for baseline fixtures.
- **Rollback / containment note:** Disable feature flag to return fully to legacy resolver.
- **Blocking dependencies:** P2-T1.
- **Priority (P0/P1/P2):** P0.

### Task P2-T3 — Enforce anti-hardcoding governance
- **One-sentence execution goal:** Add explicit review gates that reject new server-specific conditionals outside approved extension points.
- **Scope / boundaries:** CI/static checks + contribution rule updates.
- **Files or modules to inspect/change:** `tests/`, `docs/CODEX_RUN_GUIDE.md`, `docs/README.md`, lint/test helpers.
- **Deliverable:** Anti-hardcoding check + documented extension policy.
- **Validation / acceptance checks:** New `if server == ...` patterns fail checks unless in whitelisted plugin boundary.
- **Rollback / containment note:** Policy can run warning-only for one sprint before hard fail.
- **Blocking dependencies:** P2-T1.
- **Priority (P0/P1/P2):** P1.

---

## Phase 3 — Visual admin architecture (modular, read-first)
**Goal**  
Restructure admin surface by domain, starting with read-only views and progressive editability.

**Why now**  
Admin is core product surface for non-technical operators; wrong structure causes long-term lock-in.

**Dependencies**  
Phase 2.

**Risks**  
R3, R2.

**Acceptance criteria**  
- Domain-separated admin sections exist (not mega-page).
- Read-only discovery views available for each key domain.

**Deliverables / artifacts**  
- `docs/UI_ADMIN_STRUCTURE.md`
- Admin navigation map + shared UI patterns

**Read-only first vs editable later**  
Read-only domain panels first; editing/publish tools later with audit.

**Legacy compatibility notes**  
Existing admin pages remain available until equivalent domain modules are stable.

**Proposed task(s)**

### Task P3-T1 — Define admin domain IA and module boundaries
- **One-sentence execution goal:** Create explicit information architecture for admin domains and shared components.
- **Scope / boundaries:** IA, routes, module boundaries; no bulk UI rewrite.
- **Files or modules to inspect/change:** `web/ogp_web/static/pages/admin.js`, `web/ogp_web/static/shared/admin_*`, `web/ogp_web/templates/*admin*`, `docs/UI_ADMIN_STRUCTURE.md`.
- **Deliverable:** Domain map for Servers, Procedures, BB Codes, Forms, Rules, Templates, Law Sets, Publications, Audit, Users & Permissions.
- **Validation / acceptance checks:** Each domain has isolated data-fetch and state boundary.
- **Rollback / containment note:** Keep current admin entrypoint as fallback shell.
- **Blocking dependencies:** P2-T1.
- **Priority (P0/P1/P2):** P0.

### Task P3-T2 — Deliver read-only admin slices for runtime entities
- **One-sentence execution goal:** Implement first read-only admin pages for runtime entities from new resolver.
- **Scope / boundaries:** Read-only list/detail views for reference server/procedure.
- **Files or modules to inspect/change:** `web/ogp_web/routes/admin.py`, `web/ogp_web/static/shared/admin_runtime_*`, `web/ogp_web/templates/admin*.html`.
- **Deliverable:** Navigable read-only admin views backed by new runtime service.
- **Validation / acceptance checks:** Admin can inspect active/pending versions without editing.
- **Rollback / containment note:** Feature-flag route to legacy admin data provider.
- **Blocking dependencies:** P3-T1, P2-T2.
- **Priority (P0/P1/P2):** P1.

### Task P3-T3 — Add editable tools with draft/publish constraints
- **One-sentence execution goal:** Add scoped edit flows with draft/publish/rollback/audit workflow.
- **Scope / boundaries:** One domain first (e.g., procedures/forms) before broader rollout.
- **Files or modules to inspect/change:** `web/ogp_web/routes/admin.py`, `web/ogp_web/services/law_admin_service.py`, `web/ogp_web/services/content_workflow_service.py`.
- **Deliverable:** First editable domain module with versioned workflow controls.
- **Validation / acceptance checks:** No direct mutation of published version; rollback creates audit trail.
- **Rollback / containment note:** Disable edit actions, keep read-only mode.
- **Blocking dependencies:** P3-T2, P6-T1.
- **Priority (P0/P1/P2):** P1.

---

## Phase 4 — Procedure pipeline migration (forms, validation, templates, BB catalogs)
**Goal**  
Migrate one end-to-end procedure flow from legacy logic to configuration-driven runtime.

**Why now**  
Delivers first tangible business scenario proving architecture without full rewrite.

**Dependencies**  
Phases 2–3.

**Risks**  
R1, R2, R5.

**Acceptance criteria**  
- Reference procedure completes user flow using versioned data.
- Legacy and new behavior parity validated by fixtures.

**Deliverables / artifacts**  
- Reference server pack for one procedure
- Mapping doc from legacy fields/rules to new model

**Read-only first vs editable later**  
Use read-only runtime snapshots during migration; editing unlocked after parity.

**Legacy compatibility notes**  
Legacy handler remains available behind switch until cutover criteria met.

**Proposed task(s)**

### Task P4-T1 — Create legacy-to-runtime mapping for reference procedure
- **One-sentence execution goal:** Map legacy inputs, rules, templates, BB codes to versioned runtime records.
- **Scope / boundaries:** One procedure only.
- **Files or modules to inspect/change:** `web/ogp_web/routes/complaint.py`, `web/ogp_web/services/complaint_service.py`, `web/ogp_web/services/validation_service.py`, `web/ogp_web/services/document_builder_service.py`.
- **Deliverable:** Mapping matrix + data seed specification.
- **Validation / acceptance checks:** Every legacy decision point mapped to runtime source.
- **Rollback / containment note:** Keep legacy execution as primary until parity checks pass.
- **Blocking dependencies:** P2-T2.
- **Priority (P0/P1/P2):** P0.

### Task P4-T2 — Implement dual-run shadow validation and drift alerts
- **One-sentence execution goal:** Run legacy and new pipelines in shadow for the same inputs and report drift.
- **Scope / boundaries:** Non-blocking shadow mode for selected traffic/fixtures.
- **Files or modules to inspect/change:** `web/ogp_web/services/generation_orchestrator.py`, `web/ogp_web/services/legal_pipeline_service.py`, `web/ogp_web/services/input_audit_service.py`, logs/metrics hooks.
- **Deliverable:** Drift report and alert thresholds.
- **Validation / acceptance checks:** Drift rate below approved threshold for cutover window.
- **Rollback / containment note:** Keep shadow-only mode if drift exceeds threshold.
- **Blocking dependencies:** P4-T1.
- **Priority (P0/P1/P2):** P0.

### Task P4-T3 — Cut over reference procedure to new runtime source of truth
- **One-sentence execution goal:** Switch reference procedure execution to runtime resolver while legacy becomes adapter-only.
- **Scope / boundaries:** One procedure + one server; no global cutover.
- **Files or modules to inspect/change:** `web/ogp_web/routes/complaint.py`, `web/ogp_web/routes/validation.py`, feature flag configs.
- **Deliverable:** Controlled cutover with runbook and rollback toggle.
- **Validation / acceptance checks:** Production checks pass; rollback tested within defined window.
- **Rollback / containment note:** Immediate toggle back to legacy source for failed SLOs.
- **Blocking dependencies:** P4-T2.
- **Priority (P0/P1/P2):** P0.

---

## Phase 5 — Law registry and publication flow
**Goal**  
Establish versioned law sets and publication lifecycle aligned with runtime procedures.

**Why now**  
Legal context must be stable/versioned before broad AI generation or audit promises.

**Dependencies**  
Phases 2 and 4.

**Risks**  
R1, R5.

**Acceptance criteria**  
- Law set versions are publishable/rollbackable with audit.
- Procedure runtime references law_set versions explicitly.

**Deliverables / artifacts**  
- Law registry model and publication workflow
- Law set linkage rules to server/procedure versions

**Read-only first vs editable later**  
Read-only publication history first; editing/publish actions later.

**Legacy compatibility notes**  
Existing law bundles can be imported as initial versions, not hardcoded runtime assets.

**Proposed task(s)**

### Task P5-T1 — Normalize law set version model and links
- **One-sentence execution goal:** Ensure law sets are first-class versioned entities linked to server/procedure runtime.
- **Scope / boundaries:** Data model and service contract alignment.
- **Files or modules to inspect/change:** `web/ogp_web/services/law_bundle_service.py`, `web/ogp_web/services/law_version_service.py`, related migrations.
- **Deliverable:** Updated law version linkage spec + migration patch list.
- **Validation / acceptance checks:** Runtime can resolve exact law_set version for generated document.
- **Rollback / containment note:** Preserve previous linkage columns until migration stable.
- **Blocking dependencies:** P2-T1.
- **Priority (P0/P1/P2):** P0.

### Task P5-T2 — Add publication workflow and rollback for law sets
- **One-sentence execution goal:** Implement draft/publish/rollback lifecycle for law sets with audit events.
- **Scope / boundaries:** Law registry domain only.
- **Files or modules to inspect/change:** `web/ogp_web/services/content_workflow_service.py`, `web/ogp_web/routes/admin.py`, `web/ogp_web/services/law_admin_service.py`.
- **Deliverable:** Publish API + rollback action + audit entries.
- **Validation / acceptance checks:** Published version immutable; rollback selectable and logged.
- **Rollback / containment note:** Disable publish endpoints if invariants fail.
- **Blocking dependencies:** P5-T1, P6-T1.
- **Priority (P0/P1/P2):** P1.

---

## Phase 6 — Draft/Publish/Rollback/Audit platform cross-cutting controls
**Goal**  
Unify version lifecycle and audit guarantees across server packs, procedures, templates, and laws.

**Why now**  
Cross-domain workflow consistency is needed before scale and admin edit expansion.

**Dependencies**  
Phases 2 and 3.

**Risks**  
R1, R3, R5.

**Acceptance criteria**  
- Shared lifecycle policy applies across all major admin-managed entities.
- Audit logs capture actor, change set, and effective version references.

**Deliverables / artifacts**  
- Workflow policy spec
- Audit event schema
- Cross-domain lifecycle conformance checks

**Read-only first vs editable later**  
Audit/read visibility first; mutation endpoints gated until conformance checks pass.

**Legacy compatibility notes**  
Legacy write paths remain restricted; new lifecycle applies only to migrated domains.

**Proposed task(s)**

### Task P6-T1 — Standardize lifecycle state machine across domains
- **One-sentence execution goal:** Define and enforce a single draft/publish/rollback state model used by all target entities.
- **Scope / boundaries:** State model + service-level guards.
- **Files or modules to inspect/change:** `web/ogp_web/services/content_workflow_service.py`, `web/ogp_web/schemas*.py`, migrations for status columns.
- **Deliverable:** Lifecycle specification and guarded service APIs.
- **Validation / acceptance checks:** Invalid transitions rejected uniformly across domains.
- **Rollback / containment note:** Keep entity-specific transitions until global model fully adopted.
- **Blocking dependencies:** P2-T1.
- **Priority (P0/P1/P2):** P0.

### Task P6-T2 — Implement audit event contract and admin visibility
- **One-sentence execution goal:** Persist and surface immutable audit events for lifecycle actions.
- **Scope / boundaries:** Audit storage + read APIs/UI.
- **Files or modules to inspect/change:** `web/ogp_web/services/admin_dashboard_service.py`, `web/ogp_web/routes/admin.py`, `web/ogp_web/static/shared/admin_activity.js`.
- **Deliverable:** Audit event timeline in admin for migrated domains.
- **Validation / acceptance checks:** Every publish/rollback action has actor/timestamp/version reference.
- **Rollback / containment note:** If UI fails, retain backend logging as source for audits.
- **Blocking dependencies:** P6-T1.
- **Priority (P0/P1/P2):** P1.

---

## Phase 7 — AI/retrieval/citation provenance hardening
**Goal**  
Guarantee traceability for generated outputs and legal citations across runtime versions.

**Why now**  
Explainability and auditability are pre-launch blockers for legal outputs.

**Dependencies**  
Phases 4–6.

**Risks**  
R5 (primary), R1.

**Acceptance criteria**  
- Minimum provenance fields persisted per generation.
- Citation trace resolvable from document/admin views.

**Deliverables / artifacts**  
- Provenance storage contract
- Citation trace service
- Admin provenance view

**Read-only first vs editable later**  
Read-only provenance inspection first; no manual provenance edits.

**Legacy compatibility notes**  
Legacy generation allowed only if provenance fallback is captured.

**Proposed task(s)**

### Task P7-T1 — Define and persist minimum provenance fields
- **One-sentence execution goal:** Store mandatory provenance tuple for every generation run.
- **Scope / boundaries:** Persistence model + generation write path.
- **Files or modules to inspect/change:** `web/ogp_web/services/legal_pipeline_service.py`, `web/ogp_web/services/law_retrieval_service.py`, `web/ogp_web/db/migrations/versions/postgres/0007_citations_retrieval.sql`, `0017_generation_snapshot_effective_config_and_document_status.sql`.
- **Deliverable:** Provenance schema + write integration.
- **Validation / acceptance checks:** Fields present: server_id, server_config_version, procedure_version, template_version, law_set_version, citation_ids, model/provider, prompt_version, generation_timestamp.
- **Rollback / containment note:** Block publish of generated docs missing required provenance.
- **Blocking dependencies:** P5-T1, P6-T1.
- **Priority (P0/P1/P2):** P0.

### Task P7-T2 — Surface provenance and citation trace in admin/review flows
- **One-sentence execution goal:** Provide admin/reviewer visibility into exact legal and model context of outputs.
- **Scope / boundaries:** Read APIs and UI panels; no mutation.
- **Files or modules to inspect/change:** `web/ogp_web/routes/admin.py`, `web/ogp_web/static/shared/admin_runtime_laws.js`, document review templates.
- **Deliverable:** Provenance tab/panel on document review.
- **Validation / acceptance checks:** Reviewer can trace each citation fragment to source/version.
- **Rollback / containment note:** Hide panel only if backend stable storage remains intact.
- **Blocking dependencies:** P7-T1.
- **Priority (P0/P1/P2):** P1.

---

## Phase 8 — Async jobs/imports/exports and infra migration (Redis/Queue/S3)
**Goal**  
Stabilize asynchronous operations with explicit states, retries, idempotency, and operational visibility.

**Why now**  
Async instability is often silent until business-critical failures appear.

**Dependencies**  
Phases 4 and 6.

**Risks**  
R4 (primary), R1.

**Acceptance criteria**  
- Job state machine and retry policy documented and enforced.
- Admin/ops can inspect failed and stuck jobs.

**Deliverables / artifacts**  
- Async migration runbook
- Job state dashboards
- Retry/idempotency policy

**Read-only first vs editable later**  
Read-only observability first; operational controls (retry/requeue) later.

**Legacy compatibility notes**  
Legacy async paths remain available until per-job cutover validation is complete.

**Proposed task(s)**

### Task P8-T1 — Standardize async job contract and idempotency keys
- **One-sentence execution goal:** Define unified job schema with deterministic idempotency and retry semantics.
- **Scope / boundaries:** Job model + worker contract.
- **Files or modules to inspect/change:** `web/ogp_web/workers/job_worker.py`, `web/ogp_web/workers/worker_pool.py`, `web/ogp_web/routes/jobs.py`, `tests/test_async_jobs_layer.py`.
- **Deliverable:** Async contract spec + base implementation.
- **Validation / acceptance checks:** Duplicate submits do not execute side effects twice.
- **Rollback / containment note:** Route selected job types back to legacy executor if error rates spike.
- **Blocking dependencies:** P4-T2.
- **Priority (P0/P1/P2):** P0.

### Task P8-T2 — Add job visibility and failure containment surfaces
- **One-sentence execution goal:** Expose job status, retries, and failure reasons in admin/ops interfaces.
- **Scope / boundaries:** Monitoring endpoints + admin read views.
- **Files or modules to inspect/change:** `web/ogp_web/routes/jobs.py`, `web/ogp_web/routes/admin.py`, `web/ogp_web/static/shared/admin_overview*.js`.
- **Deliverable:** Job observability panel + failure playbook links.
- **Validation / acceptance checks:** Operators can identify stuck/failed jobs and next action.
- **Rollback / containment note:** If UI unavailable, CLI/runbook path remains documented.
- **Blocking dependencies:** P8-T1.
- **Priority (P0/P1/P2):** P1.

### Task P8-T3 — Migrate imports/exports to phased queue workers
- **One-sentence execution goal:** Move import/export heavy operations onto queue workers with staged cutover.
- **Scope / boundaries:** One operation type at a time (exam import first, exports second).
- **Files or modules to inspect/change:** `web/ogp_web/routes/exam_import.py`, `web/ogp_web/routes/exports.py`, `web/ogp_web/services/exam_import_service.py`, `web/ogp_web/services/export_service.py`.
- **Deliverable:** Phased migration runbook and cutover toggles per operation.
- **Validation / acceptance checks:** Throughput and failure SLOs meet baseline before next operation migrates.
- **Rollback / containment note:** Per-operation rollback switch to synchronous/legacy handler.
- **Blocking dependencies:** P8-T1, P8-T2.
- **Priority (P0/P1/P2):** P1.

---

## Phase 9 — Master manifest, docs layers, rollout, and legacy cleanup
**Goal**  
Finalize exportable manifest, operational docs, and safe decommissioning of duplicated legacy logic.

**Why now**  
Only after core flows stabilize should cleanup and governance become enforceable.

**Dependencies**  
Phases 4–8.

**Risks**  
R1, R2, R4, R5.

**Acceptance criteria**  
- Master manifest export/import reflects published state.
- Legacy duplicate decision paths removed per cutover checklist.

**Deliverables / artifacts**  
- `docs/MANIFEST_SPEC.md`
- Updated user/admin/ops/dev docs set
- Legacy removal checklist with closure sign-off

**Read-only first vs editable later**  
Manifest export/read first, import controls later with validation gates.

**Legacy compatibility notes**  
Legacy code removed only after cutover metrics remain stable for agreed rollback window.

**Proposed task(s)**

### Task P9-T1 — Define master manifest schema and export pipeline
- **One-sentence execution goal:** Specify and generate one canonical manifest for published server/runtime/legal configuration.
- **Scope / boundaries:** Export first; import validation separately.
- **Files or modules to inspect/change:** `web/ogp_web/services/export_service.py`, `web/ogp_web/routes/exports.py`, `docs/MANIFEST_SPEC.md`.
- **Deliverable:** Versioned manifest spec + export endpoint.
- **Validation / acceptance checks:** Manifest reproduces published runtime snapshot for reference server.
- **Rollback / containment note:** Keep manifest read-only until import validation is hardened.
- **Blocking dependencies:** P5-T2, P6-T2.
- **Priority (P0/P1/P2):** P1.

### Task P9-T2 — Build three-layer documentation set (admin/ops/dev)
- **One-sentence execution goal:** Publish coherent docs for non-technical admins, operations, and developers.
- **Scope / boundaries:** Update docs; no runtime behavior changes.
- **Files or modules to inspect/change:** `docs/README.md`, `docs/RUNBOOK.md`, `docs/OPERATIONS_INDEX.md`, new admin guides.
- **Deliverable:** Linked doc set mapped to migrated domains.
- **Validation / acceptance checks:** Each critical flow has one admin guide + one ops runbook reference.
- **Rollback / containment note:** Preserve legacy docs until replacements validated.
- **Blocking dependencies:** P3-T2, P8-T2.
- **Priority (P0/P1/P2):** P2.

### Task P9-T3 — Execute legacy cleanup by scenario closure checklist
- **One-sentence execution goal:** Remove duplicated legacy logic only for scenarios that passed cutover and rollback windows.
- **Scope / boundaries:** Scenario-by-scenario cleanup, not bulk deletion.
- **Files or modules to inspect/change:** legacy routes/services mapped in `docs/MIGRATION_MAP.md`.
- **Deliverable:** Closed scenario checklist + removed duplicate branches.
- **Validation / acceptance checks:** No active scenario depends on removed legacy source-of-truth logic.
- **Rollback / containment note:** Tag release before removal; restore from tag if latent regressions appear.
- **Blocking dependencies:** P4-T3, P7-T2, P8-T3, P9-T1.
- **Priority (P0/P1/P2):** P1.

---

## Risk Register and Closure Strategy

### Risk 1 — Dual source of truth between legacy and DB runtime
- **Priority:** Critical (P0), pre-launch blocker.
- **Owner area:** backend + migration/rollout.
- **Trigger / warning signs:** Divergent outputs between legacy and runtime; unclear ownership of decision logic.
- **Mitigation:** P1-T2, P4-T2, P4-T3, P9-T3.
- **Validation:** Shadow drift reports + explicit cutover checklist + legacy adapter-only confirmation.
- **Closure milestone:** After P4-T3 for reference scenario; fully closed after P9-T3 across migrated scenarios.

### Risk 2 — Hardcoded server-specific logic
- **Priority:** Critical (P0), pre-scale blocker.
- **Owner area:** backend + architecture governance.
- **Trigger / warning signs:** New `if server == ...` branches, enum growth, per-server route forks.
- **Mitigation:** P2-T1, P2-T3, P3-T1, P4-T1.
- **Validation:** CI/review checks reject scattered conditionals; all server differences represented in versioned config.
- **Closure milestone:** Governance enforced by P2-T3; operationally closed after second server onboarded with zero hardcoded branches.

### Risk 3 — Monolithic admin UI complexity
- **Priority:** High (P1), pre-scale blocker.
- **Owner area:** admin UI.
- **Trigger / warning signs:** Single mega-admin module/page owning all domains; tightly coupled state.
- **Mitigation:** P3-T1, P3-T2, P3-T3, P6-T2.
- **Validation:** Domain-level module boundaries + independent navigation/state/data loading.
- **Closure milestone:** After P3-T3 for first editable domain and P6-T2 audit visibility.

### Risk 4 — Async/jobs/import/export instability
- **Priority:** Critical (P0), pre-launch blocker for async-heavy flows.
- **Owner area:** infra + backend + ops.
- **Trigger / warning signs:** Silent job failures, duplicate effects, missing retry visibility.
- **Mitigation:** P8-T1, P8-T2, P8-T3.
- **Validation:** Idempotency tests, retry policy conformance, observable failed/stuck jobs.
- **Closure milestone:** After P8-T3 staged migration and SLO pass for migrated operations.

### Risk 5 — Incomplete AI/citation provenance
- **Priority:** Critical (P0), pre-launch blocker for legal generation.
- **Owner area:** AI/retrieval + backend + admin review.
- **Trigger / warning signs:** Documents cannot be traced to exact law/template/prompt/model context.
- **Mitigation:** P7-T1, P7-T2, P5-T1, P6-T2.
- **Validation:** Mandatory provenance fields present and reviewable for sampled generated documents.
- **Closure milestone:** After P7-T2 with audit sampling sign-off.

If any risk is not tied to concrete tasks, the plan is incomplete. Current status: **all 5 mandatory risks are tied to concrete tasks above**.

---

## Launchable Task Backlog

1. **P1-T1** | Build current-state module map | Phase 1 | **P0** | deps: none | acceptance: full route/service/storage ownership map.
2. **P1-T2** | Define migration seams and adapter boundaries | Phase 1 | **P0** | deps: P1-T1 | acceptance: single source-of-truth boundaries + cutover criteria.
3. **P2-T1** | Define canonical runtime data contract | Phase 2 | **P0** | deps: P1-T2 | acceptance: versioned entities + lifecycle fields fully specified.
4. **P2-T2** | Implement runtime resolution service behind feature flag | Phase 2 | **P0** | deps: P2-T1 | acceptance: resolver parity in shadow checks.
5. **P4-T1** | Create legacy-to-runtime mapping for reference procedure | Phase 4 | **P0** | deps: P2-T2 | acceptance: all legacy decision points mapped.
6. **P4-T2** | Implement dual-run shadow validation and drift alerts | Phase 4 | **P0** | deps: P4-T1 | acceptance: drift rate within threshold window.
7. **P4-T3** | Cut over reference procedure to new runtime source of truth | Phase 4 | **P0** | deps: P4-T2 | acceptance: production cutover + tested rollback.
8. **P6-T1** | Standardize lifecycle state machine across domains | Phase 6 | **P0** | deps: P2-T1 | acceptance: uniform transition guards enforced.
9. **P5-T1** | Normalize law set version model and links | Phase 5 | **P0** | deps: P2-T1 | acceptance: runtime resolves exact law_set version.
10. **P7-T1** | Define and persist minimum provenance fields | Phase 7 | **P0** | deps: P5-T1, P6-T1 | acceptance: mandatory provenance tuple stored per generation.
11. **P8-T1** | Standardize async job contract and idempotency keys | Phase 8 | **P0** | deps: P4-T2 | acceptance: duplicate submits are idempotent.
12. **P2-T3** | Enforce anti-hardcoding governance | Phase 2 | **P1** | deps: P2-T1 | acceptance: review/CI rejects scattered server conditionals.
13. **P3-T1** | Define admin domain IA and module boundaries | Phase 3 | **P0** | deps: P2-T1 | acceptance: domain-isolated admin boundaries documented.
14. **P3-T2** | Deliver read-only admin slices for runtime entities | Phase 3 | **P1** | deps: P3-T1, P2-T2 | acceptance: read-only runtime version inspection available.
15. **P6-T2** | Implement audit event contract and admin visibility | Phase 6 | **P1** | deps: P6-T1 | acceptance: publish/rollback actions visible with actor+version.
16. **P5-T2** | Add publication workflow and rollback for law sets | Phase 5 | **P1** | deps: P5-T1, P6-T1 | acceptance: immutable publish + reversible rollback with audit.
17. **P7-T2** | Surface provenance and citation trace in admin/review flows | Phase 7 | **P1** | deps: P7-T1 | acceptance: reviewer sees full citation trace.
18. **P8-T2** | Add job visibility and failure containment surfaces | Phase 8 | **P1** | deps: P8-T1 | acceptance: failed/stuck jobs are observable and actionable.
19. **P8-T3** | Migrate imports/exports to phased queue workers | Phase 8 | **P1** | deps: P8-T1, P8-T2 | acceptance: operation-by-operation SLO-safe cutover.
20. **P3-T3** | Add editable tools with draft/publish constraints | Phase 3 | **P1** | deps: P3-T2, P6-T1 | acceptance: first editable domain with safe lifecycle controls.
21. **P9-T1** | Define master manifest schema and export pipeline | Phase 9 | **P1** | deps: P5-T2, P6-T2 | acceptance: manifest reproduces published snapshot.
22. **P9-T3** | Execute legacy cleanup by scenario closure checklist | Phase 9 | **P1** | deps: P4-T3, P7-T2, P8-T3, P9-T1 | acceptance: duplicate legacy source-of-truth branches removed safely.
23. **P9-T2** | Build three-layer documentation set (admin/ops/dev) | Phase 9 | **P2** | deps: P3-T2, P8-T2 | acceptance: every critical flow documented for admin and ops.


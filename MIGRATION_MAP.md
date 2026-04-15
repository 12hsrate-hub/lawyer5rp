# MIGRATION_MAP.md — Baseline route/service/storage map (Phase A start)

Status: initial baseline  
Date: 2026-04-14

## Execution Status

- Execution checkpoint: `2026-04-15`
- Active phase: `Phase J`
- Active task: `J.3 AI facade tightening`
- Status: `in_progress`
- Last completed phase: `Phase H`
- Inventory slices completed: `6`
- Next slice: `move remaining suggest runtime-context and transport glue out of ai_service.py without changing route contracts`
- Last updated: `2026-04-16`
- Phase H progress:
  - `H.1a` selected `blackberry + rehab` as the bounded next candidate and recorded the rollout gate
  - `H.1b` runtime catalog verification executed on production commit `1e74a26`
  - `H.1c` deployed on production commit `de6bb2f`
  - production verification now passes for:
    - `procedures:rehab_law_index`
    - `templates:rehab_template_v1`
    - `laws:law_sources_manifest`
    - `validation_rules:rehab_default`
    - bootstrap `validation_profiles.rehab`
  - `H.1d` deployed on production commit `f7c0bb5`
  - rehab remains on the bounded transitional runtime path, not a complaint-only adapter clone
  - `/api/generate-rehab` now mirrors complaint post-generation validation behavior for `document_version`
  - API coverage confirms rehab-generated documents are visible through admin provenance and review context with non-empty validation summary
  - `Phase H.1` is accepted; next work moves to `H.2`
  - `H.2a` deployed on production commit `55accd1`
  - admin generated-document review context now emits normalized string refs instead of legacy-shaped raw refs
  - the client-side legacy raw-ref compaction workaround has been removed from `admin.js`
  - `H.2b` deployed on production commit `e0098b3`
  - pilot adapter fallback-only `source_of_truth` visibility metadata has been removed
  - `H.2c` deployed on production commit `07f302a`
  - shadow-compare-only complaint metrics plumbing and the pilot snapshot parity helper have been removed
  - `H.2d` deployed on production commit `c40d859`
  - compare-only pilot drift helper scripts were removed because no runtime path emits `pilot_runtime_shadow_compare` anymore
  - `H.2e` deployed on production commit `751d0a0`
  - pilot adapter runtime snapshots no longer expose fallback-only visibility fields (`status`, `content_item_id`) while keeping published-read resolution intact
  - `H.2f` deployed on production commit `5fb1671`
  - rollout/admin copy is now renamed away from pilot/preflight-only wording while preserving the same rollout-state logic
  - `Phase H.2 wave 1` is accepted as complete
  - next work moves to `H.3 Runtime source-of-truth tightening`
  - `H.3a` deployed on production commit `6d21f72`
  - `/api/generate` no longer builds `legacy_context_snapshot` when `pilot_runtime_adapter_v1` is active for `blackberry + complaint`
  - `H.3b` deployed on production commit `b6b5328`
  - `resolve_pilot_complaint_runtime_context` no longer needs legacy `get_server_config(...)` lookup just to resolve law bundle metadata
  - `H.3c` deployed on production commit `55a10a7`
  - complaint adapter snapshots now carry `feature_flags` directly, so the route no longer needs a route-level legacy server-config read when adapter flow is active
  - `H.3d` deployed on production commit `b7699e7`
  - complaint adapter snapshots no longer carry the unused internal `runtime_adapter` ID block
  - `H.3e` deployed on production commit `85078b2`
  - complaint adapter fallback template/validation refs now reuse the shared complaint-service helper logic instead of maintaining a second hash-calculation path
  - `H.3f` deployed on production commit `246ee73`
  - complaint form fallback refs now reuse the shared draft-schema helper instead of maintaining a second adapter-local hash path
  - `H.3g` deployed on production commit `fda2d0f`
  - complaint adapter published workflow version reads and payload extraction are now centralized behind shared helper paths without changing the snapshot contract
  - `H.3h` deployed on production commit `429287d`
  - complaint adapter runtime version dictionaries and feature-flag normalization are now assembled through strict helper builders instead of repeated inline fallback blocks
  - `H.3i` deployed on production commit `6b21e6e`
  - complaint adapter now caches published payload extraction and fallback hash/ref helpers inside the resolver instead of recomputing them for each runtime version block
  - `H.3j` deployed on production commit `4e04822`
  - complaint generation routes now isolate adapter-vs-legacy context snapshot assembly and shared shadow citations-policy injection behind local helpers without changing route contracts
  - `H.3k` deployed on production commit `d4170c3`
  - complaint adapter snapshot internals now use dedicated effective-config, content-workflow, and server snapshot helpers, with a parity assertion keeping `content_workflow.applied_published_versions` aligned with `effective_config_snapshot`
  - `H.3l` deployed on production commit `1695401`
  - legacy complaint generation snapshots now use the same small helper structure for server/effective-config/content-workflow assembly, with parity coverage keeping legacy content_workflow aligned with effective_config_snapshot
  - `H.3` is accepted
  - no further meaningful complaint-path transitional seams remain that can be removed as small safe slices without inventing artificial refactors
  - `Phase H` is accepted as complete
  - `Phase I` is opened
  - first focus area is runtime/admin convergence for remaining non-adapter `server_config` seams outside the accepted complaint adapter path
  - `I.1a` deployed on production commit `1b071bd`
  - shared `resolve_user_server_context(...)` now owns the bounded user server-config plus permission resolution seam reused by `pages.py` and selected `admin.py` paths
  - `I.1b` deployed on production commit `436fba9`
  - user-bound server-config reads in `complaint.py` and `profile.py` now reuse the same shared helper without changing complaint draft or selected-server route contracts
  - `I.1c` deployed on production commit `d740b24`
  - public/default server-config reads in `pages.py` now reuse shared `resolve_server_config(...)` for login, verify-email, and reset-password context assembly
  - `I.1d` deployed on production commit `bc161e1`
  - `law_admin_service.py` now reuses shared `resolve_server_config(...)` across effective source, sync, and rebuild paths
  - `I.1e` deployed on production commit `a562afc`
  - legacy complaint generation snapshot assembly now reuses shared `resolve_server_config(...)`
  - `I.1f` deployed on production commit `a562afc`
  - bounded `ai_service` suggest/law helper paths now reuse shared `resolve_server_config(...)`
  - `I.1g` deployed on production commit `3ae4349`
  - shared law-context helper functions now centralize `law_qa_bundle_path` and normalized `law_qa_sources` reads across bounded service paths
  - `I.1h` deployed on production commit `bd4e104`
  - `law_retrieval_service.py` now reuses shared extracted law-context settings for source URLs, bundle path, and bundle max-age shaping
  - `I.1i` deployed on production commit `ef329f4`
  - `law_qa_test` page rendering now reuses shared law-context helpers for source listing and server availability filtering
  - `I.1j` deployed on production commit `6ca518f`
  - `ai_service` now reuses shared extracted AI-context settings for law-QA/suggest shadow profiles plus suggest prompt/policy shaping
  - `I.1k` deployed on production commit `7026994`
  - shared server identity extraction now backs `law_retrieval_service` result shaping and complaint generation snapshot server metadata
  - `I.1l` deployed on production commit `7026994`
  - shared normalized feature-flag extraction now backs complaint snapshot feature flags and `ai_service` feature checks
  - `I.1m` deployed on production commit `078350d`
  - shared page/admin shell context extraction now backs `pages.py` and `admin.py` route rendering paths
  - `I.1n` deployed on production commit `4b64c12`
  - shared complaint/page server settings now back complaint payload validation plus complaint-test and exam-import page rendering
  - `I.1o` deployed on production commit `ff9be09`
  - shared user-permissions resolution now backs admin cross-server law-sources permission checks, and the `complaint_test_page` settings regression is fixed in production
  - `I.1p` deployed on production commit `9c83be7`
  - shared user-server config resolution now backs `profile.py` selected-server switching and complaint route config reads
  - `I.1q` deployed on production commit `9c83be7`
  - shared law-QA server availability/identity helpers now back `pages.py` and law-sources dependency reporting
  - `I.1r` deployed on production commit `adb09aa`
  - `law_qa_test_page` now reuses shared server identity for source loading instead of repeated direct `server_config.code` reads
  - `I.1s` deployed on production commit `adb09aa`
  - law-sources dependency reporting no longer re-resolves server identity after the shared law-QA availability helper already supplied it
  - `I.1t` deployed on production commit `adb09aa`
  - dead `resolve_server_config(...)` reads were removed from bounded law-QA admin/AI helper paths without changing runtime contracts
  - `I.1u` deployed on production commit `8395223`
  - repeated request-default server-config lookup in `pages.py` is now centralized behind `_request_server_config(...)` for login, verify-email, and reset-password rendering
  - `I.1v` deployed on production commit `8395223`
  - tiny dead cleanup leftovers were removed from bounded page/law-admin paths, and stale `law_admin_service` tests now follow the shared server-context helpers
  - `I.1w` deployed on production commit `304d9d6`
  - shared `resolve_server_ai_context_settings(...)` now backs bounded AI law-QA and suggest call sites instead of local extract-only seams
  - `I.1x` deployed on production commit `304d9d6`
  - shared `resolve_server_identity(...)` and `resolve_server_feature_flags(...)` now back bounded complaint generation snapshot assembly and related server-context tests
  - `I.1y` deployed on production commit `c7be298`
  - shared user-level resolvers now back complaint route identity/settings checks and remove the last local `_server_config_for_user(...)` wrapper
  - `I.1z` deployed on production commit `c7be298`
  - verify-email page server selection now reuses a single page-level resolver for request-default and username-bound rendering paths
  - `I.1` is accepted
  - `I.2a` deployed on production commit `6844864`
  - shared generation snapshot schema helpers now back admin review-context summary/linkage shaping and provenance extraction without changing route payloads
  - `I.2b` deployed on production commit `81faa7b`
  - shared generation-context schema blocks now back legacy complaint snapshots and pilot adapter snapshots for server/effective-config/content-workflow assembly
  - `I.2c` deployed on production commit `81faa7b`
  - `generation_orchestrator` now reuses the shared persistence-block extractor for `effective_config_snapshot` and `content_workflow` instead of inline schema checks
  - `I.2d` deployed on production commit `81faa7b`
  - shared provenance lookup by `generation_snapshot_id` now backs generated-document snapshot and admin provenance bridge paths
  - `I.2e` deployed on production commit `33533e0`
  - shared generated-document trace bundle resolution now backs user snapshot, admin provenance, and admin review-context routes
  - `I.2f` deployed on production commit `33533e0`
  - shared generated-document provenance/review-context builders now own the remaining route-local generated-document trace payload assembly without changing external contracts
  - `I.2g` deployed on production commit `15def5a`
  - user generated-document snapshot and history reads now resolve through shared store/service helpers instead of the read-only `GenerationOrchestrator` bridge path
  - `I.2h` deployed on production commit `15def5a`
  - generation-snapshot row decoding is now centralized inside `UserStore` for the generated-document snapshot readers
  - `I.2i` deployed on production commit `15def5a`
  - dead read-only snapshot/history bridge methods were removed from `GenerationOrchestrator` after the store-backed read path took ownership
  - `I.2j` deployed on production commit `ed75805`
  - row-based provenance trace building now avoids duplicate `document_version` reads when resolving by `generation_snapshot_id`
  - `I.2k` deployed on production commit `ed75805`
  - the store-backed provenance service factory is now centralized in `provenance_service`
  - `I.2l` deployed on production commit `ed75805`
  - complaint/admin generated-document provenance routes now reuse bundle-based provenance resolution instead of split `generation_snapshot_id/version_row` wiring
  - `I.2m` deployed on production commit `ff6884f`
  - generated-document review-context supporting data now resolves through a shared helper instead of inline service wiring
  - `I.2n` deployed on production commit `ff6884f`
  - bbcode preview truncation is now centralized in a dedicated generated-document helper
  - `I.2o` deployed on production commit `ff6884f`
  - admin generated-document review-context now uses a bundle-based wrapper helper for naming parity with the provenance path
  - `I.2p` deployed on production commit `c1fdaa9`
  - shared admin/user generated-document bundle require helpers now own route-appropriate 404 handling
  - `I.2q` deployed on production commit `c1fdaa9`
  - the user generated-document snapshot route now uses a shared snapshot payload wrapper instead of inline `snapshot + provenance` assembly
  - `I.2r` deployed on production commit `c1fdaa9`
  - complaint/admin generated-document routes now follow one consistent bundle-guard/wrapper pattern across snapshot, provenance, and review-context surfaces
  - `I.2s` deployed on production commit `d8dd0d8`
  - document-version provenance server access checks plus payload resolution now converge behind shared `provenance_service` route helpers
  - `I.2t` deployed on production commit `d8dd0d8`
  - generated-document trace bundles now expose normalized generated-document/server/version metadata accessors consumed by review/support builders
  - `I.2u` deployed on production commit `d8dd0d8`
  - generated-document snapshot payload assembly now converges behind a shared builder instead of bundle-wrapper inline merging
  - `I.2v` deployed on production commit `62c2d5d`
  - generated-document list item normalization now converges behind shared helpers instead of route-local timestamp/field shaping
  - `I.2w` deployed on production commit `62c2d5d`
  - user generated-document history now flows through a shared generated-document list helper instead of route-local normalization
  - `I.2x` deployed on production commit `62c2d5d`
  - admin recent generated-documents now reuses the same shared list helper layer with normalized `generation_snapshot_id` and `username` shaping
  - `I.2` is accepted
  - no further meaningful snapshot/provenance convergence seams remain that remove a real second source of truth without slipping into wrapper-only reshuffling
  - route contracts remain unchanged and the first thirty-three Phase I convergence slices are accepted
  - `I.3a` deployed on production commit `2b70af8`
  - `exam_import` overview payload assembly now converges behind a shared admin overview helper reused by both the standalone admin route and the main dashboard payload builder
  - `I.3b` deployed on production commit `e83b789`
  - `law-jobs` overview payload assembly now converges behind a shared admin overview helper instead of route-local filtering/summary logic in `routes/admin.py`
  - `I.3c` deployed on production commit `e83b789`
  - `async-jobs` overview payload assembly now converges behind the same shared admin overview helper layer instead of route-local status bucketing/grouping logic
  - `I.3d` deployed on production commit `1c532df`
  - runtime-server CRUD payload assembly now converges behind a dedicated admin runtime-server helper layer instead of route-local response shaping
  - `I.3e` deployed on production commit `1c532df`
  - runtime-server health payload assembly now converges behind the same helper layer instead of route-local dependency orchestration inside `routes/admin.py`
  - `I.3f` deployed on production commit `dcd6adc`
  - runtime-server law-sets and law-bindings payload assembly now converges behind a shared admin law-management helper layer instead of route-local store orchestration in `routes/admin.py`
  - `I.3g` deployed on production commit `dcd6adc`
  - law-set rebuild and rollback context preparation now converges behind the same helper layer instead of route-local store lookups and empty-source validation
  - `I.3h` deployed on production commit `dcd6adc`
  - law-source registry list/create/update payload assembly now converges behind the same helper layer instead of route-local shaping in `routes/admin.py`
  - `I.3i` deployed on production commit `5035570`
  - law-sources status, sync, rebuild, save, preview, history, and dependency payload orchestration now converges behind a shared admin law-sources helper layer instead of route-local `LawAdminService` wiring
  - `I.3j` deployed on production commit `5035570`
  - permission-aware target server resolution for law-sources operations now converges behind the same helper layer instead of route-local cross-server permission checks
  - `I.3k` deployed on production commit `5035570`
  - law-sources task-status guarding and canonical payload shaping now converge behind the same helper layer instead of route-local task validation in `routes/admin.py`
  - `I.3l` deployed on production commit `d660d7f`
  - catalog audit/list/get/versions payload assembly now converges behind a shared admin catalog helper layer instead of route-local workflow-service orchestration
  - `I.3m` deployed on production commit `d660d7f`
  - catalog workflow action dispatch plus change-request review/validate payload shaping now converge behind the same helper layer instead of route-local action branching
  - `I.3n` deployed on production commit `d660d7f`
  - catalog item create/update/rollback payload configuration and active change-request resolution now converge behind the same helper layer instead of route-local config shaping in `routes/admin.py`
  - `I.3o` deployed on production commit `2bed351`
  - admin users list payload assembly now converges behind a shared admin users helper layer instead of route-local metrics/user overview shaping
  - `I.3p` deployed on production commit `2bed351`
  - admin user details payload assembly now converges behind the same helper layer instead of route-local permission snapshot and activity summary shaping
  - `I.3q` deployed on production commit `2bed351`
  - role-history and users.csv reporting now converge behind the same helper layer instead of route-local overview/export wiring in `routes/admin.py`
  - `I.3r` deployed on production commit `024c3e2`
  - verify-email plus block/unblock payload assembly now converges behind a shared admin user-mutations helper layer instead of route-local store-call wiring
  - `I.3s` deployed on production commit `024c3e2`
  - tester/gka role toggles and email/password update payload assembly now converge behind the same helper layer instead of route-local per-endpoint mutation shaping
  - `I.3t` deployed on production commit `024c3e2`
  - deactivate/reactivate and daily-quota payload assembly now converge behind the same helper layer instead of route-local write-path handling in `routes/admin.py`
  - `I.3u` deployed on production commit `f9d34a8`
  - bulk user-mutation dispatch now converges behind the same shared admin user-mutations helper layer instead of route-local action branching and duplicated metrics meta
  - `I.3` is accepted
  - no further meaningful admin route decomposition seams remain that remove a real second orchestration layer without slipping into task-boundary or wrapper-only reshuffling
  - `I.4a` deployed on production commit `c9ad609`
  - `/api/admin/dashboard` KPI, alerts, quick-links, and recent-event aggregation now converge behind a shared admin analytics helper instead of route-local assembly
  - `I.4b` deployed on production commit `c9ad609`
  - `/api/admin/overview` metrics, model-policy, error-explorer, synthetic summary, and partial-error orchestration now converge behind the same shared analytics helper instead of route-local glue
  - `I.4c` deployed on production commit `c9ad609`
  - `/api/admin/performance` caching, latency/rates/totals shaping, and snapshot metadata now converge behind the same shared analytics helper instead of route-local cache and formatting helpers
  - `I.4d` deployed on production commit `6d93cc7`
  - `/api/admin/ai-pipeline` summary/generation/feedback orchestration now converges behind a dedicated admin AI pipeline service instead of staying inline in `routes/admin.py`
  - `I.4e` deployed on production commit `6d93cc7`
  - ai-pipeline recent-window filtering, quality summary, cost tables, top inaccurate generations, and policy-action shaping now converge behind the same shared service instead of route-local helper sprawl
  - `I.4f` deployed on production commit `6d93cc7`
  - the remaining ai-pipeline helper leftovers were removed from `routes/admin.py`, helper tests now target the service layer directly, and the admin analytics wave is accepted
  - `I.5a` deployed on production commit `6ad4359`
  - shared admin task persistence, task claiming, and canonical task-status loading now converge behind `AdminTaskOpsService` instead of route-local globals in `routes/admin.py`
  - `I.5b` deployed on production commit `6ad4359`
  - `law-jobs` overview and `law-sources/rebuild-async` now reuse the same task ops service instead of keeping route-local queue/orchestration logic
  - `I.5c` deployed on production commit `6ad4359`
  - async `users/bulk-actions` dispatch and generic `/api/admin/tasks/{task_id}` status now reuse the same service, and API tests now override the dependency-backed task service instead of patching route globals
  - `I.5` is accepted
  - `Phase I` is accepted
  - the next real seam is no longer in `admin.py`; it is the still-monolithic suggest/law-QA orchestration that remains inside `ai_service.py` despite the existing `ogp_web.services.ai_pipeline` package
  - `Phase J` is opened for bounded `ai_service -> ai_pipeline` extraction work
  - `J.1a` deployed on production commit `dbeacc2`
  - suggest prompt-compaction and generation-retry orchestration now converge behind `ai_pipeline.orchestration` helpers instead of staying inline in `ai_service.py`
  - `J.1b` deployed on production commit `dbeacc2`
  - suggest validation retry / safe-fallback remediation now converge behind the same orchestration layer while keeping the public suggest contract stable
  - the local `get_server_config(...)` seam in `ai_service.py` now uses a compatibility wrapper so shared server-context resolution remains positional-safe for retrieval helpers
  - `J.1c` deployed on production commit `3114c63`
  - suggest warning aggregation and `SuggestTextResult` payload assembly now converge behind the same orchestration layer instead of staying inline in `ai_service.py`
  - `J.1d` deployed on production commit `c5ad780`
  - suggest telemetry/result finalization now converges behind the same orchestration layer, and the dead local suggest/law-qa metrics helper duplicates were removed from `ai_service.py`
  - `J.2a` deployed on production commit `00bcafe`
  - law-QA telemetry/result finalization now converges behind `ai_pipeline.orchestration` instead of staying inline in `ai_service.py`
  - `J.2b` deployed on production commit `872bc05`
  - law-QA context-compaction retry orchestration now converges behind the same shared layer instead of staying inline in `ai_service.py`
  - `J.2c` deployed on production commit `3004077`
  - law-QA runtime-context assembly now converges behind the same shared layer instead of staying inline in `ai_service.py`
  - `J.2` is accepted
  - after runtime-context, retry, and finalization extraction, the remaining law-QA block is mostly thin facade glue rather than another high-value orchestration seam
  - `J.3a` is ready locally
  - suggest runtime-context assembly now converges behind `ai_pipeline.orchestration.resolve_suggest_runtime_context(...)`, so `suggest_text_details(...)` no longer keeps inline validation, retrieval-shadow, low-confidence policy, and compaction-attempt assembly
- Phase C progress:
  - `UI_ADMIN_STRUCTURE.md` added as the read-only admin boundary map for the catalog-oriented admin pages.
  - Read-only page shells are now in place for `/admin/servers|laws|templates|features|rules`.
  - Initial glossary baseline added in `docs/ADMIN_GLOSSARY.md`.
  - Explicit page-shell subdomains are in place for servers, laws, templates, features, and rules.
- Phase D progress:
  - `ContentWorkflowService` now exposes explicit change-request validation for pilot editable entities.
  - Submit-for-review and publish paths now revalidate the candidate version before state transition.
  - `EDITABLE_WORKFLOW_CHECKLIST.md` added as the first editable workflow contract for pilot entities.
  - Existing catalog workflow UI now exposes a `validate draft` action path for workflow-backed entities in draft state.
  - High-risk two-person approval is now enforced for `procedures`, `templates`, and `validation_rules`.
  - `PUBLISH_RELEASE_CHECKLIST.md` added as the first release gate checklist for pilot publish actions.

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

## Verified inventory slices

### Slice 1 — Authentication flow (`/api/auth/*`, `/api/profile*`)

**Routes**
- `web/ogp_web/routes/auth.py`
- `web/ogp_web/routes/profile.py`

**Primary dependencies**
- `ogp_web.dependencies.get_user_store`
- `ogp_web.dependencies.requires_permission`
- `ogp_web.services.auth_service`
- `ogp_web.services.profile_service`
- `ogp_web.services.email_service`
- `ogp_web.storage.user_store.UserStore`
- `ogp_web.rate_limit.auth_rate_limit`

**Confirmed route -> service -> storage map**
- `GET /api/auth/me`
  - route auth guard: `requires_permission()`
  - session/user resolution: `auth_service.require_user` -> `request.app.state.user_store` or default `UserStore`
  - storage authority: `UserStore.get_auth_user`, `UserStore.is_access_blocked`
- `POST /api/auth/register`
  - route: `auth.py`
  - rate limit: `auth_rate_limit(..., "register", request.app.state.rate_limiter)`
  - storage write authority: `UserStore.register(...)`
  - side effect: `email_service.send_verification_email(...)` via threadpool
- `POST /api/auth/login`
  - route: `auth.py`
  - rate limit: `auth_rate_limit(..., "login", request.app.state.rate_limiter)`
  - storage read authority: `UserStore.authenticate(...)`
  - session cookie authority: `auth_service.set_auth_cookie(...)`
- `POST /api/auth/resend-verification`
  - storage authority: `UserStore.issue_email_verification_token(...)`
  - side effect: `email_service.send_verification_email(...)`
- `POST /api/auth/logout`
  - session cookie authority: `auth_service.clear_auth_cookie(...)`
- `POST /api/auth/forgot-password`
  - rate limit: `auth_rate_limit(..., "forgot-password", request.app.state.rate_limiter)`
  - storage authority: `UserStore.issue_password_reset_token(...)`
  - side effect: `email_service.send_password_reset_email(...)`
- `POST /api/auth/reset-password`
  - storage authority: `UserStore.reset_password(...)`
  - session cookie authority: `auth_service.set_auth_cookie(...)`
- `POST /api/auth/change-password`
  - auth guard: `requires_permission()`
  - storage authority: `UserStore.change_password(...)`
  - session cookie authority: `auth_service.set_auth_cookie(...)`
- `GET /api/profile`
  - auth guard: `requires_permission()`
  - service wrapper: `profile_service.get_profile_payload(...)`
  - storage authority: `UserStore.get_representative_profile(...)`
- `PUT /api/profile`
  - auth guard: `requires_permission()`
  - service wrapper: `profile_service.save_profile_payload(...)`
  - storage authority: `UserStore.save_representative_profile(...)`
- `PATCH /api/profile/selected-server`
  - auth guard: `require_user`
  - storage authority: `UserStore.set_selected_server_code(...)`, `UserStore.get_complaint_draft(...)`
  - server config dependency: `server_config.registry.get_server_config(...)`
  - draft normalization dependency: `complaint_draft_schema.normalize_complaint_draft(...)`, `classify_switch_actions(...)`

**Storage/infrastructure anchor**
- Primary storage authority for auth/profile/session state: `web/ogp_web/storage/user_store.py`
- Backing repository abstraction: `web/ogp_web/storage/user_repository.py`
- Backend factory: `web/ogp_web/db/factory.py`
- Session token/cookie logic is not DB-backed directly; it is handled in `web/ogp_web/services/auth_service.py`

**Current migration seam note**
- This slice already mixes route-level auth/session logic, cookie/session logic, email side effects, and user/profile persistence around one storage authority (`UserStore`).
- For migration planning, auth/profile should likely stay route-contract stable while persistence/runtime resolution moves behind adapter/service boundaries rather than being split first.

### Slice 2 - Complaint/case flow (`/api/complaint-*`, `/api/generate*`, `/api/cases*`)

**Routes**
- `web/ogp_web/routes/complaint.py`
- `web/ogp_web/routes/cases.py`
- `web/ogp_web/routes/validation.py`
- `web/ogp_web/routes/document_builder.py`

**Primary dependencies**
- `web/ogp_web/services/complaint_service.py`
- `web/ogp_web/services/generation_orchestrator.py`
- `web/ogp_web/services/case_service.py`
- `web/ogp_web/services/document_service.py`
- `web/ogp_web/services/validation_service.py`
- `web/ogp_web/services/retrieval_service.py`
- `web/ogp_web/services/citation_service.py`
- `web/ogp_web/services/feature_flag_service.py`
- `web/ogp_web/repositories/case_repository.py`
- `web/ogp_web/repositories/document_repository.py`
- `web/ogp_web/repositories/validation_repository.py`
- `web/ogp_web/storage/user_store.py`
- `web/ogp_web/storage/admin_metrics_store.py`

**Confirmed route -> service -> storage map**
- Complaint generation and related runtime endpoints in `web/ogp_web/routes/complaint.py` (`/api/complaint-draft`, `/api/generate`, `/api/generate-rehab`, generated document history/snapshot, AI suggestion, law QA, citations, feedback):
  - payload/profile shaping: `web/ogp_web/services/complaint_service.py`
  - generation persistence bridge: `web/ogp_web/services/generation_orchestrator.py`
  - retrieval/citations: `web/ogp_web/services/retrieval_service.py`, `web/ogp_web/services/citation_service.py`
  - validation reads: `web/ogp_web/services/validation_service.py` -> `web/ogp_web/repositories/validation_repository.py`
  - user draft/profile authority: `web/ogp_web/storage/user_store.py`
  - admin metrics side effects: `web/ogp_web/storage/admin_metrics_store.py`
- Case/document workflow endpoints in `web/ogp_web/routes/cases.py` (`/api/cases`, `/api/cases/{id}`, `/api/cases/{id}/documents`, `/api/documents/{id}/versions`, `/api/documents/{id}/status`):
  - case domain service: `web/ogp_web/services/case_service.py` -> `web/ogp_web/repositories/case_repository.py`
  - document domain service: `web/ogp_web/services/document_service.py` -> `web/ogp_web/repositories/document_repository.py` + `CaseRepository`
  - runtime gates: `web/ogp_web/services/feature_flag_service.py` (`cases_v1`, `documents_v2`)
- Validation retrieval endpoints in `web/ogp_web/routes/validation.py` (`/api/document-versions/{version_id}/validation`, `/api/law-qa-runs/{run_id}/validation`, `/api/validation-runs/{run_id}`):
  - thin route wrappers over `ValidationService` -> `ValidationRepository`
- Document builder endpoint in `web/ogp_web/routes/document_builder.py` (`/api/document-builder/bundle`):
  - bundle assembly path is still coupled to the same complaint/generation-side runtime flow rather than a separate modular backend boundary

**Storage/infrastructure anchor**
- Draft/profile context for complaint generation: `web/ogp_web/storage/user_store.py`
- Generated case/document/version persistence: `web/ogp_web/repositories/case_repository.py`, `web/ogp_web/repositories/document_repository.py`
- Validation persistence: `web/ogp_web/repositories/validation_repository.py`
- Complaint generation snapshot building already resolves server-aware config inputs before persistence via `web/ogp_web/services/complaint_service.py`

**Current migration seam note**
- This slice is partially modularized already: request parsing and payload shaping live in `complaint_service`, while durable case/document/version writes are centralized in `generation_orchestrator`, `case_service`, and `document_service`.
- The route layer still coordinates too many concerns directly: permissions, feature flags, retrieval, citations, validation, metrics, and persistence triggers.
- For migration planning, the safest seam is to keep current request/response contracts stable and continue moving orchestration into dedicated domain services while preserving repository-backed persistence boundaries.
- This slice depends on the auth/profile slice because selected-server and representative profile state materially affect complaint generation inputs.

### Slice 3 - Admin review and configuration operations (`/admin*`, `/api/admin/*`)

**Routes**
- `web/ogp_web/routes/admin.py`
- `web/ogp_web/routes/pages.py`

**Primary dependencies**
- `web/ogp_web/services/admin_dashboard_service.py`
- `web/ogp_web/services/content_workflow_service.py`
- `web/ogp_web/services/law_admin_service.py`
- `web/ogp_web/services/synthetic_runner_service.py`
- `web/ogp_web/services/law_bundle_service.py`
- `web/ogp_web/services/law_version_service.py`
- `web/ogp_web/storage/admin_metrics_store.py`
- `web/ogp_web/storage/admin_catalog_store.py`
- `web/ogp_web/storage/runtime_servers_store.py`
- `web/ogp_web/storage/runtime_law_sets_store.py`
- `web/ogp_web/storage/exam_answers_store.py`
- `web/ogp_web/storage/content_workflow_repository.py`
- `web/ogp_web/storage/admin_dashboard_repository.py`

**Confirmed route -> service -> storage map**
- Admin HTML shells (`/admin`, `/admin/dashboard`, `/admin/users`, `/admin/servers`, `/admin/laws`, `/admin/templates`, `/admin/features`, `/admin/rules`) in `admin.py` are still page-entry wrappers over one broad admin surface.
- Runtime server and runtime law-set endpoints (`/api/admin/runtime-servers*`, `/api/admin/law-sets*`, `/api/admin/runtime-servers/{server_code}/law-bindings`) primarily use `RuntimeServersStore`, `RuntimeLawSetsStore`, and `AdminMetricsStore`.
- Catalog and publication workflow endpoints (`/api/admin/catalog/*`, `/api/admin/change-requests/{id}/review`, rollback/workflow actions) primarily use `ContentWorkflowService` -> `ContentWorkflowRepository`, with legacy fallback context from `AdminCatalogStore` and law-specific publication flows from `LawAdminService`.
- Dashboard/overview/quality/performance endpoints (`/api/admin/dashboard*`, `/api/admin/overview`, `/api/admin/ai-pipeline`, `/api/admin/performance`, `/api/admin/users*`, `/api/admin/role-history`, CSV exports) primarily use `AdminDashboardService` -> `AdminDashboardRepository`, `AdminMetricsStore`, `ExamAnswersStore`, and `SyntheticRunnerService`.
- User moderation endpoints (`/api/admin/users/{username}/*`, bulk actions, task polling) still rely on route-level orchestration plus `UserStore`, `AdminMetricsStore`, and in-memory/file-backed admin task tracking inside `admin.py`.

**Storage/infrastructure anchor**
- Metrics and admin operational telemetry: `web/ogp_web/storage/admin_metrics_store.py`
- Content workflow persistence boundary: `web/ogp_web/storage/content_workflow_repository.py`
- Legacy admin catalog fallback: `web/ogp_web/storage/admin_catalog_store.py`
- Runtime server and law-set persistence: `web/ogp_web/storage/runtime_servers_store.py`, `web/ogp_web/storage/runtime_law_sets_store.py`

**Current migration seam note**
- `admin.py` remains the largest monolithic route surface in the repo and is the clearest current hotspot for Risk 3.
- A stronger modular seam already exists underneath it: dashboard, content workflow, law admin, runtime server, and synthetic runner services are separable bounded contexts even though the route layer still aggregates them in one file.
- For migration planning, admin read surfaces should be split by domain first, while mutation flows continue to preserve current route contracts until service boundaries are tightened further.

### Slice 4 - Exam import processing (`/api/exam-import/*`)

**Routes**
- `web/ogp_web/routes/exam_import.py`

**Primary dependencies**
- `web/ogp_web/services/exam_import_service.py`
- `web/ogp_web/services/exam_import_tasks.py`
- `web/ogp_web/services/exam_sheet_service.py`
- `web/ogp_web/storage/exam_answers_store.py`
- `web/ogp_web/storage/admin_metrics_store.py`
- `shared/ogp_ai.py`

**Confirmed route -> service -> storage map**
- Sync/list/score endpoints in `exam_import.py` use `run_in_threadpool(...)` wrappers around `exam_import_service` and `ExamAnswersStore`.
- Bulk score, failed-row rescore, row score, and task polling depend on `ExamImportTaskRegistry`, `ExamAnswersStore`, `AdminMetricsStore`, and `shared.ogp_ai` scoring helpers with batch and single-item proxy fallback.
- `exam_import_service.py` owns retry policy for invalid batch results through batch retry, single-item retry, stage tracing, and scoring stats aggregation.

**Storage/infrastructure anchor**
- Imported exam rows and score state: `web/ogp_web/storage/exam_answers_store.py`
- Task-state persistence and capacity enforcement: `web/ogp_web/services/exam_import_tasks.py`
- Metrics and failure visibility: `web/ogp_web/storage/admin_metrics_store.py`

**Current migration seam note**
- This slice is already isolated enough to migrate independently, but it carries explicit async/retry risk because threadpool work, task registry state, and AI fallback logic are coordinated across route and service boundaries.
- It is a strong candidate for Phase E stabilization work rather than early runtime-model migration.

### Slice 5 - Exports/attachments lifecycle (`/api/document-versions/*/exports`, `/api/*attachments*`, `/api/jobs*`)

**Routes**
- `web/ogp_web/routes/exports.py`
- `web/ogp_web/routes/attachments.py`
- `web/ogp_web/routes/jobs.py`

**Primary dependencies**
- `web/ogp_web/services/export_service.py`
- `web/ogp_web/services/attachment_service.py`
- `web/ogp_web/services/async_job_service.py`
- `web/ogp_web/services/object_storage_service.py`
- `web/ogp_web/storage/artifact_repository.py`
- `web/ogp_web/storage/case_repository.py`

**Confirmed route -> service -> storage map**
- Export endpoints in `exports.py` use `ExportService`, `ArtifactRepository`, `ObjectStorageService`, and `AsyncJobService` for async export mode.
- Attachment endpoints in `attachments.py` use `AttachmentService`, `ArtifactRepository`, and `ObjectStorageService`.
- Generic job endpoints in `jobs.py` use `AsyncJobService` and `CaseRepository.get_user_id_by_username(...)` for actor resolution, with server-scoped permission checks on reads, retries, and cancellation.
- `AsyncJobService` already defines explicit job statuses, per-job retry policies, idempotency-key generation and deduplication, and a queue-provider publication boundary.

**Storage/infrastructure anchor**
- Artifact persistence boundary: `web/ogp_web/storage/artifact_repository.py`
- Async job persistence boundary: `async_jobs` / `job_attempts` via `web/ogp_web/services/async_job_service.py`
- Blob/object boundary: `web/ogp_web/services/object_storage_service.py`

**Current migration seam note**
- This slice already resembles the target architecture more than the older runtime flows do: artifacts are repository-backed, object storage is behind a service, and async jobs have explicit state transitions and retry semantics.
- The main migration need is operational hardening and consistent visibility in admin/ops surfaces, not a large domain rewrite.

## Hardcoded server-dependent paths (Phase A.1 inventory)

### High risk
- `web/ogp_web/server_config/blackberry.py`
- `web/ogp_web/server_config/packs/blackberry.bootstrap.json`
- `web/ogp_web/server_config/registry.py`
- `web/ogp_web/storage/user_store.py`
- `web/ogp_web/routes/pages.py`
- `web/ogp_web/services/document_builder_bundle_service.py`

Why high risk:
- default server and bootstrap data still assume `blackberry`
- only one bootstrap server pack is first-class in code and migrations
- several entry points still fall back to `"blackberry"` directly instead of resolving fully from versioned config

### Medium risk
- `web/ogp_web/routes/complaint.py`
- `web/ogp_web/services/complaint_service.py`
- `web/ogp_web/services/ai_service.py`
- `web/ogp_web/services/law_admin_service.py`
- `web/ogp_web/routes/admin.py`

Why medium risk:
- these paths are already server-aware through `get_server_config(...)` and related services
- risk is not direct hardcoded branching so much as continued coupling to legacy server config/runtime pack assumptions

### Lower risk / expected guard paths
- server-scope access checks in `cases.py`, `validation.py`, `attachment_service.py`, `export_service.py`, `document_service.py`, `case_service.py`

Why lower risk:
- these checks enforce tenant/server boundaries rather than encode server-specific business rules

## Async operations and retry/error handling locations

- `web/ogp_web/routes/exam_import.py`
  - threadpool wrappers for sync I/O
  - delegated task registry endpoints
- `web/ogp_web/services/exam_import_service.py`
  - batch retry and single-item retry for failed AI scoring
  - failed-row aggregation and metrics logging
- `web/ogp_web/services/exam_import_tasks.py`
  - queued/running/failed/completed task lifecycle and capacity enforcement
- `web/ogp_web/services/async_job_service.py`
  - durable job state machine, idempotency, retries, dead-letter transitions, queue publication
- `web/ogp_web/services/export_service.py`
  - sync vs async export split; async export creation delegates into `AsyncJobService`
- `web/ogp_web/routes/complaint.py`
  - concurrency limiter and retry-after behavior for suggest/law-QA related AI operations
- `web/ogp_web/services/ai_service.py`
  - context-compaction and validation-retry flow for suggest/law-QA generation
- `web/ogp_web/routes/admin.py`
  - in-memory/file-backed task tracking for admin bulk actions and async law rebuild operations

## Reference pilot (Phase A.2)

- Reference server: `blackberry`
- Reference procedure: `complaint`
- Why this pilot:
  - it is the only fully first-class bootstrap server in current repo state
  - it touches the most important migration seams at once: auth/profile selection, server config lookup, complaint generation, validation, citations, case/document persistence, and admin review
  - it is rich enough to validate config-as-data goals without starting with the more volatile exam-import async surface

### Pilot acceptance checklist

- `GET/PUT/PATCH /api/profile*` continues to resolve and persist selected server correctly.
- `GET/PUT/DELETE /api/complaint-draft` remains behavior-compatible for `blackberry`.
- `POST /api/generate` for `document_kind=complaint` produces stable persisted case/document/version output.
- validation reads and citation reads still resolve against the generated document version.
- admin overview and admin catalog/law-source read surfaces can explain the pilot server state without raw internal-only terminology.
- no new scattered `if server == "blackberry"` logic is introduced while migrating the pilot.

### Pilot KPIs and fallback criteria

- KPI 1: route compatibility
  - no contract regressions on auth/profile/complaint endpoints for the pilot scenario
- KPI 2: output drift
  - in shadow mode, complaint output mismatches are logged and classified before any active cutover
- KPI 3: persistence integrity
  - case/document/version rows, validation payloads, and citations remain server-scoped and queryable
- KPI 4: admin observability
  - admin overview can surface pilot release/integrity/validation state without requiring direct DB inspection
- KPI 5: rollback readiness
  - one-flag revert to legacy-only remains available for the pilot scenario until drift is acceptably low

Fallback criteria:
- any unexplained output drift in complaint generation
- broken selected-server persistence
- missing citations/provenance for generated pilot documents
- async export/job instability affecting pilot documents

## Execution Status

- Current active phase: `Phase G`
- Last completed phase: `Phase F`
- Phase G progress:
  - pilot rollout visibility is now exposed in the `admin/dashboard` ops workspace
  - rollout state is derived from `pilot_runtime_adapter_v1` and `pilot_shadow_compare_v1`
  - fallback signals and rollback history are now visible before enabling pilot cutover
  - pilot preflight gating is now documented in `PILOT_ACTIVATION_CHECKLIST.md`
  - the same preflight checklist is rendered inline in the `Pilot rollout` dashboard block
  - `SCALE_OUT_CHECKLIST_TEMPLATE.md` added as the first reusable template for post-pilot server/procedure expansion
  - `LEGACY_DEPRECATION_CANDIDATES.md` added to track which compatibility seams may become removable after observation
  - `PILOT_CUTOVER_REPORT_TEMPLATE.md` added to record pilot rollout decisions, observation windows, and rollback outcomes
  - the `Pilot rollout` block now surfaces operator playbooks for activation, cutover recording, scale-out, and legacy deprecation follow-up
  - `PILOT_OBSERVATION_LOG_TEMPLATE.md` added for repeated observation-window reviews before sign-off
  - the `Pilot rollout` block now includes `Observation guidance` so warning signals, fallback counts, rollback readiness, and review journaling stay visible in one place
  - rollout warning signals now include `severity`, `owner`, and `next action` in the dashboard to support observation-window triage
  - the `Pilot rollout` block now includes an explicit `go / hold / rollback` cutover summary derived from rollout state, warning severity, fallback usage, and rollback history
  - the `Pilot rollout` block now includes a `scale-out readiness` summary so the next migration candidate stays blocked until pilot observation is accepted
  - the `Pilot rollout` block now includes an `observation sign-off` table so pilot cutover criteria are visible as explicit `met / not met` checks
  - the `Pilot rollout` block now includes a human-readable `next candidate recommendation` summary so reuse decisions are visible before a second candidate is chosen
  - the `Pilot rollout` block now includes a `legacy cleanup backlog` table so compatibility-seam removal stays visible and gated after pilot observation
- Phase H start:
  - next work begins with one bounded post-pilot candidate, not broad rollout
  - legacy cleanup should follow the already-published removal gates from the rollout backlog
  - first recommended H.1 candidate is `blackberry + rehab` because it expands only the procedure dimension while keeping the pilot server and rollback surface unchanged
  - `H.1a` is complete at the code/seed level via `REHAB_ROLLOUT_GAP_MAP.md`
  - current H.1b target is runtime verification of effective rehab inventory, validation, and provenance coverage
- Phase F outcome:
  - provenance baseline mapped in `PROVENANCE_SCHEMA.md` for `blackberry + complaint`
  - read-only provenance assembler and API added for `document_version_id`
  - generated document snapshot enriched with provenance payload
  - admin dashboard now includes provenance lookup by both `document version id` and `generated document id`
  - admin dashboard now includes an inline review surface with recent generated documents and `Inspect trace`
  - review context now includes snapshot summary, validation summary, validation issue preview, content preview, citation drilldown, artifact/export summary, and workflow-linkage anchors
  - safe drilldown links now exist for snapshot/validation/citations/exports APIs
- Phase F acceptance:
  - pilot generated output trace is now visible end-to-end in admin review context without DB inspection
  - explainability surface covers config/model/retrieval/validation/artifact context for the pilot complaint flow
- Next phase:
  - `Phase G` observation, stabilization, and rollout checkpointing

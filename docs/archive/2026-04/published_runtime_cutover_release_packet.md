# Published Runtime Cutover Release Packet

## Status
- `law_qa` now requires `published_pack` runtime truth by default.
- `court_claim` now requires `published_pack` runtime truth by default.
- Rollback lever: set `OGP_RELAXED_PUBLISHED_RUNTIME_SECTIONS=law_qa` to temporarily re-allow bootstrap-pack compatibility.
- Rollback lever: set `OGP_RELAXED_PUBLISHED_RUNTIME_SECTIONS=court_claim` to temporarily re-allow bootstrap-pack compatibility for `court_claim`.
- Runtime pack rollback is available through `/api/admin/runtime-servers/{server}/pack-rollback`.
- `/admin/servers` and runtime routes now expose the same migrated runtime truth for `complaint`, `court_claim`, and `law_qa`.
- `/admin/servers/{server}` now also exposes `strict_cutover_candidates`, so operators can see whether a migrated flow is:
  - `not_ready` for strict flip,
  - `ready_to_flip` from compatibility mode,
  - `strict_safe` because live runtime already uses a published-pack path,
  - `strict_active` because strict cutover is already enabled.

## Deploy Checklist
1. Validate the regression packet locally.
2. Ensure the target server has a published runtime pack:
   - check `/api/admin/runtime-servers/{server}/pack-publish-blockers`
   - publish if needed via `/api/admin/runtime-servers/{server}/pack-publish`
3. Confirm `/admin/servers/{server}` shows:
   - `runtime_requirements.status = ready` or `ready_with_compatibility`
   - `strict_cutover_candidates.items[*]` shows `court_claim` as `ready_to_flip` or `strict_safe` before enabling strict cutover for it
   - `law_context.status = ready` for law-backed rollout targets
4. For `court_claim` strict rollout:
   - if `strict_cutover_candidates.items[court_claim].status = ready_to_flip`, deploy with `OGP_STRICT_PUBLISHED_RUNTIME_SECTIONS=court_claim`
   - if the same item is already `strict_safe`, enabling `OGP_STRICT_PUBLISHED_RUNTIME_SECTIONS=court_claim` should be an operational no-op
5. Deploy using the standard GitHub-backed checkout flow from `AGENTS.md`.
6. Verify `curl -sS http://127.0.0.1:8000/health`.
7. Smoke-check:
   - `/law-qa-test`
   - `/api/ai/law-qa-test`
   - `/court-claim-test`
   - `/api/document-builder/bundle?document_type=court_claim`
   - `/api/runtime/sections/law_qa/capability-context`
   - `/api/runtime/sections/court_claim/capability-context`
   - `/api/runtime/servers/{server}/law-context-readiness`

## Rollback Checklist
1. If the issue is isolated to `law_qa` strictness, set `OGP_RELAXED_PUBLISHED_RUNTIME_SECTIONS=law_qa` and redeploy.
2. If the issue is caused by a bad published pack:
   - call `/api/admin/runtime-servers/{server}/pack-rollback`
   - or roll back to a specified previously published version
3. If the issue is isolated to `court_claim` strictness, set `OGP_RELAXED_PUBLISHED_RUNTIME_SECTIONS=court_claim` and redeploy.
4. Re-run:
   - `/api/runtime/sections/law_qa/capability-context`
   - `/api/runtime/sections/court_claim/capability-context`
   - `/api/runtime/servers/{server}/law-context-readiness`
   - `/api/ai/law-qa-test`
   - `/api/document-builder/bundle?document_type=court_claim`
5. If runtime health is still degraded, revert the release commit and redeploy through the standard checkout-based flow.

## Regression Packet
Run:

```bash
python -m pytest tests/test_capability_registry_service.py tests/test_published_runtime_gate_service.py tests/test_section_access_service.py tests/test_section_capability_context_service.py tests/test_runtime_context_api.py tests/test_runtime_pack_reader_service.py tests/test_published_artifact_resolution_service.py tests/test_document_builder_bundle_service.py tests/test_pilot_runtime_adapter.py tests/test_law_context_readiness_service.py tests/test_law_context_runtime_api.py tests/test_admin_runtime_servers_service.py tests/test_admin_runtime_servers_api.py tests/test_runtime_server_packs_store.py tests/test_runtime_server_pack_service.py tests/test_sync_server_bootstrap_pack.py tests/test_migrated_runtime_route_guards.py tests/test_web_pages.py::WebPagesSmokeTests::test_complaint_page_smoke tests/test_web_pages.py::WebPagesSmokeTests::test_court_claim_test_page_preserves_in_development_marker tests/test_web_pages.py::WebPagesSmokeTests::test_law_qa_test_page_renders_sources_panel tests/test_web_api.py::WebApiTests::test_register_verify_login_profile_and_generate_flow tests/test_web_api.py::WebApiTests::test_document_builder_bundle_endpoint tests/test_web_api.py::WebApiTests::test_law_qa_test_endpoint_returns_text_and_sources tests/test_web_api.py::WebApiTests::test_law_qa_test_page_available_for_tester tests/test_web_api.py::WebApiTests::test_law_qa_test_endpoint_forbidden_for_user_without_tester_access tests/test_web_api.py::WebApiTests::test_law_qa_test_endpoint_returns_json_when_unexpected_error_happens -q
```

Expected result: all green.

Focused `court_claim` strict-cutover safety checks:

```bash
python -m pytest tests/test_runtime_context_api.py tests/test_document_builder_bundle_service.py tests/test_published_runtime_gate_service.py -q
python -m pytest tests/test_web_pages.py::WebPagesSmokeTests::test_court_claim_test_page_preserves_in_development_marker tests/test_web_api.py::WebApiTests::test_document_builder_bundle_endpoint tests/test_migrated_runtime_route_guards.py -q
```

These checks should prove both sides of the rollout:
- bootstrap-pack `court_claim` paths are blocked when `OGP_STRICT_PUBLISHED_RUNTIME_SECTIONS=court_claim`
- published-pack `court_claim` paths continue to work under the same strict env

Focused `complaint` strict-cutover safety checks:

```bash
python -m pytest tests/test_runtime_context_api.py tests/test_published_runtime_gate_service.py tests/test_section_capability_context_service.py -q
python -m pytest tests/test_web_pages.py::WebPagesSmokeTests::test_complaint_page_smoke tests/test_web_api.py::WebApiTests::test_register_verify_login_profile_and_generate_flow tests/test_migrated_runtime_route_guards.py -q
```

These checks should prove both sides of the rollout:
- bootstrap-pack `complaint` page/generate paths are blocked when `OGP_STRICT_PUBLISHED_RUNTIME_SECTIONS=complaint`
- published-pack-backed `complaint` page/generate paths continue to work under the same strict env

## Known Transitional Paths
- `complaint` still allows bootstrap-pack compatibility.
- `law_qa` retrieval/activation internals still use the current law runtime stack; this packet only hardens runtime truth/gating.
- Non-migrated routes still use older config/fallback helpers and are out of scope for this rollout.

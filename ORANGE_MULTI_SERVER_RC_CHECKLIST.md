# Orange Multi-Server RC Checklist

Status: production-ready accepted within current RC scope
Date: 2026-04-16

## Candidate

- Server: `orange`
- Procedure scope: `runtime/admin/law/config surfaces only`
- Owner: `platform-ops`
- Planned rollout window: `opened on 2026-04-16T02:47:53Z; accepted after successful live projection pilot on main@3293acf`
- Claimed onboarding state: `production-ready (manual sign-off within current RC scope)`

## Preconditions

1. `blackberry` production flow remains green.
2. `orange` exists as a runtime server candidate with explicit activation state.
3. `orange` resolves through a published/bootstrap-backed pack path, not neutral fallback as the claimed RC evidence path.
4. Admin runtime health for `orange` is explainable and operator-visible.
5. At least one law set and one law binding exist for `orange`.
6. Active law version visibility and rollback remain available for `orange`.
7. Document-builder bundle for `orange` resolves from config-owned metadata.
8. Second-server complaint runtime remains out of scope.

## Activation path

1. Create or confirm the `orange` runtime server record.
2. Keep `orange` inactive until pre-RC validation evidence is complete.
3. Verify `orange` published/bootstrap-backed config path and admin health payload.
4. Verify `orange` law set, bindings, active version evidence, and rollback handle.
5. Activate `orange` explicitly.
6. Run production deploy and smoke verification.
7. Collect rollout evidence and start the observation log.

## Evidence to attach

- Known-good deployed baseline commit: `3293acf`
- Known-good deployed `/health` baseline: `status=ok` from Deploy Production run `24494677193`
- RC transition package PR: `#307` — `https://github.com/12hsrate-hub/lawyer5rp/pull/307`
- RC transition package merged commit: `c1dabbb451170008cedcb622951a14dd113b1908`
- `orange` runtime server health payload: `live projection pilot run 24494653859: active_law_version_id=247, chunk_count=1, summary.is_ready=true, highest_completed_state=rollout-ready, next_required_state=production-ready, resolution_mode=published_pack, uses_transitional_fallback=false; production-ready remains manual/operator-confirmed`
- `orange` document-builder bundle sample: `live enablement snapshot 2026-04-16T02:37:44Z: claim_kind_by_court_type.appeal includes orange_appeal_admin_claim and proves orange-owned metadata`
- `orange` law set / law binding / rollback sample: `live projection pilot run 24494653859: approved projection run_id=1, materialized law_set_id=4, active law_version_id=247, rollback remains available through existing admin law-version flow`
- CI Runtime result: `success` — `https://github.com/12hsrate-hub/lawyer5rp/actions/runs/24487677670`
- UTF-8 check result: `success` — `https://github.com/12hsrate-hub/lawyer5rp/actions/runs/24487677658`
- Deploy Production workflow result: `success` — `https://github.com/12hsrate-hub/lawyer5rp/actions/runs/24494677193`
- Synthetic smoke result: `pass` in Deploy Production run `24494677193`

## Exit criteria

- `orange` is accepted as the first staged multi-server RC candidate, or
- `orange` remains inactive / on hold with a recorded reason, or
- rollout is rolled back with evidence captured below.

## Required evidence block

- claimed_state: `production-ready (manual/operator sign-off)`
- completed_items:
  - `bootstrap-ready` regression evidence recorded via `tests/test_runtime_servers_store.py`, `tests/test_server_config_registry.py`, and `tests/test_admin_runtime_servers_service.py`
  - `workflow-ready` regression evidence recorded via `tests/test_admin_runtime_servers_api.py` and `tests/test_admin_runtime_law_sets_api.py`
  - live orange enablement completed in production: runtime server row created inactive, published pack synced, published law set and binding seeded, active law version generated, and server returned to inactive state
  - admin/runtime visibility confirmed in targeted orange registry/runtime/law/document-builder regression coverage and live production snapshot
  - projection/canonical pilot completed successfully in production via GitHub Actions run `24494653859`
  - active orange runtime now resolves through projection provenance with `law_version_id=247` and `chunk_count=1`
  - known-good production smoke evidence collected for baseline commit `3293acf` via Deploy Production run `24494677193`
  - manual operator sign-off accepted `orange` as a staged multi-server RC candidate
  - manual production-ready sign-off accepted the current `orange` RC scope as operator-safe to continue without an open runtime blocker
- skipped_items_with_justification:
  - second-server complaint runtime is intentionally out of scope for this RC
  - broader multi-server parity beyond the current law/config/runtime/document-builder surfaces is intentionally not claimed by this production-ready sign-off
- rollback_reference: `deactivate orange runtime server and revert to previous known-good main via Deploy Production`
- validation_commands:
  - `python -m pytest tests/test_sync_server_bootstrap_pack.py tests/test_server_config_registry.py tests/test_document_builder_bundle_service.py tests/test_admin_runtime_servers_service.py tests/test_admin_runtime_servers_api.py -q`
  - result: `29 passed in 2.61s` on `main@9b687b2`
  - `python -m pytest tests/test_runtime_servers_store.py tests/test_server_config_registry.py tests/test_document_builder_bundle_service.py tests/test_admin_runtime_servers_service.py tests/test_admin_runtime_servers_api.py tests/test_admin_runtime_law_sets_api.py -q`
  - result: `31 passed in 3.04s` on `main@4b6049e`
  - `python -m pytest tests/test_web_api.py -q -k "selected_server or runtime_servers or document_builder_bundle"`
  - result: `5 passed, 96 deselected in 1.22s` on `main@4b6049e`
  - `gh workflow run "Orange Projection Pilot" --ref main -f server_code=orange -f actor_user_id=1`
  - result: `success` in run `24494653859` on `main@3293acf`
  - `gh workflow run "Deploy Production" --ref main`
  - result: `success` in run `24494677193` on `main@3293acf`

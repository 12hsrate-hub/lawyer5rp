# Orange Multi-Server RC Evidence

Status: accepted staged multi-server RC candidate
Date: 2026-04-16

## Scope

- Candidate server: `orange`
- RC type: `first staged multi-server release candidate`
- In scope:
  - runtime server lifecycle
  - published/bootstrap-backed config resolution
  - admin/runtime visibility
  - law set / law binding / active law version / rollback visibility
  - document-builder config-owned behavior
- Out of scope:
  - second-server complaint runtime
  - `production-ready` auto-proof

## Required proof points

1. `orange` is visible in admin runtime surfaces.
2. `orange` onboarding and health payloads are explicit and operator-readable.
3. `orange` is not claimed through `neutral_fallback` as the RC evidence path.
4. `orange` has law source configuration visibility, at least one law set, and at least one law binding.
5. `orange` has active law version visibility and a known rollback path.
6. `orange` document-builder bundle resolves from server-owned metadata.
7. Runtime server selection remains safe:
   - inactive/unready servers fail safely
   - active `orange` selection succeeds through the shared server-context path

## Rollback reference

- Candidate-specific rollback:
  - deactivate `orange`
  - verify `blackberry` health and runtime server visibility
- Code-wide rollback:
  - redeploy the previous known-good `main` commit `3293acf` via `Deploy Production`

## Validation commands

- `python -m py_compile tests/test_web_api.py tests/test_server_config_registry.py tests/test_document_builder_bundle_service.py tests/test_admin_runtime_servers_service.py tests/test_admin_runtime_servers_api.py tests/test_admin_runtime_law_sets_api.py`
- `python -m pytest tests/test_runtime_servers_store.py tests/test_server_config_registry.py tests/test_document_builder_bundle_service.py tests/test_admin_runtime_servers_service.py tests/test_admin_runtime_servers_api.py tests/test_admin_runtime_law_sets_api.py -q`
- `python -m pytest tests/test_web_api.py -q -k "selected_server or runtime_servers or document_builder_bundle"`

## Current pre-window evidence

- RC branch / PR:
  - PR `#307` — `Open Phase L and add orange RC operator artifacts`
  - https://github.com/12hsrate-hub/lawyer5rp/pull/307
- Merged commit:
  - `c1dabbb451170008cedcb622951a14dd113b1908`
- Orange enablement follow-ups:
  - PR `#312` — `Guard bootstrap pack sync for missing servers`
  - PR `#313` — `Commit published bootstrap pack sync`
- CI Runtime:
  - `success`
  - https://github.com/12hsrate-hub/lawyer5rp/actions/runs/24487677670
- UTF-8 Check:
  - `success`
  - https://github.com/12hsrate-hub/lawyer5rp/actions/runs/24487677658
- Current known-good deployed baseline:
  - commit `3293acf`
  - Deploy Production run `24494677193`
  - https://github.com/12hsrate-hub/lawyer5rp/actions/runs/24494677193
- Baseline production verification from run `24494677193`:
  - `/health`: `status=ok`
  - deploy smoke: `passed`
  - synthetic smoke: `pass`
- Latest local pre-window validation results on `main@4b6049e`:
  - `python -m pytest tests/test_runtime_servers_store.py tests/test_server_config_registry.py tests/test_document_builder_bundle_service.py tests/test_admin_runtime_servers_service.py tests/test_admin_runtime_servers_api.py tests/test_admin_runtime_law_sets_api.py -q`
  - result: `31 passed in 3.04s`
  - `python -m pytest tests/test_web_api.py -q -k "selected_server or runtime_servers or document_builder_bundle"`
  - result: `5 passed, 96 deselected in 1.22s`
- Proven by current regression pack:
  - inactive server selection fails safely
  - active `orange` selection succeeds
  - `orange` published/bootstrap-backed config path is available
  - `orange` law set + binding + active-law visibility + rollback path exist in targeted RC evidence coverage
  - `orange` document-builder bundle is `orange`-owned, not inherited from `blackberry`

## Live enablement snapshot

- Snapshot time:
  - `2026-04-16T05:57:21Z`
- Current production baseline:
  - `/health = status=ok`
- `orange` runtime server:
  - exists
  - `is_active = true`
  - title = `Orange`
- `orange` admin health snapshot:
  - `highest_completed_state = rollout-ready`
  - `next_required_state = production-ready`
  - `resolution_mode = published_pack`
  - `uses_transitional_fallback = false`
- `orange` law runtime state:
  - approved `projection_run_id = 1`
  - materialized `law_set_id = 4`
  - binding count = `2`
  - active `law_version_id = 247`
  - `chunk_count = 1`
  - rollback path remains the existing admin law-version flow
- `orange` document-builder sample:
  - `claim_kind_by_court_type.appeal[0].value = orange_appeal_admin_claim`
  - bundle resolves from orange-owned metadata, not base fallback
- scope confirmation:
  - second-server complaint runtime remains out of scope
 - operator sign-off:
   - `orange` accepted as a staged multi-server RC candidate

## RC rollout evidence

- Projection pilot run:
  - `24494653859`
  - result: `success`
- Deploy Production run for accepted baseline:
  - `24494677193`
- `/health` result for accepted baseline:
  - `status=ok`
- Deploy smoke result for accepted baseline:
  - `passed`
- Synthetic smoke result for accepted baseline:
  - `pass`
- `orange` admin health payload snapshot:
  - live pilot result:
    - `highest_completed_state = rollout-ready`
    - `next_required_state = production-ready`
    - `summary.is_ready = true`
    - `active_law_version_id = 247`
    - `chunk_count = 1`
- `orange` document-builder sample:
  - live pilot reused orange-owned metadata path
  - evidence:
    - `server = orange`
    - `claim_kind_by_court_type.appeal[0].value = orange_appeal_admin_claim`
    - orange-specific document-builder metadata is present
- `orange` law rollback sample:
  - live pilot result:
    - approved projection run `1`
    - materialized `law_set_id = 4`
    - active `law_version_id = 247`
    - rollback path remains explainable through existing admin rollback flow
- Observation window status:
  - technical rollout-ready accepted; remaining `production-ready` evidence is manual/operator-based

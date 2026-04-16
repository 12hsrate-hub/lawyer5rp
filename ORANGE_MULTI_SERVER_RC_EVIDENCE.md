# Orange Multi-Server RC Evidence

Status: pre-window ready  
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
  - redeploy the previous known-good `main` commit `4f3b059` via `Deploy Production`

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
- CI Runtime:
  - `success`
  - https://github.com/12hsrate-hub/lawyer5rp/actions/runs/24487677670
- UTF-8 Check:
  - `success`
  - https://github.com/12hsrate-hub/lawyer5rp/actions/runs/24487677658
- Current known-good deployed baseline:
  - commit `4f3b059`
  - Deploy Production run `24487474591`
  - https://github.com/12hsrate-hub/lawyer5rp/actions/runs/24487474591
- Baseline production verification from run `24487474591`:
  - `/health`: `status=ok`
  - deploy smoke: `passed`
  - synthetic smoke: `pass`
- Latest local pre-window validation results on `main@c1dabbb`:
  - `python -m pytest tests/test_runtime_servers_store.py tests/test_server_config_registry.py tests/test_document_builder_bundle_service.py tests/test_admin_runtime_servers_service.py tests/test_admin_runtime_servers_api.py tests/test_admin_runtime_law_sets_api.py -q`
  - result: `31 passed in 3.03s`
  - `python -m pytest tests/test_web_api.py -q -k "selected_server or runtime_servers or document_builder_bundle"`
  - result: `5 passed, 96 deselected in 1.25s`
- Proven by current regression pack:
  - inactive server selection fails safely
  - active `orange` selection succeeds
  - `orange` published/bootstrap-backed config path is available
  - `orange` law set + binding + active-law visibility + rollback path exist in targeted RC evidence coverage
  - `orange` document-builder bundle is `orange`-owned, not inherited from `blackberry`

## Evidence to fill during RC rollout

- Deploy Production run for RC window:
- `/health` result for RC window:
- Deploy smoke result for RC window:
- Synthetic smoke result for RC window:
- `orange` admin health payload snapshot:
  - paste `/api/admin/runtime-servers/orange/health` payload here after activation
- `orange` document-builder sample:
  - paste a representative `document_builder` payload sample for `orange` here after activation
- `orange` law rollback sample:
  - paste rollback route/service evidence for `orange` here after activation
- Observation window status:
  - link the corresponding checkpoint entries from `ORANGE_MULTI_SERVER_RC_OBSERVATION_LOG.md`

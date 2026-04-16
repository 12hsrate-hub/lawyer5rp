# Orange Multi-Server RC Evidence

Status: draft  
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
  - redeploy the previous known-good `main` commit via `Deploy Production`

## Validation commands

- `python -m py_compile tests/test_web_api.py tests/test_server_config_registry.py tests/test_document_builder_bundle_service.py tests/test_admin_runtime_servers_service.py tests/test_admin_runtime_servers_api.py tests/test_admin_runtime_law_sets_api.py`
- `python -m pytest tests/test_runtime_servers_store.py tests/test_server_config_registry.py tests/test_document_builder_bundle_service.py tests/test_admin_runtime_servers_service.py tests/test_admin_runtime_servers_api.py tests/test_admin_runtime_law_sets_api.py -q`
- `python -m pytest tests/test_web_api.py -q -k "selected_server or runtime_servers or document_builder_bundle"`
- `gh workflow run "Deploy Production" --ref main`

## Evidence to fill during RC rollout

- RC branch / PR:
- Merged commit:
- Deploy Production run:
- `/health` result:
- Deploy smoke result:
- Synthetic smoke result:
- `orange` admin health payload snapshot:
- `orange` document-builder sample:
- `orange` law rollback sample:
- Observation window status:

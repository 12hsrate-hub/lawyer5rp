# Orange Multi-Server RC Checklist

Status: draft  
Date: 2026-04-16

## Candidate

- Server: `orange`
- Procedure scope: `runtime/admin/law/config surfaces only`
- Owner: `platform-ops`
- Planned rollout window: `next controlled production window after final pre-RC validation`
- Claimed onboarding state: `rollout-ready`

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

- Deploy commit:
- `/health` payload:
- `orange` runtime server health payload:
- `orange` document-builder bundle sample:
- `orange` law set / law binding / rollback sample:
- CI Runtime result:
- UTF-8 check result:
- Deploy Production workflow result:
- Synthetic smoke result:

## Exit criteria

- `orange` is accepted as the first staged multi-server RC candidate, or
- `orange` remains inactive / on hold with a recorded reason, or
- rollout is rolled back with evidence captured below.

## Required evidence block

- claimed_state: `rollout-ready`
- completed_items:
  - `bootstrap-ready` evidence recorded
  - `workflow-ready` evidence recorded
  - `rollout-ready` evidence recorded
  - admin/runtime visibility confirmed
  - smoke evidence collected
- skipped_items_with_justification:
  - `production-ready` is intentionally not claimed during first RC; it remains a manual sign-off state
  - second-server complaint runtime is intentionally out of scope for this RC
- rollback_reference: `deactivate orange runtime server and revert to previous known-good main via Deploy Production`
- validation_commands:
  - `python -m pytest tests/test_runtime_servers_store.py tests/test_server_config_registry.py tests/test_document_builder_bundle_service.py tests/test_admin_runtime_servers_service.py tests/test_admin_runtime_servers_api.py tests/test_admin_runtime_law_sets_api.py -q`
  - `python -m pytest tests/test_web_api.py -q -k "selected_server or runtime_servers or document_builder_bundle"`
  - `gh workflow run "Deploy Production" --ref main`

# Orange Multi-Server RC Packet (2026-04-16)

> **Status:** Historical / archived consolidated rollout packet.

This file consolidates the earlier one-off Orange RC root documents into a single archive packet.

## Scope

- Candidate server: `orange`
- Date: `2026-04-16`
- RC type: first staged multi-server release candidate
- In scope:
  - runtime server lifecycle
  - published/bootstrap-backed config resolution
  - admin/runtime visibility
  - law set, law binding, active law version, and rollback visibility
  - document-builder config-owned behavior
- Out of scope:
  - second-server complaint runtime
  - blanket platform-wide production-ready proof

## Final decision

- Decision: `proceed`
- Outcome:
  - `orange` accepted as the first staged multi-server RC candidate
  - `production-ready` accepted within the current RC scope
- Reason:
  - live projection pilot completed successfully
  - active runtime advanced to `law_version_id=247` with `chunk_count=1`
  - rollout-ready health requirements were satisfied
  - manual operator sign-off accepted the current RC scope

## Key evidence

- Known-good deployed baseline commit: `3293acf`
- RC transition package PR: `#307`
- RC transition package merged commit: `c1dabbb451170008cedcb622951a14dd113b1908`
- Projection pilot workflow run: `24494653859` -> `success`
- Deploy Production run: `24494677193` -> `success`
- Accepted `/health` result: `status=ok`
- Synthetic smoke result: `pass`

## Runtime snapshot at acceptance

- `orange` runtime server record: present and active
- `resolution_mode`: `published_pack`
- `uses_transitional_fallback`: `false`
- `highest_completed_state`: `rollout-ready`
- `next_required_state`: `production-ready`
- approved `projection_run_id`: `1`
- materialized `law_set_id`: `4`
- active `law_version_id`: `247`
- `chunk_count`: `1`

## Document-builder and rollback evidence

- orange-owned document-builder metadata confirmed through `orange_appeal_admin_claim`
- rollback remained available through the existing admin law-version flow
- candidate-specific rollback:
  - deactivate `orange`
  - verify `blackberry` health and runtime visibility
- code-wide rollback:
  - redeploy the previous known-good `main` commit via `Deploy Production`

## Observation window summary

- Window start: `2026-04-16T02:47:53Z`
- Final sign-off: `2026-04-16T05:57:21Z`
- Blocking incidents: none
- Noted issue before acceptance:
  - one zero-chunk activation reuse gap was fixed before final acceptance

## Validation commands recorded in the original packet

- `python -m pytest tests/test_sync_server_bootstrap_pack.py tests/test_server_config_registry.py tests/test_document_builder_bundle_service.py tests/test_admin_runtime_servers_service.py tests/test_admin_runtime_servers_api.py -q`
- `python -m pytest tests/test_runtime_servers_store.py tests/test_server_config_registry.py tests/test_document_builder_bundle_service.py tests/test_admin_runtime_servers_service.py tests/test_admin_runtime_servers_api.py tests/test_admin_runtime_law_sets_api.py -q`
- `python -m pytest tests/test_web_api.py -q -k "selected_server or runtime_servers or document_builder_bundle"`
- `gh workflow run "Orange Projection Pilot" --ref main -f server_code=orange -f actor_user_id=1`
- `gh workflow run "Deploy Production" --ref main`

## Follow-up notes

- reusable lesson: projection activation must import canonical parsed runtime snapshot directly and must not reuse zero-chunk activations
- broader multi-server parity outside the current RC surfaces remained intentionally deferred

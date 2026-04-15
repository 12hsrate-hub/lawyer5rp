# REHAB_ROLLOUT_GAP_MAP.md

Status: `H.1 complete; candidate checkpoint accepted`  
Date: `2026-04-15`

## Scope

Compare `blackberry + rehab` against the already-stabilized pilot path `blackberry + complaint`.

Goal:
- identify what is already reusable
- identify what is still missing before a bounded rehab rollout gate can be approved

## What is already aligned

### 1. Same runtime server

- server: `blackberry`
- this preserves:
  - same server config registry
  - same law bundle environment
  - same admin rollout workspace
  - same rollback ownership surface

This is the main reason `rehab` is safer than a second-server candidate.

### 2. Runtime route already exists

Evidence:
- `web/ogp_web/routes/complaint.py`
- `POST /api/generate-rehab`

Current behavior:
- `generate_rehab(...)` already builds a context snapshot
- persists generated output with `document_kind="rehab"`
- logs metrics/events for rehab generation

This means rehab is not a net-new route surface.

### 3. Template binding already exists in bootstrap metadata

Evidence:
- `web/ogp_web/server_config/packs/blackberry.bootstrap.json`

Observed:
- `template_bindings.rehab.template_key = rehab_template_v1`
- `template_bindings.rehab.document_type = rehab`

So the base server pack already knows rehab as a first-class document kind.

### 4. Server UI/runtime language already knows rehab

Evidence:
- `web/ogp_web/server_config/blackberry.py`
- navigation/terminology includes `rehab`

This lowers admin/runtime naming risk for the next candidate.

## Verified inventory and gaps vs complaint pilot

### Verified inventory finding A. Bootstrap rehab binding is present

Verified in `web/ogp_web/server_config/packs/blackberry.bootstrap.json`:

- `template_bindings.rehab.template_key = rehab_template_v1`
- `template_bindings.rehab.document_type = rehab`
- terminology includes rehab as a first-class document type

### Verified inventory finding B. Seeded rehab procedure + template publish path exists

Verified in `scripts/seed_admin_catalog_workflow.py`:

- `procedures` includes `rehab_law_index`
- `templates` includes `rehab_template_v1`
- the seed flow publishes items, not just drafts:
  - create content item
  - create draft version
  - submit for review
  - peer-approve
  - publish

This proves rehab procedure/template inventory exists at the code/seed level, even though the current local shell cannot inspect a live DB without `DATABASE_URL`.

## Current gaps vs complaint pilot

### Gap 1. No rehab adapter-backed runtime path

Current state:
- `web/ogp_web/services/pilot_runtime_adapter.py` is hardcoded to:
  - `PILOT_SERVER_CODE = "blackberry"`
  - `PILOT_PROCEDURE_CODE = "complaint"`
  - complaint-only content keys

Impact:
- complaint has adapter-backed published read support
- rehab still appears to run through legacy/runtime snapshot logic only

Gate implication:
- decision made for H.1:
  - rehab stays on the bounded transitional runtime path
  - no complaint-only pilot adapter extension is required for the H.1 checkpoint
  - parity is satisfied by shared bridge write, validation run, and admin review/provenance surfaces

### Gap 2. Runtime-effective rehab published state is verified and catalog-aligned

Current state:
- bootstrap metadata now contains `rehab_template_v1`
- seed workflow contains published rehab procedure/template items
- H.1c production verification now confirms:
  - `procedures:rehab_law_index` exists and is published
  - `templates:rehab_template_v1` exists and is published
  - `laws:law_sources_manifest` exists and is published
  - `validation_rules:rehab_default` exists and is published
- published server pack version `2` now contains:
  - `template_bindings.rehab.template_key = rehab_template_v1`
  - `validation_profiles.rehab`

Impact:
- config-as-data coverage is now proven for the rehab catalog slice

Gate implication:
- catalog coverage gate is satisfied; next work moves to runtime-path and provenance parity before any rollout change

### H.1b execution status

Status update:
- Runtime verification script added: `scripts/verify_rehab_runtime_catalog.py`
- Local execution remains blocked in this workspace (`DATABASE_URL` not set), but production execution is now complete.
- Production execution context:
  - commit: `1e74a26`
  - runtime root: `/srv/lawyer5rp.ru`
  - command: `./web/.venv/bin/python ./scripts/verify_rehab_runtime_catalog.py --server blackberry --json 1`
- Production execution result: `FAIL`
- Production findings:
  - `procedures:rehab_law_index` is present and published
  - `laws:law_sources_manifest` is present and published
  - `templates:rehab_v1` is missing as a published content item
  - no published rehab validation rule key was found
  - bootstrap `validation_profiles` does not include `rehab`
- Scope used by the verifier:
  - `procedures:rehab_law_index` must be present and published
  - `templates` must include the active rehab template key from pack binding (default `rehab_template_v1`)
  - `laws:law_sources_manifest` must be present and published
  - at least one rehab validation rule key must be present and published:
    - `rehab_default`
    - `rehab_validation`
    - `rehab_rules`
- The verifier also reports whether bootstrap `validation_profiles` contains a `rehab` profile key

### H.1c execution status

Status update:
- bootstrap rehab template binding aligned to `rehab_template_v1`
- bootstrap `validation_profiles.rehab` added
- deploy now runs `scripts/sync_server_bootstrap_pack.py` so published DB pack tracks the bootstrap source
- `scripts/seed_admin_catalog_workflow.py` now publishes `validation_rules:rehab_default`
- Production execution context:
  - commit: `de6bb2f`
  - runtime root: `/srv/lawyer5rp.ru`
  - command: `./web/.venv/bin/python ./scripts/verify_rehab_runtime_catalog.py --server blackberry --json 1`
- Production execution result: `PASS`
- Production findings:
  - `procedures:rehab_law_index` is present and published
  - `templates:rehab_template_v1` is present and published
  - `laws:law_sources_manifest` is present and published
  - `validation_rules:rehab_default` is present and published
  - bootstrap `validation_profiles` includes `rehab`

### Gap 3. Provenance equivalence is not yet explicitly proven for rehab

Current state:
- complaint pilot provenance is explainable end-to-end
- rehab now uses the same bridge write plus admin provenance/review endpoints
- `/api/generate-rehab` now mirrors complaint post-generation validation behavior for `document_version`
- automated API coverage proves rehab-generated documents are readable via:
  - `/api/admin/generated-documents/{id}/provenance`
  - `/api/admin/generated-documents/{id}/review-context`

Impact:
- rehab provenance/readability parity is now acceptable for the bounded H.1 candidate

Gate implication:
- parity proof for the H.1 checkpoint is satisfied

### Gap 4. Validation profile parity is still unclear

Current state:
- bootstrap metadata now contains `validation_profiles.rehab`
- `scripts/seed_admin_catalog_workflow.py` now seeds and publishes `validation_rules:rehab_default`

Impact:
- rehab validation is now explicit at the catalog level, but runtime behavior still needs parity confirmation

Gate implication:
- validation coverage gate is satisfied; remaining work is proving runtime-path/provenance parity

## H.1 rollout gate for `blackberry + rehab`

Before any activation change for rehab, all of the following must be confirmed:

1. pilot `blackberry + complaint` remains out of rollback
2. one rehab runtime path is chosen:
- adapter-backed published reads
- or explicit transitional path with matching rollback visibility
3. rehab has published content coverage for:
- procedure
- template
- validation
- law/runtime linkage
4. rehab output is reviewable through the same admin provenance/review workspace standard
5. rehab rollout remains same-server and single-procedure only

Result:
- `H.1` gate is accepted as a bounded candidate checkpoint
- activation-wide expansion is still out of scope

## H.1a result

`H.1a Rehab inventory verification` is complete at the code/seed level:

- bootstrap rehab binding: verified
- seeded rehab procedure inventory: verified
- seeded rehab template inventory: verified
- rehab-specific validation parity: verified for catalog coverage
- runtime-effective DB state: verified and passing for catalog coverage

## Recommended next executable slice

`H.2 Legacy cleanup wave 1`

Do only this next:
- remove only one already-approved compatibility seam from the legacy cleanup backlog
- keep rollback visibility and admin explainability intact after the cleanup slice
- record the cleanup result back into the rollout backlog and plan

Do not:
- activate rehab rollout
- widen to another server
- couple rehab rollout with legacy cleanup

# REHAB_ROLLOUT_GAP_MAP.md

Status: `H.1 draft`  
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
- `template_bindings.rehab.template_key = rehab_v1`
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

- `template_bindings.rehab.template_key = rehab_v1`
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
- rehab cannot be treated as the next bounded candidate until we decide whether:
  - to extend the current pilot adapter to rehab
  - or to create a second bounded adapter path with the same rollout discipline

### Gap 2. Runtime-effective rehab published state is not yet verified

Current state:
- bootstrap metadata contains `rehab_v1`
- seed workflow contains published rehab procedure/template items
- but H.1 has not yet runtime-verified the effective DB-backed state for:
  - procedure
  - template
  - validation rule/profile
  - law/runtime linkage

Impact:
- config-as-data coverage is not yet proven to match the complaint pilot standard in the running workflow surface

Gate implication:
- we need one runtime audit pass on published rehab content inventory before any rollout change

### H.1b execution status

Status update:
- Runtime verification script added: `scripts/verify_rehab_runtime_catalog.py`
- Execution status: `blocked` in local workspace (`DATABASE_URL` not set in this environment)
- Scope used by the verifier:
  - `procedures:rehab_law_index` must be present and published
  - `templates` must include the active rehab template key from pack binding (default `rehab_template_v1`)
  - `laws:law_sources_manifest` must be present and published
  - at least one rehab validation rule key must be present and published:
    - `rehab_default`
    - `rehab_validation`
    - `rehab_rules`
- The verifier also reports whether bootstrap `validation_profiles` contains a `rehab` profile key

### Gap 3. Provenance equivalence is not yet explicitly proven for rehab

Current state:
- complaint pilot provenance is now explainable end-to-end
- rehab route persists generated output, but no rehab-specific provenance parity checklist is documented yet

Impact:
- rehab may generate documents successfully while still missing some explainability guarantees we now require after Phase F

Gate implication:
- rehab rollout must prove:
  - snapshot summary
  - validation summary
  - export/artifact context
  - provenance/review readability

### Gap 4. Validation profile parity is still unclear

Current state:
- bootstrap metadata explicitly contains `complaint_default`
- no equivalent rehab validation profile is evident in the same bootstrap pack snippet
- `scripts/seed_admin_catalog_workflow.py` seeds generic governance rules, not a rehab-specific validation rule

Impact:
- rehab may still depend on older implicit validation assumptions

Gate implication:
- we need to confirm whether rehab has:
  - explicit published validation rules
  - or only legacy validation behavior

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

## H.1a result

`H.1a Rehab inventory verification` is complete at the code/seed level:

- bootstrap rehab binding: verified
- seeded rehab procedure inventory: verified
- seeded rehab template inventory: verified
- rehab-specific validation parity: not verified
- runtime-effective DB state: not verified

## Recommended next executable slice

`H.1b Rehab runtime catalog verification`

Do only this next:
- inspect current published catalog/admin inventory for rehab on `blackberry` through the running workflow surface or DB-backed admin API
- verify whether rehab currently has:
  - effective published procedure item/version
  - effective published template item/version
  - effective validation rule/profile
  - sufficient provenance fields after generation

Do not:
- activate rehab rollout
- widen to another server
- couple rehab rollout with legacy cleanup

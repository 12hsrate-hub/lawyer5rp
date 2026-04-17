> **Status:** Historical / archived

# DATA_MODEL_DRAFT.md

Status: Phase B complete baseline
Date: 2026-04-14
Scope: pilot only (`blackberry` + `complaint`)

## Purpose
Define the minimal versioned data model needed to move the pilot scenario toward a config-driven runtime without changing route contracts yet.

## Scope guard

This draft is intentionally limited to:
- reference server: `blackberry`
- reference procedure: `complaint`
- read-path foundation only

This draft does not yet attempt to model:
- all servers
- all procedure families
- exam import
- full async operations
- broad admin editability

## Phase B.1 modelling rule

For the pilot, each migrated runtime decision should resolve from one primary versioned source, even if legacy adapters still serve the route layer.

## Minimal versioned entity families

### 1. `server_config_version`
Purpose:
- versioned server-level runtime configuration
- replaces implicit bootstrap/default-server assumptions over time

Pilot-owned fields:
- `id`
- `server_code`
- `version`
- `status`
- `display_name`
- `terminology_json`
- `capabilities_json`
- `navigation_json`
- `feature_flags_json`
- `source_snapshot_json`
- `created_at`
- `published_at`
- `created_by`

Pilot notes:
- initial source can be derived from `blackberry.bootstrap.json` plus current effective server metadata
- should become the parent anchor for pilot procedure/runtime resolution

### 2. `procedure_version`
Purpose:
- versioned definition of one procedure family inside one server
- for pilot, the first procedure is `complaint`

Pilot-owned fields:
- `id`
- `server_config_version_id`
- `procedure_code`
- `version`
- `status`
- `title`
- `document_kind`
- `organizations_json`
- `complaint_bases_json`
- `workflow_json`
- `source_snapshot_json`
- `created_at`
- `published_at`
- `created_by`

Pilot notes:
- owns server-specific complaint bases and procedure-scoped runtime behavior
- should be the first place where `blackberry + complaint` stops depending on scattered config reads

### 3. `form_version`
Purpose:
- versioned semantic form schema for the pilot procedure

Pilot-owned fields:
- `id`
- `procedure_version_id`
- `form_key`
- `version`
- `status`
- `schema_json`
- `normalization_rules_json`
- `legacy_field_map_json`
- `ui_hints_json`
- `created_at`
- `published_at`
- `created_by`

Pilot notes:
- first target is the complaint draft semantic schema already enforced around `normalize_complaint_draft(...)`

### 4. `validation_rule_version`
Purpose:
- versioned validation profile and rule bundle for the pilot procedure

Pilot-owned fields:
- `id`
- `procedure_version_id`
- `rule_set_key`
- `version`
- `status`
- `rules_json`
- `error_messages_json`
- `severity_policy_json`
- `created_at`
- `published_at`
- `created_by`

Pilot notes:
- should absorb complaint-default validation requirements now implicit in server config and shared validation paths

### 5. `template_version`
Purpose:
- versioned document template binding for generated pilot output

Pilot-owned fields:
- `id`
- `procedure_version_id`
- `template_key`
- `document_type`
- `version`
- `status`
- `template_body`
- `render_contract_json`
- `created_at`
- `published_at`
- `created_by`

Pilot notes:
- first pilot target is the complaint template binding currently resolved through legacy config/template identifiers

### 6. `law_set_version`
Purpose:
- versioned legal corpus binding used by the pilot procedure

Pilot-owned fields:
- `id`
- `server_code`
- `law_set_key`
- `version`
- `status`
- `manifest_json`
- `bundle_meta_json`
- `citation_contract_json`
- `created_at`
- `published_at`
- `created_by`

Pilot notes:
- should align with runtime law-set and law-source publication flows already present in admin

### 7. `publication_event`
Purpose:
- audit and publication ledger for all versioned pilot entities

Pilot-owned fields:
- `id`
- `entity_type`
- `entity_id`
- `server_code`
- `action`
- `from_version`
- `to_version`
- `request_id`
- `actor_user_id`
- `summary_json`
- `created_at`

Pilot notes:
- should unify publish/rollback/audit visibility across config entities instead of keeping entity-specific event logic only

## Minimal pilot relationships

- one `server_config_version` -> many `procedure_version`
- one `procedure_version` -> many `form_version`
- one `procedure_version` -> many `validation_rule_version`
- one `procedure_version` -> many `template_version`
- one `server_config_version` -> many `law_set_version`
- any published entity version -> many `publication_event`

## Concrete table sketches

### Physical persistence skeleton for the current repo

Use existing persistence families first:
- `server_packs`
  - physical seed/source for `server_config_version`
- `content_items`
- `content_versions`
- `change_requests`
- `reviews`
- `publish_batches`
- `publish_batch_items`
  - physical skeleton for `procedure_version`, `form_version`, `validation_rule_version`, `template_version`, and publication/audit flow
- `law_versions`
  - physical skeleton for law corpus versioning until a dedicated `law_set_version` family is introduced

### Pilot content identity conventions

| Logical entity | Physical family | `content_type` | `content_key` |
|---|---|---|---|
| `procedure_version` | `content_items/content_versions` | `procedures` | `complaint` |
| `form_version` | `content_items/content_versions` | `forms` | `complaint_form` |
| `validation_rule_version` | `content_items/content_versions` | `validation_rules` | `complaint_default` |
| `template_version` | `content_items/content_versions` | `templates` | `complaint_v1` |
| `law_set_version` bridge | `content_items/content_versions` | `laws` | `law_sources_manifest` |

### Required keys and uniqueness

- `server_packs`
  - unique: `(server_code, version)`
- `content_items`
  - unique identity for pilot entities must be enforced as:
  - `(server_scope='server', server_id='blackberry', content_type, content_key)`
- `content_versions`
  - unique within content item: `(content_item_id, version_number)`
- `publish_batches`
  - append-only batch log; no overwrite semantics
- `publish_batch_items`
  - one published version transition per `(publish_batch_id, content_item_id)`
- `law_versions`
  - append-only by server and source snapshot

### Publish-status rules

- only one `current_published_version_id` per `content_item`
- `draft` versions are editable only through a change request path
- `in_review` change request cannot be published until review resolves to `approved`
- publish action updates:
  - `content_items.current_published_version_id`
  - `content_items.status = 'published'`
  - append `publish_batch`
  - append `publish_batch_item`
- rollback action must create a new publish batch that points back to a previous published version rather than mutating history

## Minimal adapter read order for pilot runtime

For `blackberry + complaint`, runtime resolution should read in this order:

1. `server_packs`
   - resolve effective published server pack
2. `content_items/content_versions`
   - read published `procedures:complaint`
3. `content_items/content_versions`
   - read published `forms:complaint_form`
4. `content_items/content_versions`
   - read published `validation_rules:complaint_default`
5. `content_items/content_versions`
   - read published `templates:complaint_v1`
6. `law_versions` plus law-source manifest
   - resolve active legal bundle fingerprint and published source manifest if present
7. fallback
  - if any required published pilot entity is absent, adapter falls back to the current legacy seed for that entity without surfacing extra hybrid visibility metadata in the runtime snapshot

## B.2 acceptance target for pilot read path

- route contract for `/api/generate` remains unchanged
- adapter can resolve runtime context in three modes:
  - `legacy_adapter_seed`
  - `hybrid_workflow_seed`
  - `content_workflow_published`
- shadow compare can measure mismatch count across core version identifiers before active cutover

## Single-source-of-truth target for pilot

During transition:
- route contracts stay legacy-compatible
- legacy services may still read current server config

Target after B.1/B.2:
- pilot runtime resolution should prefer published versioned entities for:
  - server terminology/capabilities
  - complaint procedure metadata
  - complaint form schema
  - validation profile
  - template binding
  - law-set binding

## Initial mapping from current repo to target entities

- `web/ogp_web/server_config/packs/blackberry.bootstrap.json`
  - seed source for `server_config_version` and part of `procedure_version`
- `web/ogp_web/server_config/blackberry.py`
  - seed source for normalized server/procedure metadata
- `web/ogp_web/services/complaint_draft_schema.py`
  - seed source for `form_version.normalization_rules_json` and `legacy_field_map_json`
- `web/ogp_web/services/complaint_service.py`
  - seed source for current template/law/context resolution expectations
- `web/ogp_web/services/law_admin_service.py`
  - seed source for `law_set_version` publication expectations
- `web/ogp_web/services/content_workflow_service.py`
  - reference shape for publication/audit semantics

## Open design constraints for the next micro-step

- decide whether `procedure_version` should directly reference one published `law_set_version` or only a binding key
- decide whether `template_version` stores raw template body, a template manifest, or both
- decide whether `publication_event` should be generalized from existing content-workflow audit records or remain a parallel table initially
- decide the minimal provenance fields that must be stored on generated pilot document versions as soon as adapter reads begin

## Next micro-step

Translate this entity draft into:
- concrete table sketches
- required unique keys
- publish-status rules
- minimal adapter read order for the pilot scenario

## B.2/B.3 implementation seam started

Current implementation anchor:
- `web/ogp_web/services/pilot_runtime_adapter.py`

What it does now:
- resolves a pilot-scoped runtime context for `blackberry + complaint`
- keeps route contracts unchanged

Current rollout control:
- `pilot_runtime_adapter_v1`
- `pilot_shadow_compare_v1`

Current drift visibility:
- historical shadow-compare metrics plumbing existed during pilot observation
- that compare-only event logging and helper scripts were removed in `Phase H.2` after pilot acceptance

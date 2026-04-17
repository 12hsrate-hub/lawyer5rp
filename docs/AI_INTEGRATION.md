# AI Integration

Status: active  
Date: 2026-04-17

## Purpose

This document is the canonical technical reference for AI integration boundaries, provenance requirements, and traceability for generated outputs.

Operational review cadence, SLOs, and routing policy live in `AI_QUALITY_COST_RUNBOOK_ADMIN.md`. This document covers the implementation-facing contract that those operational controls depend on.

## Scope

Current reference path:

- server: `blackberry`
- procedure/document kind: `complaint`
- trace path:
  - `POST /api/generate`
  - generation snapshot
  - document version
  - validation and citations
  - admin trace surface

## Goal

Every generated document must remain explainable through legal, configuration, and model context without inventing a parallel audit subsystem.

## Current persistence anchors

- `generation_snapshots`
  - request payload
  - result text
  - `context_snapshot_json`
  - `effective_config_snapshot_json`
  - `content_workflow_ref_json`
- `document_versions`
  - generated artifact rows linked through `generation_snapshot_id`
- `retrieval_runs`
  - query text
  - effective law/version snapshot
  - retrieved source fragments
- `law_qa_runs`
  - answer text
  - retrieval linkage
- `document_version_citations`
  - explicit source/version/article references for generated document versions
- `answer_citations`
  - explicit source/version/article references for law-QA answers
- validation records
  - post-generation review and quality-gate history

## Minimum provenance fields

The minimum provenance contract for generated outputs is:

- `server_id`
- `document_kind`
- `generation_timestamp`
- `server_config_version`
- `procedure_version`
- `template_version`
- `law_set_version`
- `law_version_id`
- `retrieval_run_id`
- `citation_ids`
- `model_provider`
- `model_id`
- `prompt_version`

## Canonical storage mapping

### Generation snapshot

Primary row: `generation_snapshots`

- `server_id` -> `generation_snapshots.server_id`
- `document_kind` -> `generation_snapshots.document_kind`
- `generation_timestamp` -> `generation_snapshots.created_at`
- `server_config_version` -> `effective_config_snapshot_json.server_config_version`
- `procedure_version` -> `content_workflow_ref_json.procedure`
- `template_version` -> `content_workflow_ref_json.template`
- `law_set_version` -> `effective_config_snapshot_json.law_set_version`
- `prompt_version` -> `content_workflow_ref_json.prompt_version`
- `model_provider` -> `context_snapshot_json.ai.provider`
- `model_id` -> `context_snapshot_json.ai.model`

Fallbacks may still rely on `context_snapshot_json`, but the target direction is one normalized persisted identifier per versioned dependency.

### Document version

Primary row: `document_versions`

- `document_versions.generation_snapshot_id` -> `generation_snapshots.id`

This is the main bridge for document review and “why was this generated?” trace views.

### Retrieval trace

Primary row: `retrieval_runs`

- `retrieval_run_id` -> `retrieval_runs.id`
- `law_version_id` -> `retrieval_runs.effective_versions_json.law_version_id`
- retrieval fragment ids -> `retrieval_runs.retrieved_sources_json[*]` plus explicit citation rows

### Citation trace

Primary rows:

- `document_version_citations`
- `answer_citations`

Canonical citation fields:

- `citation_ids`
- `source_type`
- `source_id`
- `source_version_id`
- `canonical_ref`

## Canonical read order

For a generated-document trace view:

1. Resolve `document_version`
2. Read linked `generation_snapshot`
3. Read linked citation rows
4. Resolve related `retrieval_run` when available
5. Read validation history for the same `document_version`
6. Present one merged trace object in admin/review surfaces

## Canonical trace object

```json
{
  "document_version_id": 0,
  "server_id": "blackberry",
  "document_kind": "complaint",
  "generation_timestamp": "2026-04-15T00:00:00+00:00",
  "config": {
    "server_config_version": "",
    "procedure_version": "",
    "template_version": "",
    "law_set_version": "",
    "law_version_id": null
  },
  "ai": {
    "provider": "",
    "model_id": "",
    "prompt_version": ""
  },
  "retrieval": {
    "retrieval_run_id": null,
    "citation_ids": []
  },
  "validation": {
    "latest_run_id": null,
    "latest_status": ""
  }
}
```

## Current gaps

- `server_config_version` is not yet normalized everywhere as a single persisted identifier.
- `law_set_version` still partially depends on effective runtime/law-version state.
- `prompt_version` is not yet guaranteed on every generation path.
- Admin/review surfaces do not yet expose the full trace end-to-end for every relevant flow.

## Non-goals

- No separate audit subsystem
- No broad schema redesign outside the bounded trace path
- No full cross-flow provenance unification for exam import or exports yet

## Related active docs

- `AI_QUALITY_COST_RUNBOOK_ADMIN.md` - operational quality, cost, and routing policy
- `FEATURE_FLAGS.md` - rollout flags that guard migration and cutover behavior
- `docs/seams/` - compatibility seam notes for AI and runtime transitions

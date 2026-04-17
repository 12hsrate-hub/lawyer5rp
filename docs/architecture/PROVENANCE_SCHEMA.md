# PROVENANCE_SCHEMA.md

## Scope

This document defines the minimum provenance contract for the reference pilot:

- server: `blackberry`
- procedure/document kind: `complaint`

It is the first `Phase F.1` deliverable and intentionally focuses on the smallest traceable path:

`POST /api/generate` -> generation snapshot -> document version -> validation/citations -> admin trace surface

## Goal

Every pilot-generated document must be explainable through legal, configuration, and model context without inventing a parallel audit system.

## Current persistence anchors

The current codebase already persists most of the required trace fragments:

- `generation_snapshots`
  - request payload
  - result text
  - `context_snapshot_json`
  - `effective_config_snapshot_json`
  - `content_workflow_ref_json`
- `document_versions`
  - generated artifact row linked back through `generation_snapshot_id`
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
  - post-generation review/quality gate history

## Minimum provenance fields

The minimum provenance contract for pilot generated outputs is:

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

### 1. Generation snapshot

Primary row: `generation_snapshots`

Canonical fields:

- `server_id`
  - source: `generation_snapshots.server_id`
- `document_kind`
  - source: `generation_snapshots.document_kind`
- `generation_timestamp`
  - source: `generation_snapshots.created_at`
- `server_config_version`
  - source: `effective_config_snapshot_json.server_config_version`
- `procedure_version`
  - source: `content_workflow_ref_json.procedure`
  - fallback: `context_snapshot_json.content_workflow.procedure`
- `template_version`
  - source: `content_workflow_ref_json.template`
  - fallback: `context_snapshot_json.content_workflow.template`
- `law_set_version`
  - source: `effective_config_snapshot_json.law_set_version`
  - fallback: `context_snapshot_json.effective_versions.law_version_id` until full law-set versioning is stored everywhere
- `prompt_version`
  - source: `content_workflow_ref_json.prompt_version`
  - fallback: `context_snapshot_json.content_workflow.prompt_version`
- `model_provider`
  - source: `context_snapshot_json.ai.provider`
- `model_id`
  - source: `context_snapshot_json.ai.model`

### 2. Document version

Primary row: `document_versions`

Canonical linkage:

- `document_versions.generation_snapshot_id` -> `generation_snapshots.id`

This is the main bridge for "show me why this persisted document looks like this".

### 3. Retrieval trace

Primary row: `retrieval_runs`

Canonical fields:

- `retrieval_run_id`
  - source: `retrieval_runs.id`
- `law_version_id`
  - source: `retrieval_runs.effective_versions_json.law_version_id`
- `retrieval/citation fragment ids`
  - source: `retrieval_runs.retrieved_sources_json[*]`
  - plus explicit persisted citation rows below

### 4. Citation trace

Primary rows:

- `document_version_citations`
- `answer_citations`

Canonical fields:

- `citation_ids`
  - source: citation row ids linked to the generated document version or law-QA run
- legal reference target
  - source: `source_type`, `source_id`, `source_version_id`, `canonical_ref`

For the pilot, these rows are the minimum legal explainability surface.

## Pilot read order

For a pilot complaint document trace view, the read order should be:

1. Resolve `document_version`
2. Read linked `generation_snapshot`
3. Read linked `document_version_citations`
4. If available, resolve related `retrieval_run`
5. Read validation history for the same `document_version`
6. Present merged trace in admin/document review UI

## Canonical pilot trace object

The admin/document-review trace surface should converge on this shape:

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

## Known gaps

These are acceptable for `F.1`, but must be closed before `Phase F` is accepted:

- `server_config_version` is not yet enforced as a single normalized persisted identifier everywhere
- `law_set_version` is partially represented through effective runtime/law-version state rather than one explicit canonical field
- `prompt_version` is not yet guaranteed on every generation path
- document review/admin UI does not yet expose this trace end-to-end

## Non-goals for F.1

- no new full audit subsystem
- no broad schema redesign outside the pilot path
- no cross-flow provenance unification for exam import or exports yet

## Next implementation step

Add a small stored trace read service for the pilot path:

- input: `document_version_id`
- output: canonical pilot trace object assembled from existing persisted rows

# Compatibility Seam Note

- Seam ID: `seam-2026-04-law-source-set-runtime-promotion`
- Area: `law-domain canonical source-of-truth transition`
- Reason this seam exists: the current runtime still bridges between `server_config.law_qa_sources`, optional workflow-backed `law_sources_manifest`, runtime `law_sets`, and imported `law_versions`, while the target model should be `SourceSet -> discovered links -> canonical law documents -> explicit runtime promotion`.
- Current source of truth: server-effective law context is still derived from flat source URLs plus runtime rebuild/import behavior, with `law_sets` and `law_versions` acting as both runtime artifacts and partial ingestion truth.
- Target source of truth: canonical upstream law state should come from workflow-backed reusable `SourceSet` revisions, discovery runs, canonical `LawDocument` identities with URL aliases, and explicit server-to-source-set bindings, while runtime `law_sets`/`law_versions` become projections only.
- What changed in this task: added the first persistence foundation for reusable `source_sets`, immutable `source_set_revisions`, and `server_source_set_bindings` without switching the active runtime law-resolution path away from the legacy flat-source compatibility model.
- Why this was necessary: the repo needed a formal architecture and migration contract for replacing flat per-server law-source handling with a source-set-driven ingestion and promotion model, without silently rewriting the runtime path.
- Rollback path: continue using the existing flat-source compatibility model (`server_config`, `law_sources_manifest`, runtime rebuild/import) until source sets, bindings, discovery, canonical document ingest, and runtime promotion all reach parity for the target servers.
- Removal gate: remove or shrink this seam only after active servers resolve law runtime state from source-set bindings and promoted projections by default, legacy flat source imports are purely migration-only, and admin/runtime surfaces can explain provenance, duplicates, disappearance states, and rollback without referencing flat-source truth.
- Tests covering this seam:
  - future source-set migration parity tests must compare legacy flat-source rebuild output against the new projection path
  - future admin/runtime contract tests must prove provenance, duplicate resolution, disappearance handling, and activation/rollback remain explainable
- Remaining risks:
  - canonical law identity and URL alias/remap behavior do not exist yet in code
  - runtime still depends on flat source URLs and rebuild-side effects
  - disappearance/quarantine/promotion semantics are not yet implemented
  - migration complexity is high because existing servers already rely on legacy flat source flows

# AGENTS.md

## Mission
Work as a senior architect / senior technical planner for this repository.
Your first job for large architecture tasks is to understand the current codebase and produce a concrete migration plan before implementation.

## Default mode
For complex requests:
1. inspect repository structure
2. inspect relevant files
3. identify current architecture and dependencies
4. identify risks and legacy traps
5. create or update `PLANS.md`
6. only after plan approval, propose implementation order

Do not jump into implementation for large migration tasks unless explicitly asked.

## Repository-wide architectural rules
1. Do not expand legacy architecture unless absolutely necessary.
2. Do not introduce new server-specific logic via scattered `if server == ...`.
3. Do not hardcode BB codes, procedures, legal rules, or server differences in enums or ad hoc Python configs if they should live in versioned data/config models.
4. Prefer a modular monolith over premature microservices.
5. Treat visual admin as a first-class product surface, not an afterthought.
6. Treat user-facing terminology and readability as core requirements.
7. Treat draft/publish/rollback/audit as mandatory for all major admin-managed entities.
8. Treat master manifest as export/import and control artifact, not as the main manual editing interface.
9. Prefer staged migration over full rewrite.
10. Preserve working behavior when possible through adapters and phased replacement.

## Product-specific architectural intent
The platform is multi-server and server-aware.
Common logic should be:
- workflow engine
- form handling
- validation framework
- document lifecycle
- generation pipeline
- export
- permissions
- audit
- publication flow

Server-specific content should be configurable:
- procedures
- BB code catalogs
- forms
- validation rules
- templates
- law sets
- terminology
- capabilities

## Required planning perspective
When planning, always separate:
- platform core
- runtime model
- admin model
- publication model
- legal registry
- workflow model
- infrastructure evolution
- legacy transition strategy

## Instructions for migration planning
When producing a plan:
- define phases
- define dependencies
- define risks
- define acceptance criteria
- define artifacts per phase
- define what is read-only first
- define what becomes editable later
- define what must remain compatible with legacy
- define what can be postponed
- define first reference server and first reference procedure
- define order of migration by scenario, not only by files

## UI / Admin requirements
Always optimize for non-technical administrators.
User-facing names must be human-readable.
Avoid exposing raw technical internal terms in user flows unless strictly necessary.

When proposing admin structure, prefer sections like:
- Servers
- Process Types
- BB Codes
- Forms
- Validation Rules
- Document Templates
- Law Sets
- Publications
- Audit
- Users & Permissions

## Documentation requirements
Any planning output should consider 3 documentation layers:
1. user/admin documentation
2. operational documentation
3. developer/technical documentation

Prefer auto-generated or data-derived documentation where possible.

## Technical preferences
Target direction:
- FastAPI-compatible backend evolution
- PostgreSQL as primary database
- Redis for cache / quotas / queue / temp state
- S3-compatible storage for files and exports
- queue/workers for heavy async jobs
- AI provider access via gateway/adapters
- law retrieval and citation traceability

## Things to avoid
- giant rewrite plan with no migration strategy
- vague generic advice
- architecture disconnected from current repo
- assuming all servers share the same legal ontology
- manual daily management through one giant config file
- mixing user-facing naming with internal-only jargon
- putting all admin concerns into one generic admin bucket

## Expected deliverables for major architecture tasks
Primary deliverable:
- `PLANS.md`

Possible secondary deliverables:
- `MIGRATION_MAP.md`
- `DATA_MODEL_DRAFT.md`
- `UI_ADMIN_STRUCTURE.md`
- `LEGACY_RISKS.md`
- `ARCHITECTURE_NOTES.md`

## Definition of good output
A good result is:
- concrete
- staged
- repo-aware
- migration-safe
- admin-first
- readable for humans
- explicit about risks and tradeoffs

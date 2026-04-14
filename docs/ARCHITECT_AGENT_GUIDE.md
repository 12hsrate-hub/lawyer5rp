# ARCHITECT_AGENT_GUIDE.md

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

## Non-negotiable migration risk controls

The following risks are mandatory planning constraints.
They are not optional observations.
Any migration plan is incomplete unless each risk is explicitly addressed in `PLANS.md`.

For each risk below, `PLANS.md` must include:
- why it matters
- where it exists now or is likely to appear
- target architectural rule that prevents it
- mitigation steps
- earliest phase where it must be addressed
- validation / acceptance criteria
- fallback / rollback / containment plan
- whether it is a pre-launch blocker, pre-scale blocker, or later optimization

### Risk 1 — Dual source of truth between legacy logic and new DB-driven workflow
This is a critical migration risk.
Do not allow legacy runtime rules and new configuration-driven runtime rules to coexist as long-term competing sources of truth.

Required planning stance:
- define the future single source of truth per migrated scenario
- define when legacy becomes adapter-only
- define temporary compatibility boundaries
- define detection of behavior drift between old and new paths
- define cutover criteria

Required mitigation expectations:
- feature flags or explicit route/use-case switching
- adapter strategy for legacy endpoints
- comparison or shadow-mode validation where useful
- removal plan for duplicated decision logic

### Risk 2 — Hardcoded server-specific business logic for new servers
Do not solve server differences via scattered conditionals, ad hoc enums, or one-off code branches.

Required planning stance:
- server-specific behavior must move into versioned configuration/data models
- server differences must be represented through server configs, procedures, BB catalogs, forms, rules, templates, law sets, and capabilities
- any unavoidable code-level extension must be explicit, bounded, and justified

Required mitigation expectations:
- prohibit new server-specific hardcoded logic in migration phases
- define review rules for rejecting scattered server conditionals
- define where configuration ends and plugin-style extension begins

### Risk 3 — Frontend admin complexity collapsing into a monolithic admin UI
Do not allow the admin surface to become one giant tightly coupled module.

Required planning stance:
- split admin UI by domain areas
- keep human-readable user flows as a first-class requirement
- distinguish read-only discovery views from later editable tools
- define reusable UI patterns, shared components, and boundaries

Required mitigation expectations:
- separate sections such as Servers, Process Types, BB Codes, Forms, Validation Rules, Templates, Law Sets, Publications, Audit, Users & Permissions
- avoid one mega-page or one mega-module owning the whole admin surface
- define how state, routing, and data-fetching boundaries remain modular

### Risk 4 — Transitional instability of background jobs, imports, exports, retries, and async processing
Migration often destabilizes async behavior before the core product appears broken.

Required planning stance:
- treat jobs, imports, exports, retries, queues, and workers as a dedicated migration concern
- define idempotency expectations
- define status visibility in admin UI
- define failure handling, retry policy, and containment strategy

Required mitigation expectations:
- explicit job states
- retry strategy
- failed-job visibility
- duplicate prevention where needed
- phased migration of exports/imports rather than silent replacement
- operational acceptance criteria before broader rollout

### Risk 5 — Incomplete AI / citation provenance for audit and explainability
Do not leave AI generation, retrieval, or citation behavior without traceability.

Required planning stance:
- every generated output must be attributable to server context, procedure context, law set version, and template/prompt context
- provenance is a product and audit requirement, not an optional enhancement

Required mitigation expectations:
- define minimum provenance fields to persist
- define citation trace storage
- define how provenance is surfaced in admin / audit / document review flows
- define acceptance criteria for explainability

Minimum provenance fields expected in planning:
- server_id
- server configuration version
- procedure version
- template version
- law_set version
- citation / fragment identifiers
- model/provider identifier
- prompt version
- generation timestamp

## Mandatory Risk Register section for PLANS.md

`PLANS.md` must contain a dedicated section named:

## Risk Register and Closure Strategy

That section must include, for each mandatory risk:
- priority
- owner area
- trigger / warning signs
- mitigation
- validation
- closure milestone

Owner area examples:
- backend
- admin UI
- infra
- AI / retrieval
- migration / rollout

## Definition of incomplete plan

A plan is incomplete if any of the following is missing:
- explicit treatment of all 5 mandatory risks
- single-source-of-truth transition strategy
- anti-hardcoding strategy for server differences
- modular admin UI strategy
- async/jobs stabilization strategy
- AI/citation provenance strategy
- acceptance criteria for each major phase
- rollback / containment thinking for risky migrations

If a risk is deferred, the plan must explicitly say:
- why it is deferred
- what boundary keeps the system safe until then
- what milestone closes it later

## Review rule for major planning tasks

For large migration tasks, do not approve a plan that ignores or vaguely mentions the mandatory risks above.
A valid plan must stage them, constrain them, and define how they will be closed.

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
When in doubt, prefer a safer staged migration plan over a cleaner but riskier rewrite-style plan.

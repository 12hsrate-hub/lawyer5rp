# Source Sets to Runtime Promotion Architecture

- Status: Proposed
- Date: 2026-04-16
- Owners: Platform Architecture
- Phase anchor: `post-Phase L / next law-platform architecture track`

## Summary

Текущая law-domain модель привязана к плоским `source_urls`, связанным с сервером. Это делает ingestion слишком хрупким, плохо масштабируемым и слабо объяснимым в audit/runtime контуре.

Новая целевая ось:

1. `SourceSet` как канонический container-level вход.
2. `DiscoveredLawLink` как URL-based discovery result.
3. `LawDocument` как canonical law identity, не жёстко равная URL.
4. `ServerSourceSetBinding` как единственная upstream связь сервера.
5. `Runtime promotion` как явный переход от canonical upstream state к server-effective projections.

Главный принцип: серверы связываются не с отдельными законами, а с глобальными переиспользуемыми source sets через bindings.

## Problem Analysis

### Current architecture problem

Сегодня effective law state складывается из нескольких слоёв, которые плохо различены по роли:

- `server_config.law_qa_sources`
- optional workflow-backed `law_sources_manifest`
- rebuild bundle / import `law_version`
- runtime `law_sets` / `law_set_items`

Это создаёт архитектурные дефекты:

- Сервер связан с набором URL, а не с управляемой source entity.
- Container stage отсутствует: система не различает container URLs и отдельные law URLs.
- Law identity по факту сводится к URL, что ломается при alias/remap.
- Provenance неполный: rebuild виден, но плохо видны discovery results, broken links, remaps и upstream contributor graph.
- Частично битые ссылки и временные fetch/parse ошибки слишком легко влияют на effective runtime state.
- Runtime projections (`law_sets`, `law_versions`) частично выполняют роль upstream source-of-truth, хотя должны быть downstream материализацией.

### Why a local refactor is insufficient

Простая замена `source_urls` на `source_sets` внутри текущих сервисов не решит:

- canonical law identity;
- URL alias/remap support;
- duplicate merge policy;
- disappearance and quarantine policy;
- explicit promotion policy;
- idempotent pipeline guarantees;
- safe migration bridge.

Нужна новая canonical model с controlled compatibility bridge.

## Options Considered

### Option A — Minimal extension over flat sources

Суть:

- добавить `source_sets` и `server_source_set_bindings`;
- хранить container URLs в source set;
- хранить discovery results отдельно;
- дальше схлопывать их в flat URL list и использовать почти текущий rebuild path.

Плюсы:

- дешёвая миграция;
- низкий immediate risk;
- меньше изменений в admin/runtime flows.

Минусы:

- source set остаётся обёрткой над flat URLs;
- provenance и identity остаются слабыми;
- исчезновение и promotion semantics остаются transitional.

### Option B — Canonical Source Set + canonical Law Document + runtime projections

Суть:

- upstream canonical layer:
  - `SourceSet`
  - `SourceSetRevision`
  - `ServerSourceSetBinding`
  - `SourceDiscoveryRun`
  - `DiscoveredLawLink`
  - `LawDocument`
  - `LawDocumentAlias`
  - `LawDocumentVersion`
- downstream runtime layer:
  - server-effective law projection
  - `law_sets`
  - `law_versions`
  - bundle/chunks
- явная promotion model между upstream canonical state и runtime state.

Плюсы:

- правильная ось модели;
- поддержка alias/remap;
- deterministic merge across bindings;
- полная contributor provenance visibility;
- clean stale/quarantine/archive policy;
- explicit promotion/activation model;
- хорошо ложится на `LAW_PLATFORM_RULES.md`.

Минусы:

- больше новых сущностей;
- сложнее migration;
- нужны новые bounded services и compatibility bridge.

### Option C — Event-native ingestion platform

Суть:

- discovery/fetch/parse/materialization как отдельные event-driven subsystems;
- runtime использует только projections;
- orchestration идёт через jobs/events.

Плюсы:

- strongest operational model;
- хорошая observability и retry discipline;
- отлично масштабируется.

Минусы:

- слишком тяжёлый шаг для текущего repo state;
- высокий migration cost;
- избыточен для ближайшего развития платформы.

## Selected Model

Выбран **Option B: canonical Source Set model with runtime projections**.

Это лучший компромисс между:

- архитектурной правильностью;
- audit/provenance требованиями;
- multi-server масштабируемостью;
- возможностью безопасно мигрировать без big-bang rewrite.

## Target Architecture

### Core upstream entities

#### 1. SourceSet

- глобальная переиспользуемая сущность;
- стабильная identity: `source_set_key`;
- хранит только business identity и descriptive metadata;
- не содержит server-specific state.

#### 2. SourceSetRevision

- workflow-backed revision source set;
- payload содержит:
  - `container_urls` (1-2 общие ссылки);
  - extractor/adapter policy;
  - inclusion/exclusion defaults;
  - trust/promotion defaults;
  - revision metadata.

#### 3. ServerSourceSetBinding

- upstream связь сервера с source set;
- содержит:
  - `server_code`
  - `source_set_key`
  - `priority`
  - `is_active`
  - include/exclude controls
  - optional pin/freeze behavior
  - optional promotion/trust override if allowed by policy
- это единственная server-side upstream связь.

#### 4. SourceDiscoveryRun

- idempotent discovery run для published `SourceSetRevision`;
- фиксирует trigger, actor, timestamps, result status, summary.

#### 5. DiscoveredLawLink

- URL-based discovery result;
- хранит:
  - normalized discovered URL
  - source container URL
  - first_seen / last_seen
  - discovery status
  - broken/partial metadata
  - provenance to discovery run and source set revision

#### 6. LawDocument

- canonical law identity;
- не является strictly URL-based;
- identity строится через canonical identity key;
- один `LawDocument` может иметь несколько URL aliases/remaps.

#### 7. LawDocumentAlias

- map raw/normalized URLs к canonical `LawDocument`;
- хранит alias kind:
  - `canonical`
  - `redirect`
  - `mirror`
  - `legacy`
  - `manual_remap`

#### 8. LawDocumentVersion

- fetch/parse результат по canonical law document;
- хранит:
  - fetch status
  - parse status
  - fingerprint/checksum
  - extracted title/body/meta
  - provenance to discovered links/runs
  - actor/job info

### Runtime projection entities

Существующие runtime сущности сохраняются, но меняют роль:

- `law_sets`
- `law_set_items`
- `law_versions`
- bundle/chunks

Новая роль:

- это server-effective runtime projections;
- они больше не считаются canonical upstream truth.

## Architectural Decisions

### 1. Law identity

- `DiscoveredLawLink` остаётся URL-based.
- `LawDocument` использует canonical identity key.
- URL aliases/remaps — first-class.
- Merge, promotion и provenance работают по `LawDocument`, а не по raw URL.

### 2. Server-effective merge rules

Server runtime state строится из всех active `ServerSourceSetBindings`.

Merge rules:

1. binding priority задаёт precedence;
2. если несколько source sets дают один canonical `LawDocument`, winner выбирается детерминированно:
   - explicit pin/freeze;
   - highest active binding priority;
   - latest acceptable upstream version;
   - stable tie-break by `source_set_key` and revision identity;
3. duplicate laws не удаляются silently:
   - winner попадает в effective runtime projection;
   - все contributors остаются видимыми в provenance graph.

### 3. Disappearance and failure policy

- исчезновение law link/document из source set не hard-delete’ит runtime immediately;
- explicit states:
  - `active`
  - `stale`
  - `quarantined`
  - `archived`
- `last_known_good` runtime materialization остаётся доступным, пока replacement/removal policy не выполнена;
- broken fetch/parse не должен сам по себе wipe active runtime state.

### 4. Override boundaries

Server-specific overrides ограничены binding-level controls:

- include
- exclude
- priority
- pin/freeze
- optional trust/promotion override

Shared `SourceSet` нельзя мутировать из server context.

Если серверу нужна уникальность:

- создаётся новый source set;
- либо fork/clone общего source set;
- либо используется binding-level override.

### 5. Pipeline execution guarantees

Discovery, fetch, parse и materialization jobs должны быть:

- idempotent;
- resumable;
- concurrency-safe.

Execution guarantees:

- no overlapping conflicting active run for the same stage/scope unless explicitly allowed;
- lock granularity:
  - discovery lock per source set revision;
  - fetch/parse lock per law document;
  - materialization lock per server;
- repeated request либо возвращает existing run, либо запускает rerun только по явной policy.

### 6. Promotion to runtime

Promotion is explicit.

Supported modes:

- `automatic`
- `manual`
- `hybrid`

Recommended default:

- `hybrid`, manual-biased;
- automatic только для low-risk/no-diff cases;
- manual escalation required for:
  - significant document delta,
  - alias/remap changes,
  - disappearance affecting effective runtime,
  - parse degradation,
  - unresolved duplicate competition.

## Public/API and UI Contract Direction

### New bounded surfaces

Нужны новые административные surface groups:

- source set CRUD / revision / publish;
- server-to-source-set bindings;
- discovery preview / run / history;
- discovered law links list/status;
- law document alias/remap visibility;
- fetch/parse history;
- promotion preview / approve / hold / activate;
- effective runtime law-state inspection.

### Compatibility rules

Сохраняются как compatibility inputs:

- `law_sources_manifest`
- flat `source_urls` preview/save/rebuild
- `server_config.law_qa_sources`

Но их роль меняется:

- они импортируются в новую source-set модель;
- они больше не являются целевой runtime truth.

### Runtime semantics that must stay unchanged

- activation/rollback contracts around `LawVersion`;
- admin explainability of active runtime state;
- rollback audit visibility;
- server-scoped effective runtime state.

## Implementation Plan

### Phase 0 — Architecture framing and seam declaration

- Add compatibility seam note for the current law-domain bridge.
- Link old model to target model explicitly:
  - `server-config / law_sources_manifest / flat source_urls`
  - `source sets canonical -> law links -> law documents -> runtime promotion`
- Use this seam note as the migration guardrail.

### Phase 1 — Canonical upstream persistence model

Add new repositories:

- `SourceSetRepository`
- `SourceDiscoveryRepository`
- `LawDocumentRepository`
- `RuntimePromotionRepository`

Add persistence structures:

- `source_sets`
- `source_set_revisions`
- `server_source_set_bindings`
- `source_discovery_runs`
- `discovered_law_links`
- `law_documents`
- `law_document_aliases`
- `law_document_versions`
- `server_effective_law_projection_runs` or equivalent

### Phase 2 — Stage-separated services

Split the current `LawAdminService` responsibility into bounded services:

1. `SourceSetAdminService`
2. `LawLinkDiscoveryService`
3. `LawDocumentIngestService`
4. `LawRuntimePromotionService`
5. `LawRuntimeActivationService`

This keeps current runtime contracts while separating upstream stages.

### Phase 3 — Merge and disappearance policy

Implement:

- canonical document grouping by `canonical_law_identity_key`;
- winner selection by deterministic merge rules;
- contributor provenance persistence for losers;
- stale/quarantine/archive behavior for disappearances and failures.

### Phase 4 — Promotion policy layer

Introduce explicit promotion policy:

- automatic
- manual
- hybrid

Recommended default:

- `hybrid`, manual-biased.

Promotion output must be:

- a promotion candidate,
- a hold state,
- or an activation-ready projection,

with complete provenance snapshot.

### Phase 5 — Compatibility bridge and migration

Migration is additive and reversible.

Migration bridge:

- existing per-server `law_sources_manifest.source_urls` imports into:
  - one `SourceSet`
  - one `SourceSetRevision`
  - one `ServerSourceSetBinding`
- existing direct law URLs are imported as `legacy_flat` revision mode;
- existing `law_sets` and `law_versions` remain operative while bridge is active.

Migration default:

- create `legacy-<server>-default` source set per existing server when needed;
- import current flat sources;
- create active server binding;
- keep old rebuild path until parity is proven.

### Phase 6 — Admin visibility and operator surfaces

Add bounded admin surfaces for:

- source sets
- bindings
- discovery
- law documents
- promotion
- runtime effective law state

UI/operator visibility must explain:

- all contributing source sets;
- selected winner;
- overridden duplicates;
- stale/quarantined items;
- active runtime projection provenance.

### Phase 7 — Runtime resolution switch

Target runtime resolution chain:

1. resolve active bindings
2. resolve published source set revisions
3. resolve latest successful discovery results
4. resolve latest acceptable law document versions
5. apply duplicate/disappearance rules
6. produce runtime projection candidate
7. promote/activate explicitly
8. serve runtime APIs from active projection

Transitional rule:

- if no source-set binding exists, compatibility bridge may still project from legacy source manifest;
- once migrated, direct `server_config.law_qa_sources` is no longer primary runtime truth.

## Test Plan

### Model/service tests

- source set publish creates immutable auditable revision;
- binding priority resolves duplicates deterministically;
- discovery from 1-2 container URLs yields discovered law links;
- partially broken links produce partial-success runs;
- alias/remap resolves multiple URLs to one canonical law document;
- disappearance marks stale/quarantined instead of hard-removing runtime immediately;
- jobs are idempotent and concurrency-safe.

### Migration/compatibility tests

- legacy flat source import into source set + binding is idempotent;
- migrated server produces explainable runtime state;
- old rebuild path and new projection path can be compared for one pilot server;
- rollback behavior of active `law_version` remains externally unchanged.

### Admin/runtime tests

- admin can inspect source sets and bindings;
- admin can inspect broken discovered links;
- admin can inspect canonical law identity with aliases;
- admin can inspect promotion candidate and winner/losers;
- runtime status shows active projection provenance rather than just flat sources.

## Assumptions and defaults

- Chosen model: canonical `SourceSet + LawDocument + runtime projections`.
- Chosen source set scope: global and reusable.
- Chosen override scope: binding-level only.
- Chosen identity rule: `DiscoveredLawLink` is URL-based; `LawDocument` is canonical-key-based.
- Chosen failure policy: stale/quarantined/archived states, no immediate hard delete.
- Chosen promotion default: `hybrid`, manual-biased.
- Chosen non-goal: second-server complaint runtime and unrelated architecture cleanup stay out of scope.

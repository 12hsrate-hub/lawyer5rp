# Acceptance Checklist

## T01 Baseline Contracts
- [x] Prompt contract defines `factual_only`.
- [x] Prompt contract defines `factual_plus_legal`.
- [x] Global rules forbid adding new facts, dates, documents, numbers, and links.
- [x] Weak-context behavior routes to `factual_only`.
- [x] Retry contract caps retries at 1.
- [x] Quality gates include `factual_integrity`.
- [x] `factual_integrity` gate uses `fallback_factual_only`.

## Acceptance Targets
- [ ] `factual_integrity >= 1.00`
- [ ] `style_contract >= 0.995`
- [ ] `legal_linkage_high_relevance >= 0.85`
- [ ] `retry_rate <= 0.12`
- [ ] `max_cost_uplift <= 0.35`

## Sprint 1 Readiness (Baseline)
- [ ] Login success rate baseline is measured and recorded.
- [ ] `/health` baseline (availability + status code profile) is measured and recorded.
- [ ] Latency baseline is measured and recorded for key endpoints:
  - [ ] `/login`
  - [ ] `/complaint`
  - [ ] `/admin`
  - [ ] `/exam_import`

## Mandatory Regression After Each Sprint
- [ ] Registration/login flow regression completed.
- [ ] Complaint generation regression completed.
- [ ] Admin review regression completed.
- [ ] Exam import regression completed.

## Cutover Rollback Readiness
- [ ] Rollback procedure is documented and validated before cutover.
- [ ] Rollback validity window is fixed as 7 days after release.

## Owners Fixed
- [ ] DB migrations owner assigned.
- [ ] Runtime stores owner assigned.
- [ ] Scripts owner assigned.
- [ ] Tests owner assigned.
- [ ] Release owner assigned.

## Release Checklist by Legal Workflow Stage

### Stage 1 — MVP Foundation
- [ ] Все новые сущности server-scoped или explicit global с documented rationale.
- [ ] Для новых API отсутствует hidden default server.
- [ ] `/api/generate` и `/api/complaint-draft` покрыты compatibility-тестами.
- [ ] `LawVersion`, `TemplateVersion`, `DocumentVersion`, `ValidationRun` не изменяются in-place (append-only подтверждено).

### Stage 2 — Unified Verifier
- [ ] complaint + law QA используют общий verifier и единый decision mode contract.
- [ ] Включён backward-compatible first rollout для schema/API изменений этапа.
- [ ] Для изменённых storage-путей активировано dual-read/dual-write окно.
- [ ] Метрики консистентности dual-read/dual-write зафиксированы до cutover.

### Stage 3 — Feedback Loop
- [ ] Feedback API/UI поддерживает категоризацию (`wrong_fact`, `wrong_law`, `unsupported_inference`, `bad_format`, `other`).
- [ ] Логирование и retention соответствуют policy (masked-by-default, controlled raw access).
- [ ] Legacy compatibility layer остаётся стабильной для внешних интеграций.
- [ ] Перед любыми destructive changes оформлен cutover decision + rollback plan.

### Stage 4 — Multi-Server Expansion
- [ ] Для каждого нового сервера проверены scope-инварианты (нет скрытой global-связанности).
- [ ] Per-server quality/cost monitoring включён и валидирован.
- [ ] Dual-read/dual-write окно завершено и задокументировано перед destructive cleanup.
- [ ] Destructive changes выполнены только после подтверждённой backward-compatible фазы.

## Migration Policy (Release Gate)
- [ ] Любое изменение начинается с backward-compatible first.
- [ ] Destructive schema/API changes запрещены до завершения dual-read/dual-write окна.
- [ ] Перед destructive changes зафиксированы: consistency report, cutover decision, rollback window.

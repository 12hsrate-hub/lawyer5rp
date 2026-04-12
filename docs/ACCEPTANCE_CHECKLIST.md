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

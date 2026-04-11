# Exam Scoring Board

> Обновлять статус после каждого PR.
> Правило: один PR закрывает одну TASK-00X.

## Legend
- [ ] To Do
- [~] In Progress
- [x] Done
- [!] Blocked

---

## To Do

- [ ] **TASK-001** Selective mini-batch retry for invalid batch items  
  **Owner:**  
  **PR:**  
  **Depends on:** none  
  **Acceptance snapshot:** retry_batch before retry_single, stats counters added.

- [ ] **TASK-002** Add stage tracing for scoring flow  
  **Owner:**  
  **PR:**  
  **Depends on:** TASK-001 (recommended)  
  **Acceptance snapshot:** stage trace visible in logs per problematic item.

- [ ] **TASK-003** Compact scoring prompt (versioned)  
  **Owner:**  
  **PR:**  
  **Depends on:** none  
  **Acceptance snapshot:** full/compact switch via env, prompt_version logged.

- [ ] **TASK-004** Prompt/version guardrails and rollback switches  
  **Owner:**  
  **PR:**  
  **Depends on:** TASK-003  
  **Acceptance snapshot:** rollback to full mode without redeploy.

- [ ] **TASK-005** Unit tests for retry policy  
  **Owner:**  
  **PR:**  
  **Depends on:** TASK-001  
  **Acceptance snapshot:** fallback chain covered by tests.

- [x] **TASK-006** Chunking and mapping tests  
  **Owner:**  
  **PR:**  
  **Depends on:** TASK-001  
  **Acceptance snapshot:** no item loss, correct source_row/column mapping.

- [x] **TASK-007** Golden regression dataset scaffold  
  **Owner:**  
  **PR:**  
  **Depends on:** TASK-003 (recommended)  
  **Acceptance snapshot:** baseline drift gates defined in tests/CI.

- [x] **TASK-008** Scoring observability metrics  
  **Owner:**  
  **PR:**  
  **Depends on:** TASK-001, TASK-002  
  **Acceptance snapshot:** metrics exported for retry/invalid/cache/latency.

- [x] **TASK-009** Incident runbook  
  **Owner:**  
  **PR:**  
  **Depends on:** TASK-008  
  **Acceptance snapshot:** clear diagnosis steps and rollback actions.

- [x] **TASK-010** Rollout gates and success KPIs  
  **Owner:**  
  **PR:**  
  **Depends on:** TASK-007, TASK-008, TASK-009  
  **Acceptance snapshot:** documented stop/go thresholds and rollout phases.

---

## In Progress

- [~] _(move active task here)_

Template:
- [~] **TASK-00X** <title>  
  **Owner:** @username  
  **Started:** YYYY-MM-DD  
  **PR:** #  
  **Current step:**  
  **Risks/Blockers:**  

---

## Done

- [x] _(move completed task here with date + PR link)_
- [x] **TASK-006** Chunking and mapping tests  
  **Owner:** @codex  
  **Done at:** 2026-04-12  
  **PR:** pending  
  **Outcome:** Added chunk/mapping regression tests for exam scoring batch keys across chunks and verified no column-loss under mixed key formatting.
- [x] **TASK-007** Golden regression dataset scaffold  
  **Owner:** @codex  
  **Done at:** 2026-04-12  
  **PR:** pending  
  **Outcome:** Added golden baseline fixture and regression-gate tests for exam scoring heuristic behavior to detect drift in CI.
- [x] **TASK-008** Scoring observability metrics  
  **Owner:** @codex  
  **Done at:** 2026-04-12  
  **PR:** pending  
  **Outcome:** Verified and covered exported exam scoring metrics (retry/invalid/cache/latency percentiles) in admin overview and storage tests.
- [x] **TASK-009** Incident runbook  
  **Owner:** @codex  
  **Done at:** 2026-04-12  
  **PR:** pending  
  **Outcome:** Added a focused incident runbook for exam scoring with triage matrix, rollback switches, and recovery checklist.
- [x] **TASK-010** Rollout gates and success KPIs  
  **Owner:** @codex  
  **Done at:** 2026-04-12  
  **PR:** pending  
  **Outcome:** Documented phased rollout gates, hard stop criteria, KPI set, and go/hold/rollback decision template.

Template:
- [x] **TASK-00X** <title>  
  **Owner:** @username  
  **Done at:** YYYY-MM-DD  
  **PR:** #  
  **Outcome:** 1-2 lines (what changed, what improved)

---

## Blocked

- [!] _(move blocked task here)_

Template:
- [!] **TASK-00X** <title>  
  **Owner:** @username  
  **Blocked since:** YYYY-MM-DD  
  **Reason:**  
  **Unblock action:**  
  **Needs decision from:**  

---

## Weekly Review (15 min)

- LLM calls / 1000 items:  
- Tokens / item:  
- invalid_json_rate:  
- retry_single_rate:  
- score_drift_vs_baseline:  
- p95 scoring latency:  
- Top incident this week:  
- Action item for next week:  

---

## Release Gate Checklist (before enabling 100%)

- [ ] Canary 10% passed
- [ ] Canary 50% passed
- [ ] Drift within threshold
- [ ] invalid_json_rate <= threshold
- [ ] retry_single_rate <= threshold
- [ ] Runbook updated
- [ ] Rollback tested

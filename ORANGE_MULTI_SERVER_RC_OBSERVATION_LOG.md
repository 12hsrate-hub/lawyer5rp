# Orange Multi-Server RC Observation Log

Use this during the observation window after `orange` is activated as the first staged multi-server RC candidate.

Status: completed; production-ready accepted within current RC scope
Date: 2026-04-16

## Checkpoint cadence

- Checkpoint 1: `T+0` immediately after deploy / activation
- Checkpoint 2: `T+15m` after first operator verification pass
- Checkpoint 3: `T+2h` after the first normal usage window
- Checkpoint 4: `T+24h` before RC sign-off

## 1. Session metadata

- Date: `2026-04-16`
- Operator: `platform-ops`
- Candidate server: `orange`
- Observation window checkpoint: `Checkpoint 4 / final sign-off`

## 2. Stability checks

- Runtime server state still expected: `yes — orange runtime server record remains present`
- Activation state still expected: `yes — orange remains active with projection-backed runtime state`
- Warning signals count: `0`
- Neutral fallback unexpectedly used: `no`
- Rollback events since previous check: `0`

## 3. Output / config quality

- Runtime health still green: `yes — application /health remains status=ok and runtime health summary is ready`
- Onboarding state still coherent: `yes — rollout-ready, next_required_state=production-ready, resolution_mode=published_pack`
- Document-builder sample still `orange`-owned: `yes — orange_appeal_admin_claim is present`
- Law activation / rollback visibility intact: `yes — projection_run_id=1, law_set_id=4, active_law_version_id=247, chunk_count=1`
- Selected-server switching still safe: `expected yes; no live regression observed at Checkpoint 1`

## 4. Async / operations

- Deploy health remains green: `yes — accepted baseline deploy run 24494677193 is green`
- Synthetic smoke remains green: `yes — pass on deploy run 24494677193`
- New incidents: `none`

## 5. Decision for next checkpoint

- Keep current mode: `yes`
- Escalate investigation: `no`
- Roll back: `no`
- Prepare broader rollout: `not yet; production-ready accepted only for the current RC scope`

## 6. Notes

- Key findings: `orange completed the live projection pilot, active runtime advanced to law_version_id=247 with chunk_count=1, rollout-ready was confirmed, and manual production-ready sign-off was accepted within the current RC scope`
- Follow-up owner: `platform-ops`
- Follow-up deadline: `manual production-ready evidence review when needed`

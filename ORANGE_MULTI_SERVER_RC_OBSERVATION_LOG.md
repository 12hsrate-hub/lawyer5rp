# Orange Multi-Server RC Observation Log

Use this during the observation window after `orange` is activated as the first staged multi-server RC candidate.

Status: pre-window ready  
Date: 2026-04-16

## Checkpoint cadence

- Checkpoint 1: `T+0` immediately after deploy / activation
- Checkpoint 2: `T+15m` after first operator verification pass
- Checkpoint 3: `T+2h` after the first normal usage window
- Checkpoint 4: `T+24h` before RC sign-off

## 1. Session metadata

- Date: `fill per checkpoint`
- Operator: `platform-ops`
- Candidate server: `orange`
- Observation window checkpoint: `Checkpoint 1 / 2 / 3 / 4`

## 2. Stability checks

- Runtime server state still expected:
- Activation state still expected:
- Warning signals count:
- Neutral fallback unexpectedly used:
- Rollback events since previous check:

## 3. Output / config quality

- Runtime health still green:
- Onboarding state still coherent:
- Document-builder sample still `orange`-owned:
- Law activation / rollback visibility intact:
- Selected-server switching still safe:

## 4. Async / operations

- Deploy health remains green:
- Synthetic smoke remains green:
- New incidents:

## 5. Decision for next checkpoint

- Keep current mode:
- Escalate investigation:
- Roll back:
- Prepare broader rollout:

## 6. Notes

- Key findings:
- Follow-up owner:
- Follow-up deadline:

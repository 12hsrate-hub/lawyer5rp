# LEGACY_DEPRECATION_CANDIDATES.md

Status: Phase G observation draft  
Date: 2026-04-15

## Purpose

Track compatibility seams that may become removable after pilot observation and acceptance.

## Current candidates

### 1. Legacy provenance/raw-ref presentation workarounds
- Area: `web/ogp_web/static/pages/admin.js`
- Reason:
  - current UI still normalizes some legacy-shaped snapshot refs on the client side
  - after stable normalized payloads exist, this compatibility formatting can shrink

### 2. Pilot adapter fallback-only visibility paths
- Area: `web/ogp_web/services/pilot_runtime_adapter.py`
- Reason:
  - once pilot cutover is accepted and low-drift remains stable, fallback-only branches may be reducible

### 3. Shadow-compare-only metrics plumbing
- Area:
  - `scripts/report_pilot_drift.py`
  - `scripts/check_pilot_drift.py`
  - `pilot_runtime_shadow_compare` event handling
- Reason:
  - after pilot acceptance, some compare-only plumbing may move from always-on observation into targeted regression tooling

### 4. Legacy-only rollout assumptions in admin copy
- Area: dashboard/admin rollout messaging
- Reason:
  - current wording is intentionally cautious for observation mode
  - after stable activation, some “preflight-only” copy may be simplified

## Removal rule

Do not remove any candidate until:
- pilot observation window is accepted
- rollback path remains documented
- provenance and async visibility remain equivalent or better after cleanup

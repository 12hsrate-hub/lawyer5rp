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

### 2. Legacy-only rollout assumptions in admin copy
- Area: dashboard/admin rollout messaging
- Reason:
  - current wording is intentionally cautious for observation mode
  - after stable activation, some “preflight-only” copy may be simplified

## Removed in Phase H.2

### Shadow-compare-only metrics plumbing
- Removed on production commit `07f302a`
- Removed artifacts:
  - `pilot_runtime_shadow_compare` complaint metrics logging
  - `scripts/report_pilot_drift.py`
  - `scripts/check_pilot_drift.py`
- Outcome:
  - compare-only pilot observation helpers no longer appear in the active cleanup backlog

### Pilot adapter fallback-only visibility paths
- Removed locally during `H.2e` and pending production commit
- Removed artifacts:
  - adapter snapshot `status` markers for published/seeded fallback visibility
  - adapter snapshot `content_item_id` fields that were not used by runtime consumers
- Outcome:
  - pilot adapter keeps published-read resolution and seed fallback behavior without exposing extra visibility-only metadata

## Removal rule

Do not remove any candidate until:
- pilot observation window is accepted
- rollback path remains documented
- provenance and async visibility remain equivalent or better after cleanup

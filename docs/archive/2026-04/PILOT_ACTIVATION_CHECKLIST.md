> **Status:** Historical / archived

# PILOT_ACTIVATION_CHECKLIST.md

Status: Phase G working checklist  
Date: 2026-04-15  
Scope: pilot scenario `blackberry + complaint`

## Purpose

Define the minimum preflight checks before switching the pilot from `legacy_only` or `shadow_compare` to `new_runtime_active`.

## Activation gates

1. Shadow compare has been enabled for the pilot scenario.
2. Rollout warning signals are empty or explicitly reviewed.
3. Fallback-to-legacy events remain low and explainable.
4. Rollback history is visible and the last-known-good path is clear.
5. Provenance review is available in admin UI:
   - generated document review
   - provenance trace
   - validation preview
   - citation drilldown
   - artifact/export summary

## Operator interpretation

- If any gate is unclear, keep the pilot in `legacy_only` or `shadow_compare`.
- Only move to `new_runtime_active` after the rollout owner explicitly accepts the preflight state.
- During the observation window, keep shadow compare enabled.

## Current dashboard mapping

The `Pilot rollout` block in `admin/dashboard` is the operator-facing preflight view for these gates.

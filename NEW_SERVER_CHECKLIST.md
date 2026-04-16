# NEW_SERVER_CHECKLIST.md

A new server is not considered fully onboarded until it reaches the claimed onboarding state.

## Onboarding states

### bootstrap-ready
Required:
- runtime server record exists
- server identity/capabilities are defined
- rollback path for bootstrap activation is defined

### workflow-ready
Required:
- law source configuration exists
- law set / law bindings are defined
- template bindings are defined
- validation rules are defined

### rollout-ready
Required:
- feature flags / rollout defaults are defined
- admin visibility exists
- server workspace path is confirmed in `/admin/servers/{server_code}`
- smoke tests passed

### production-ready
Required:
- docs updated
- rollback path validated for active rollout mode
- no unresolved blockers from earlier states

## Merge gate
- Any task claiming "new server support" must declare the target onboarding state.
- A task is complete only for the claimed state when all required items for that state are satisfied.
- Skipped items must be explicitly justified in the task summary.

## Required evidence block (task summary)
Use this lightweight block when claiming a state:

- claimed_state:
- completed_items:
- skipped_items_with_justification:
- rollback_reference:
- validation_commands:

# EDITABLE_WORKFLOW_CHECKLIST.md

Status: draft  
Date: 2026-04-14  
Phase: `Phase D`

## Purpose

Define the smallest safe editable workflow contract for pilot admin entities before broader mutation UX work expands.

## Pilot scope

- `templates`
- `features`
- `validation_rules`
- workflow-backed `laws` artifacts where applicable

## Minimum lifecycle

1. Create or update draft
2. Validate draft
3. Submit for review
4. Approve or request changes
5. Publish approved version
6. Roll back publish batch if needed

## Current server-side gates

- Draft payload contract is checked on draft creation.
- Change request validation is available before review submission.
- Submit for review is blocked when candidate version no longer satisfies the content contract.
- Publish is blocked unless the change request is approved and the candidate version still validates.
- Existing catalog workflow UI can now trigger draft validation before review submission.
- High-risk entities (`procedures`, `templates`, `validation_rules`) require a second person for approval.

## What this phase still needs next

- validation results surfaced directly in admin UI
- explicit release checklist per publish action
- audit timeline surfaced as a first-class editable-workflow view
- optional two-person review rule for high-risk entities

## Rollback rule

- Rollback happens through publish-batch reversal, not direct version mutation.
- The last known published version remains the recovery target for the current server scope.

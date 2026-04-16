# PUBLISH_RELEASE_CHECKLIST.md

Status: draft  
Date: 2026-04-15  
Phase: `Phase D`

## Purpose

Provide a minimal release checklist for publishing workflow-backed pilot configuration safely.

## Pilot scope

- `templates`
- `features`
- `validation_rules`
- workflow-backed law artifacts used by the pilot runtime

## Pre-publish checklist

1. Draft exists for the intended server scope.
2. `validate draft` returns `ok`.
3. Change request is submitted for review.
4. Review outcome is `approved`.
   - For high-risk entities, the approver must not be the same person who proposed the draft.
5. The affected entity and server scope are confirmed by the operator.
6. Rollback target is known:
   - previous published version or publish batch
7. Audit trail is present for:
   - draft creation
   - review action
   - publish action

## Publish notes

- Publish should happen only from an approved change request.
- Publish is a version switch, not an in-place mutation.
- The publish batch id is the rollback handle.
- After merge to `main`, confirm that the standard `CI Runtime`, `UTF-8 Check`, and `Deploy Production` workflows were created for the merge commit.

## Immediate rollback checklist

1. Capture the failing entity and server scope.
2. Identify the latest successful publish batch before the incident.
3. Run rollback against the affected publish batch.
4. Verify the restored published version.
5. Record the incident note in audit or ops notes.

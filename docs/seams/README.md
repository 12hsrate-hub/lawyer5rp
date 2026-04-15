# Compatibility seam notes index rules

## Location and naming

- Seam notes must live under: `docs/seams/YYYY-MM/<slug>.md`
- `YYYY-MM` uses the task execution month.
- `<slug>` should describe the seam area and change intent, e.g. `runtime-adapter-complaint-shrink.md`.

## Create vs update

- Create a new seam note when a seam is introduced or materially changed for a new task.
- Update an existing seam note when the same seam is being iterated in the same rollout track.
- Keep old seam notes for audit history; do not overwrite unrelated seam history.

## Summary reference requirement

- Any task summary that touches a compatibility seam must include the seam note path.
- The summary must state whether the seam was shrunk, expanded, or unchanged.

# Repository Instructions

## Production deploy target

- Primary GitHub repository: `https://github.com/12hsrate-hub/lawyer5rp`
- Production server: `89.111.153.129`
- Production SSH user: `root`
- Live runtime directory: `/srv/lawyer5rp.ru`
- Deploy checkout directory: `/srv/lawyer5rp-deploy/repo`

## Expected deploy flow

When changes are ready:

1. Validate locally.
2. Commit and push to `origin/main`.
3. Update the deploy checkout on the server:

```bash
git -C /srv/lawyer5rp-deploy/repo fetch origin
git -C /srv/lawyer5rp-deploy/repo checkout main
git -C /srv/lawyer5rp-deploy/repo reset --hard origin/main
```

4. Run:

```bash
bash /srv/lawyer5rp-deploy/repo/scripts/deploy_from_checkout.sh
```

5. Verify:

```bash
curl -sS http://127.0.0.1:8000/health
```

## Important notes

- Do not deploy by copying random local files directly into `/srv/lawyer5rp.ru`.
- Production should be updated from the GitHub-backed checkout in `/srv/lawyer5rp-deploy/repo`.
- Preserve server-only runtime files in `/srv/lawyer5rp.ru/web`:
  - `.env`
  - `.venv/`
  - `data/`
- If GitHub Actions deploy secrets are configured, prefer the workflow in `.github/workflows/deploy-production.yml`.
- If auto-deploy is not configured, use the manual GitHub-to-server flow above.

## Governance references

- `ARCHITECTURE_RULES.md`
- `TESTING_RULES.md`
- `NEW_SERVER_CHECKLIST.md`
- `LAW_PLATFORM_RULES.md`
- `docs/templates/COMPATIBILITY_SEAM_NOTE.md`
- `docs/seams/README.md`

## Instruction priority inside this repository

When repository-local instructions conflict, apply them in this order:

1. Direct task instructions in the current Codex request
2. The nearest scoped `AGENTS.md` in the touched directory
3. Parent `AGENTS.md` files up to the repository root
4. Root-level governance docs referenced from the root `AGENTS.md`
5. Existing project conventions, tests, and code examples

If two rules still conflict:
- prefer the stricter rule that preserves architecture boundaries,
- prefer backward compatibility over convenience,
- prefer multi-server/config-driven direction over legacy shortcuts,
- explicitly report the conflict in the final task summary.

## Definition of Done

A task is not complete until all applicable items below are satisfied.

### Required for every task
- The change respects layer boundaries with a transport-first approach:
  - routes should stay transport-first,
  - do not add new orchestration in routes,
  - when touching legacy route orchestration, prefer extraction into services.
  - services = business logic/orchestration
  - persistence = data access only
- No new ad hoc server-specific business branching was introduced.
- Legitimate permission/ownership/scope guards are allowed when they do not encode server-specific business policy.
- Relevant checks from `TESTING_RULES.md` were run.
- The final task summary states:
  - what changed
  - what checks were run
  - what risks remain

### Required when behavior changes
- User/admin-facing docs or architecture docs were updated if needed.
- Backward compatibility impact was checked and explicitly stated.
- Route/API contracts were preserved or explicitly documented as changed.

### Required when persistence/schema changes
- Migration(s) were added when needed.
- Migration/backfill/rollback implications were documented.
- No hidden schema coupling was introduced.

### Required when rollout risk exists
- Feature flag / staged rollout / compatibility path was considered.
- Rollback path was documented.
- Observability implications were considered.

### Required when touching a compatibility seam
- A `Compatibility Seam Note` was added or updated.
- Any task that touches a compatibility seam must update or attach a Compatibility Seam Note.
- Seam notes must live under `docs/seams/YYYY-MM/<slug>.md`.
- The summary must reference the seam note path.
- The summary explicitly says whether the seam was:
  - shrunk
  - expanded
  - unchanged

### Required when touching multi-server behavior
- `NEW_SERVER_CHECKLIST.md` was respected if onboarding flow changed.
- No new single-server assumption was introduced.

### Required when touching law-domain behavior
- `LAW_PLATFORM_RULES.md` contracts were respected.
- Lifecycle impact on sources / manifests / versions / activation / rollback was checked.

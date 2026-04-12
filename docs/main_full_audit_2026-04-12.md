# Full Main Audit - 2026-04-12

## Scope
- Repository-wide static and operational audit against the current `origin/main`.
- Audit target at refresh time: commit `5459080` (`Add AI KPI cards for wrong_fact/unclear/retry and sync runbooks`).
- Goal: assess whether the current `main` passes baseline repository health gates and identify the highest remaining technical risks.

## Commands executed
1. `git status --short --branch`
2. `git branch --all`
3. `bash scripts/codex_run_checks.sh`
4. repository-wide Python syntax compile (`py_compile`) for all `*.py`
5. `python scripts/check_utf8.py`
6. `git diff --check`
7. `rg -n "TODO|FIXME|XXX|HACK|pass #|noqa|pragma: no cover" web shared tests scripts config`
8. targeted size/risk probe for `web/ogp_web/routes/admin.py`
9. targeted admin API pytest probe:
   - `DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/ogp_test python -m pytest -q tests/test_web_api.py -k "admin_ai_pipeline"`

## Executive summary
- **Audit status: baseline main pass with follow-up risks.**
- **Current baseline checks passed in this environment**:
  - `scripts/codex_run_checks.sh` -> `ok`
  - point3 pytest slice -> `12 passed`
  - repository-wide Python syntax compile -> pass
  - UTF-8 validation -> pass
  - `git diff --check` -> pass
- **The previous dependency blocker is not present in this refreshed audit**; required imports used by the default check path are available in the current environment.
- **Highest remaining code-risk hotspot is still `web/ogp_web/routes/admin.py`** (1,497 lines, 18 broad exception handlers).
- **Highest remaining validation gap is broader admin/API regression coverage**: the targeted `admin_ai_pipeline` pytest probe did not complete within the local 124s timeout, which means the default quality gate still does not give fast confidence on this high-change surface.

## Detailed findings

### 1) Main baseline
- This refresh was executed against the current `origin/main`, not against an older `work`-only checkout.
- The audit therefore reflects the repository state after the recent PostgreSQL-only cleanup, AI pipeline hardening, and admin metric UI updates already merged into `main`.

### 2) Required checks entrypoint (`scripts/codex_run_checks.sh`)
- The script starts correctly and completes successfully in the current environment.
- Current result:
  - Python syntax checks: pass
  - Point3 pytest slice: `12 passed`
  - `git diff --check`: pass
- This is a materially stronger baseline than the earlier constrained-environment snapshot.

### 3) Static integrity checks
- Repository-wide Python syntax compile: **pass**.
- UTF-8 check script: **pass**.
- `git diff --check`: **pass**.
- These checks indicate the repository is structurally clean at the source level.

### 4) Code risk hotspot
- `web/ogp_web/routes/admin.py`:
  - 1,497 lines total
  - 18 broad `except Exception as exc` handlers
- Interpretation:
  - the admin routing layer remains the highest blast-radius area in the repository;
  - broad exception normalization helps keep UI endpoints resilient, but it also increases the chance of masking root-cause specificity and makes regressions harder to triage quickly.

### 5) Testing and observability gap
- The default check path currently gives good baseline confidence for point3 and static integrity, but not for the heavier admin/API surface.
- A targeted local probe for `tests/test_web_api.py -k "admin_ai_pipeline"` did not complete within the local timeout window.
- Practical effect:
  - the highest-change operational surface in the project still lacks a fast, routinely green validation path comparable to the point3 checks;
  - regressions in admin metrics, AI pipeline summaries, or quota handling may still be caught later than ideal.

### 6) TODO / suppression scan
- Repository-wide marker scan did not reveal concentrated `TODO/FIXME/HACK` debt in the core web path.
- Most remaining markers are runtime/test annotations (`pragma: no cover`, `noqa`) or script-level operational handling rather than obvious abandoned work items.

## Recommended remediation plan (priority order)
1. **Add a fast admin/API regression slice**
   - Introduce a bounded, repeatable pytest target for the admin AI pipeline and admin metrics endpoints.
   - Wire that slice into `scripts/codex_run_checks.sh` or an adjacent CI check so admin regressions are caught earlier.

2. **Reduce admin route blast radius**
   - Continue splitting `web/ogp_web/routes/admin.py` into focused modules such as overview, AI pipeline, users/actions, exports, and exam operations.
   - Replace broad exception blocks with narrower exception taxonomy where practical.

3. **Preserve current baseline gates**
   - Keep UTF-8, syntax compile, and diff checks as non-optional merge gates.
   - Keep the point3 checks green before merge and extend the same discipline to the admin/API path.

## Final audit verdict
- **Current `main` passes baseline repository health gates in this environment.**
- **This is not yet a full exhaustive integration verdict** for every operational surface, because broader admin/API regression coverage is still slower and less deterministic than the point3 check path.
- **Top remaining risk**: complexity and exception-heavy logic concentrated in `web/ogp_web/routes/admin.py`.

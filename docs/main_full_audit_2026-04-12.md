# Full Main Audit — 2026-04-12

## Scope
- Repository-wide static and operational audit of the current working branch (`work`).
- Goal: assess baseline health for a "main-ready" state across testability, dependency hygiene, code risk concentration, and repository integrity.

## Commands executed
1. `git status --short --branch`
2. `git branch --all`
3. `bash scripts/codex_run_checks.sh`
4. `python -m pip install -q -r web/requirements_web.txt pyyaml`
5. repository-wide Python syntax compile (`py_compile`) for all `*.py`
6. `python scripts/check_utf8.py`
7. `git diff --check`
8. `rg -n "TODO|FIXME|XXX|HACK|pass #|noqa|pragma: no cover" web shared tests scripts config`
9. targeted size/risk probe for `web/ogp_web/routes/admin.py`

## Executive summary
- **Audit status: partial pass with environment constraints.**
- **Core repository integrity checks passed** (`git diff --check`, UTF-8 validator, Python syntax compile).
- **Primary blocking issue for full test audit:** missing Python packages (`yaml`, `pydantic`) in the execution environment; dependency installation failed due upstream/proxy restriction (`403 Forbidden` while resolving packages).
- **Risk concentration remains high in `web/ogp_web/routes/admin.py`** (1,640 lines, 18 broad exception handlers), which increases regression and observability risk.

## Detailed findings

### 1) Branch / main-readiness baseline
- Current branch is `work`; no local `main` branch is present in this clone.
- Because the local checkout has only `work`, this audit evaluates **main-readiness** rather than a direct `main` branch checkout validation.

### 2) Required checks entrypoint result (`scripts/codex_run_checks.sh`)
- Script starts correctly and runs syntax checks.
- It fails during pytest collection because runtime deps are unavailable:
  - `ModuleNotFoundError: No module named 'yaml'`
  - `ModuleNotFoundError: No module named 'pydantic'`
- This means mandatory automated validation is currently **not reproducible in a clean constrained environment**.

### 3) Dependency installation reliability
- Attempted install command failed due package index/proxy access (`Tunnel connection failed: 403 Forbidden`).
- Practical effect: CI-like or sandboxed environments without pre-baked dependencies cannot complete the expected quality gate workflow.

### 4) Static integrity checks
- Python syntax compile across repository: **pass** (0 compile errors).
- UTF-8 check script: **pass**.
- `git diff --check`: **pass**.

### 5) Code risk hotspots
- `web/ogp_web/routes/admin.py`:
  - 1,640 lines total.
  - 18 broad `except Exception as exc` handlers.
- Interpretation: admin routing layer is a high-change/high-risk zone with substantial error swallowing/normalization surface; this can mask root-cause specificity and complicate production triage.

### 6) Testing/developer-experience gap
- Point3 tests depend on `yaml` imports, but project-level install guidance in `web/requirements_web.txt` does not include developer/test dependencies such as `PyYAML`.
- Result: routine quality checks can fail at collection phase in minimal environments.

## Recommended remediation plan (priority order)
1. **Stabilize reproducible checks**
   - Add a dedicated dev/test requirements file (for example: `requirements_dev.txt`) including `pytest`, `PyYAML`, and any test-only dependencies.
   - Update `scripts/codex_run_checks.sh` to fail fast with a clearer dependency hint when required modules are missing.
2. **Reduce admin route blast radius**
   - Incrementally split `web/ogp_web/routes/admin.py` into focused modules (overview/performance/users/actions/export).
   - Replace broad exception blocks with narrower exception taxonomy where feasible.
3. **Keep integrity checks in merge gate**
   - Preserve UTF-8 and diff checks as non-optional baseline gates.
   - Ensure environment used for mandatory tests includes required package mirrors or offline wheel cache.

## Final audit verdict
- **Not yet "full main pass"** under constrained environments, due to dependency resolution/test execution blockers.
- **Source integrity is good**, but **test reproducibility and admin-surface risk** should be addressed before treating this state as fully main-ready.

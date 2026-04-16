# Compatibility Seam Note

- Seam ID: `seam-2026-04-admin-law-diagnostics-compatibility`
- Area: `admin UI / route policy for /admin/laws`
- Reason this seam exists: `/admin/laws` still exposes low-level law-domain diagnostics, legacy/runtime detail, and compatibility-backed workflow surfaces that remain useful for advanced operators, even though the primary day-to-day admin path has moved to the server-centric workspace at `/admin/servers` and `/admin/servers/{server_code}`.
- Current source of truth: `/admin/servers` and `/admin/servers/{server_code}` are the primary operator workspace for server setup and maintenance; `/admin/laws` remains a secondary compatibility and diagnostics surface only.
- Target source of truth: server-centric tabs should remain the only primary operator path, while any surviving law-centric screens stay explicitly advanced-only until raw diagnostics can be embedded or retired safely.
- What changed in this task: `shrunk`
- Why this was necessary: the repo already moved core operator flows into the server-centric workspace, but `/admin/laws` still risked looking like a second equal admin home. The UI and docs now state more clearly that it is a compatibility seam for diagnostics, not the default workspace for onboarding or day-to-day setup. Secondary global navigation also now prefers `/admin/ops` and `/admin/audit`, which further reduces the chance that operators treat `/admin/laws` as a peer top-level workspace.
- Rollback path: restore the previous `/admin/laws` copy and navigation wording if operators report that the stronger diagnostics-only labeling hides needed compatibility context.
- Removal gate: this seam can shrink further only after raw law diagnostics and compatibility-backed runtime details are either reachable from server-centric diagnostics without regression or proven unnecessary for operators.
- Tests covering this seam:
  - `python -m pytest tests/test_web_pages.py -q`
- Remaining risks:
  - some advanced operators may still enter through `/admin/laws` out of habit
  - raw diagnostics remain visually available, so complete route retirement would still require additional migration work

# TESTING_RULES.md

## Matrix: touched area -> required checks

| Touched area | Required checks |
|---|---|
| docs-only / governance-only (`*.md`, `AGENTS.md`, templates under `docs/`) | presence/consistency checks for required files/sections; no runtime test execution required when no executable behavior changed |
| `routes/*` | relevant API tests; regression tests for changed response contracts; auth/permission tests if access logic changed |
| `services/*` | unit or service-level tests for changed logic; integration/API tests if service behavior affects route contracts |
| `storage/*`, `repositories/*`, `db/*` | persistence tests; migration tests if schema changed; backward compatibility/read-path checks if existing data is affected |
| `services/ai_pipeline/*` | orchestration tests; facade contract tests for `ai_service` compatibility; metrics/retry/context assembly coverage if touched |
| `web/ogp_web/static/*` | frontend syntax/lint checks for touched files; contract/regression checks if payload keys or client-server contract handling changed |
| `scripts/*` | syntax/execution sanity for touched scripts (safe invocation or dry-run where possible); targeted script tests if present |
| `routes/admin.py` or admin helpers | admin API tests; permission tests; changed domain workflow tests if action endpoints changed |
| jobs / async / workers | task lifecycle tests; retry/idempotency tests; status/read-model checks; rollback/cancel behavior if touched |
| `server_config/*` | bootstrap/fallback tests; explicit note explaining why workflow-backed config is not sufficient yet |
| law-domain | source validation tests; publication/workflow tests if manifests change; rebuild/version/rollback tests if law versions change; dependency/status tests if server bindings or source registry logic changes |

## Enforcement rules

- The final summary must list exact commands run and their outcomes.
- For docs-only / governance-only changes, runtime tests may be skipped if there is no executable behavior change.
- If a required check is skipped, the reason must be explicit and tied to environment or scope.
- For compatibility-seam changes, include seam-focused contract/regression coverage in the reported checks.

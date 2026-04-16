# Compatibility Seam Note

- Seam ID: `seam-2026-04-server-config-registry-fallback`
- Area: `web/ogp_web/server_config/registry.py`
- Reason this seam exists: the registry still has to bridge between runtime DB server rows, bootstrap server packs, and a neutral fallback config so that new or partially onboarded servers can be addressed before the full staged onboarding path is complete.
- Current source of truth: `web/ogp_web/server_config/registry.py` resolves runtime-effective server packs and configs by preferring published DB packs, then bootstrap packs, then `_build_fallback_server_config(...)` for DB-only servers.
- Target source of truth: runtime-effective server config should come from an explicitly staged onboarding/runtime pack flow with declared readiness state, leaving bootstrap/fallback behavior as an audited exception rather than a silent runtime bridge.
- What changed in this task: `unchanged`
- Why this was necessary: the fallback seam remains active and multi-server critical, and admin/runtime payloads now surface onboarding state explicitly so DB-only servers are no longer implicitly treated as fully ready even while fallback resolution still exists.
- Rollback path: if onboarding or runtime server resolution regresses, continue resolving through `effective_server_pack(...)` and `_build_server_config_from_pack_or_base(...)` with the existing bootstrap/fallback ordering until readiness-state handling is introduced safely.
- Removal gate: remove or narrow the neutral fallback branch once runtime server onboarding enforces explicit readiness stages, DB-only server rows are no longer treated as runtime-addressable by default, and all active servers resolve through published/bootstrap-backed packs with declared state.
- Tests covering this seam:
  - `python -m pytest tests/test_server_config_registry.py -q`
- Remaining risks:
  - DB-created servers can still resolve to a neutral runtime config before readiness state is explicit
  - the fallback keeps multi-server behavior operational, but production-ready evidence is still not auto-tracked, so admin surfaces can make onboarding explicit without proving the final state automatically

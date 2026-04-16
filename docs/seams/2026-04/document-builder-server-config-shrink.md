# Compatibility Seam Note

- Seam ID: `seam-2026-04-document-builder-server-config`
- Area: `web/ogp_web/services/document_builder_bundle_service.py`
- Reason this seam exists: document builder historically carried a `blackberry`-specific server override blob inside the service because the route contract already depended on a ready-to-serve bundle shape before a governed server-config surface existed for document-builder metadata.
- Current source of truth: `web/ogp_web/server_config/packs/blackberry.bootstrap.json` now owns the `document_builder` metadata consumed through `web/ogp_web/server_config/registry.py::resolve_document_builder_config(...)`.
- Target source of truth: runtime-effective server packs / server-config metadata should remain the only source of server-specific document-builder behavior, with neutral fallback returning no override until a server declares explicit document-builder metadata.
- What changed in this task: `shrunk`
- Why this was necessary: it removes ad hoc `blackberry` business branching from the service layer and makes the server-specific bundle data reviewable under the governed config surface without changing the public route contract.
- Rollback path: if document-builder bundle resolution regresses, temporarily restore the previous hardcoded server override map in `document_builder_bundle_service.py` while keeping the route contract unchanged.
- Removal gate: remove the seam completely once all active server-specific document-builder behavior is sourced only from governed runtime packs and no service-level hardcoded server override fallback remains.
- Tests covering this seam:
  - `python -m pytest tests/test_document_builder_bundle_service.py -q`
  - `python -m pytest tests/test_server_config_registry.py -q`
  - `python -m pytest tests/test_web_api.py -q -k "document_builder_bundle"`
- Remaining risks:
  - the document-type-specific defaults still live in the service layer, so only the server-specific portion was moved in this task
  - servers without document-builder metadata still resolve through the neutral fallback path, which is intentional for compatibility but means the route does not enforce readiness

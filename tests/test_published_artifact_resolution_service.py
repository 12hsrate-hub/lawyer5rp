from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.published_artifact_resolution_service import (
    resolve_section_artifact_specs,
    resolve_section_published_artifacts,
)
from ogp_web.services.runtime_pack_reader_service import RuntimePackSnapshot


class PublishedArtifactResolutionServiceTests(unittest.TestCase):
    def test_resolve_section_artifact_specs_prefers_server_pack_bindings(self):
        specs = resolve_section_artifact_specs(
            section_code="complaint",
            server_pack_metadata={
                "template_bindings": {
                    "complaint": {"template_key": "complaint_orange_v1"},
                },
                "validation_profiles": {
                    "complaint_server_v2": {},
                },
            },
        )

        self.assertEqual(specs["form"], ("forms", "complaint_form"))
        self.assertEqual(specs["template"], ("templates", "complaint_orange_v1"))
        self.assertEqual(specs["validation"], ("validation_rules", "complaint_server_v2"))

    def test_resolve_section_artifact_specs_treats_explicit_empty_pack_bindings_as_missing(self):
        complaint_specs = resolve_section_artifact_specs(
            section_code="complaint",
            server_pack_metadata={
                "template_bindings": {},
                "validation_profiles": {},
            },
        )
        court_claim_specs = resolve_section_artifact_specs(
            section_code="court_claim",
            server_pack_metadata={
                "template_bindings": {},
                "validation_profiles": {},
            },
        )

        self.assertEqual(complaint_specs["form"], ("forms", "complaint_form"))
        self.assertEqual(complaint_specs["template"], ("templates", ""))
        self.assertEqual(complaint_specs["validation"], ("validation_rules", ""))
        self.assertEqual(court_claim_specs["form"], ("forms", "court_claim_form"))
        self.assertEqual(court_claim_specs["template"], ("templates", ""))
        self.assertEqual(court_claim_specs["validation"], ("validation_rules", ""))

    def test_resolve_section_published_artifacts_loads_versions_and_document_builder_overlay(self):
        with patch(
            "ogp_web.services.published_artifact_resolution_service.read_runtime_pack_snapshot",
            return_value=RuntimePackSnapshot(
                server_code="orange",
                pack={"version": 3},
                metadata={
                    "template_bindings": {"court_claim": {"template_key": "court_claim_orange_v1"}},
                    "validation_profiles": {"court_claim_default": {}},
                    "document_builder": {"validators": {"required_fields_by_claim_kind": {"appeal": ["plaintiff_name"]}}},
                },
                resolution_mode="published_pack",
                source_label="published pack",
            ),
        ), patch(
            "ogp_web.storage.content_workflow_repository.ContentWorkflowRepository.get_content_item_by_identity",
            side_effect=[
                {"id": 10, "current_published_version_id": 110},
                {"id": 11, "current_published_version_id": 111},
                {"id": 12, "current_published_version_id": 112},
            ],
        ), patch(
            "ogp_web.storage.content_workflow_repository.ContentWorkflowRepository.get_content_version",
            side_effect=[
                {"id": 110, "version_number": 4, "payload_json": {"form_code": "court_claim_form"}},
                {"id": 111, "version_number": 7, "payload_json": {"template_code": "court_claim_orange_v1"}},
                {"id": 112, "version_number": 2, "payload_json": {"rule_code": "court_claim_default", "ruleset": {"validators": {"required_fields_by_claim_kind": {"appeal": ["closing_request"]}}}}},
            ],
        ):
            payload = resolve_section_published_artifacts(
                backend=object(),
                server_code="orange",
                section_code="court_claim",
            )

        self.assertEqual(payload.server_code, "orange")
        self.assertEqual(payload.pack_version, 3)
        self.assertEqual(payload.pack_resolution_mode, "published_pack")
        self.assertEqual(payload.template.content_key, "court_claim_orange_v1")
        self.assertEqual(payload.template.published_version_id, 111)
        self.assertEqual(payload.validation.version_number, 2)
        self.assertIn("validators", payload.document_builder_overlay)

    def test_resolve_section_published_artifacts_does_not_fallback_when_pack_explicitly_clears_bindings(self):
        with patch(
            "ogp_web.services.published_artifact_resolution_service.read_runtime_pack_snapshot",
            return_value=RuntimePackSnapshot(
                server_code="orange",
                pack={"id": 202, "version": 4},
                metadata={
                    "template_bindings": {},
                    "validation_profiles": {},
                },
                resolution_mode="published_pack",
                source_label="published pack",
            ),
        ), patch(
            "ogp_web.storage.content_workflow_repository.ContentWorkflowRepository.get_content_item_by_identity",
            return_value={"id": 10, "current_published_version_id": 110},
        ) as get_item:
            payload = resolve_section_published_artifacts(
                backend=object(),
                server_code="orange",
                section_code="court_claim",
            )

        self.assertIsNotNone(payload.form)
        self.assertIsNone(payload.template)
        self.assertIsNone(payload.validation)
        self.assertEqual(get_item.call_count, 1)


if __name__ == "__main__":
    unittest.main()

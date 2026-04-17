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

from ogp_web.services.document_builder_bundle_service import build_document_builder_bundle
from ogp_web.services.published_artifact_resolution_service import (
    PublishedArtifactRef,
    SectionPublishedArtifactResolution,
)
from tests.second_server_fixtures import orange_published_pack


class DocumentBuilderBundleServiceTests(unittest.TestCase):
    def test_blackberry_bundle_uses_config_owned_document_builder_metadata(self):
        payload = build_document_builder_bundle(server_id="blackberry", document_type="court_claim")

        self.assertEqual(payload["server"], "blackberry")
        self.assertEqual(payload["template"]["name"], "court_claim_bbcode_v1")
        self.assertIn("supreme", payload["choice_sets"]["claim_kind_by_court_type"])
        self.assertEqual(
            payload["validators"]["required_fields_by_claim_kind"]["__default__"],
            ["plaintiff_name", "defendant_name", "situation_description", "closing_request"],
        )

    def test_unknown_server_keeps_neutral_fallback_without_blackberry_overrides(self):
        payload = build_document_builder_bundle(server_id="orange", document_type="court_claim")

        self.assertEqual(payload["server"], "orange")
        self.assertEqual(payload["choice_sets"]["claim_kind_by_court_type"], {})
        self.assertEqual(payload["validators"]["required_fields_by_claim_kind"], {})

    def test_published_pack_second_server_uses_its_own_document_builder_metadata(self):
        with patch(
            "ogp_web.server_config.registry._load_effective_pack_from_db",
            side_effect=lambda *, server_code, at_timestamp=None: orange_published_pack() if server_code == "orange" else None,
        ):
            payload = build_document_builder_bundle(server_id="orange", document_type="court_claim")

        self.assertEqual(payload["server"], "orange")
        self.assertEqual(payload["template"]["name"], "court_claim_bbcode_v1")
        self.assertEqual(
            payload["choice_sets"]["claim_kind_by_court_type"]["appeal"][0]["value"],
            "orange_appeal_admin_claim",
        )
        self.assertEqual(
            payload["validators"]["required_fields_by_claim_kind"]["__default__"],
            ["plaintiff_name", "situation_description", "closing_request"],
        )

    def test_bundle_applies_published_artifact_resolution_to_template_and_validators(self):
        with patch(
            "ogp_web.services.document_builder_bundle_service.resolve_section_published_artifacts",
            return_value=SectionPublishedArtifactResolution(
                section_code="court_claim",
                server_code="orange",
                pack_version=5,
                pack_resolution_mode="published_pack",
                form=PublishedArtifactRef(
                    artifact_type="forms",
                    content_type="forms",
                    content_key="court_claim_form",
                    source="published_content_workflow",
                    published_version_id=301,
                    version_number=2,
                    payload_json={"form_code": "court_claim_form"},
                    content_item_id=201,
                ),
                template=PublishedArtifactRef(
                    artifact_type="templates",
                    content_type="templates",
                    content_key="court_claim_orange_v1",
                    source="published_content_workflow",
                    published_version_id=302,
                    version_number=4,
                    payload_json={"template_code": "court_claim_orange_v1"},
                    content_item_id=202,
                ),
                validation=PublishedArtifactRef(
                    artifact_type="validation_rules",
                    content_type="validation_rules",
                    content_key="court_claim_default",
                    source="published_content_workflow",
                    published_version_id=303,
                    version_number=3,
                    payload_json={
                        "rule_code": "court_claim_default",
                        "ruleset": {
                            "validators": {
                                "required_fields_by_claim_kind": {
                                    "appeal": ["plaintiff_name", "closing_request"],
                                }
                            }
                        },
                    },
                    content_item_id=203,
                ),
                document_builder_overlay={"choice_sets": {"claim_kind_by_court_type": {"appeal": [{"value": "orange_claim"}]}}},
            ),
        ):
            payload = build_document_builder_bundle(server_id="orange", document_type="court_claim", backend=object())

        self.assertEqual(payload["template"]["name"], "court_claim_orange_v1")
        self.assertEqual(payload["template"]["published_version_id"], 302)
        self.assertEqual(
            payload["validators"]["required_fields_by_claim_kind"]["appeal"],
            ["plaintiff_name", "closing_request"],
        )
        self.assertEqual(
            payload["status"]["artifact_resolution"]["validation"]["content_key"],
            "court_claim_default",
        )

    def test_bundle_keeps_base_template_when_pack_explicitly_clears_published_bindings(self):
        with patch(
            "ogp_web.services.document_builder_bundle_service.resolve_section_published_artifacts",
            return_value=SectionPublishedArtifactResolution(
                section_code="court_claim",
                server_code="orange",
                pack_version=5,
                pack_resolution_mode="published_pack",
                form=PublishedArtifactRef(
                    artifact_type="forms",
                    content_type="forms",
                    content_key="court_claim_form",
                    source="published_content_workflow",
                    published_version_id=301,
                    version_number=2,
                    payload_json={"form_code": "court_claim_form"},
                    content_item_id=201,
                ),
                template=None,
                validation=None,
                document_builder_overlay={},
            ),
        ):
            payload = build_document_builder_bundle(server_id="orange", document_type="court_claim", backend=object())

        self.assertEqual(payload["template"]["name"], "court_claim_bbcode_v1")
        self.assertNotIn("artifact_resolution", payload["status"])


if __name__ == "__main__":
    unittest.main()

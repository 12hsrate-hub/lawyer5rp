from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from fastapi import HTTPException

from ogp_web.services.capability_registry_service import get_capability_definition
from ogp_web.services.published_runtime_gate_service import (
    ensure_published_runtime_requirement,
    resolve_published_runtime_requirement,
)


class PublishedRuntimeGateServiceTests(unittest.TestCase):
    def test_published_pack_requirement_is_ready_for_published_pack(self):
        verdict = resolve_published_runtime_requirement(
            capability=get_capability_definition("court_claim"),
            runtime_resolution_snapshot={
                "resolution_mode": "published_pack",
                "requires_explicit_runtime_pack": False,
                "has_published_pack": True,
                "is_runtime_addressable": True,
                "uses_transitional_fallback": False,
            },
        )

        self.assertTrue(verdict.is_ready)
        self.assertFalse(verdict.compatibility_mode)
        self.assertEqual(verdict.reason_code, "published_pack_ready")

    def test_published_pack_requirement_allows_bootstrap_compatibility(self):
        verdict = resolve_published_runtime_requirement(
            capability=get_capability_definition("complaint"),
            runtime_resolution_snapshot={
                "resolution_mode": "bootstrap_pack",
                "requires_explicit_runtime_pack": False,
                "has_published_pack": False,
                "is_runtime_addressable": True,
                "uses_transitional_fallback": True,
            },
        )

        self.assertTrue(verdict.is_ready)
        self.assertTrue(verdict.compatibility_mode)
        self.assertEqual(verdict.reason_code, "bootstrap_pack_compatibility")
        self.assertEqual(verdict.bootstrap_compatibility_policy, "staged")
        self.assertFalse(verdict.strict_cutover_enabled)

    def test_strict_cutover_env_can_block_complaint_bootstrap_compatibility(self):
        with patch.dict(os.environ, {"OGP_STRICT_PUBLISHED_RUNTIME_SECTIONS": "complaint"}, clear=False):
            verdict = resolve_published_runtime_requirement(
                capability=get_capability_definition("complaint"),
                runtime_resolution_snapshot={
                    "resolution_mode": "bootstrap_pack",
                    "requires_explicit_runtime_pack": False,
                    "has_published_pack": False,
                    "is_runtime_addressable": True,
                    "uses_transitional_fallback": True,
                },
            )

        self.assertFalse(verdict.is_ready)
        self.assertFalse(verdict.compatibility_mode)
        self.assertTrue(verdict.strict_cutover_enabled)
        self.assertEqual(verdict.reason_code, "published_pack_cutover_required")

    def test_default_strict_cutover_blocks_court_claim_bootstrap_compatibility(self):
        verdict = resolve_published_runtime_requirement(
            capability=get_capability_definition("court_claim"),
            runtime_resolution_snapshot={
                "resolution_mode": "bootstrap_pack",
                "requires_explicit_runtime_pack": False,
                "has_published_pack": False,
                "is_runtime_addressable": True,
                "uses_transitional_fallback": True,
            },
        )

        self.assertFalse(verdict.is_ready)
        self.assertFalse(verdict.compatibility_mode)
        self.assertTrue(verdict.strict_cutover_enabled)
        self.assertEqual(verdict.reason_code, "published_pack_cutover_required")

    def test_relaxed_cutover_env_can_temporarily_allow_court_claim_bootstrap_compatibility(self):
        with patch.dict(os.environ, {"OGP_RELAXED_PUBLISHED_RUNTIME_SECTIONS": "court_claim"}, clear=False):
            verdict = resolve_published_runtime_requirement(
                capability=get_capability_definition("court_claim"),
                runtime_resolution_snapshot={
                    "resolution_mode": "bootstrap_pack",
                    "requires_explicit_runtime_pack": False,
                    "has_published_pack": False,
                    "is_runtime_addressable": True,
                    "uses_transitional_fallback": True,
                },
            )

        self.assertTrue(verdict.is_ready)
        self.assertTrue(verdict.compatibility_mode)
        self.assertFalse(verdict.strict_cutover_enabled)
        self.assertEqual(verdict.reason_code, "bootstrap_pack_compatibility")

    def test_default_strict_cutover_blocks_law_qa_bootstrap_compatibility(self):
        verdict = resolve_published_runtime_requirement(
            capability=get_capability_definition("law_qa"),
            runtime_resolution_snapshot={
                "resolution_mode": "bootstrap_pack",
                "requires_explicit_runtime_pack": False,
                "has_published_pack": False,
                "is_runtime_addressable": True,
                "uses_transitional_fallback": True,
            },
        )

        self.assertFalse(verdict.is_ready)
        self.assertFalse(verdict.compatibility_mode)
        self.assertTrue(verdict.strict_cutover_enabled)
        self.assertEqual(verdict.reason_code, "published_pack_cutover_required")

    def test_relaxed_cutover_env_can_temporarily_allow_law_qa_bootstrap_compatibility(self):
        with patch.dict(os.environ, {"OGP_RELAXED_PUBLISHED_RUNTIME_SECTIONS": "law_qa"}, clear=False):
            verdict = resolve_published_runtime_requirement(
                capability=get_capability_definition("law_qa"),
                runtime_resolution_snapshot={
                    "resolution_mode": "bootstrap_pack",
                    "requires_explicit_runtime_pack": False,
                    "has_published_pack": False,
                    "is_runtime_addressable": True,
                    "uses_transitional_fallback": True,
                },
            )

        self.assertTrue(verdict.is_ready)
        self.assertTrue(verdict.compatibility_mode)
        self.assertFalse(verdict.strict_cutover_enabled)
        self.assertEqual(verdict.reason_code, "bootstrap_pack_compatibility")

    def test_published_pack_requirement_blocks_neutral_fallback(self):
        verdict = resolve_published_runtime_requirement(
            capability=get_capability_definition("law_qa"),
            runtime_resolution_snapshot={
                "resolution_mode": "neutral_fallback",
                "requires_explicit_runtime_pack": True,
                "has_published_pack": False,
                "is_runtime_addressable": False,
                "uses_transitional_fallback": True,
            },
        )

        self.assertFalse(verdict.is_ready)
        self.assertEqual(verdict.reason_code, "server_not_runtime_addressable")
        with self.assertRaises(HTTPException) as raised:
            ensure_published_runtime_requirement(verdict, route_path="/api/ai/law-qa-test")

        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("server_not_runtime_addressable", raised.exception.detail[0])


if __name__ == "__main__":
    unittest.main()

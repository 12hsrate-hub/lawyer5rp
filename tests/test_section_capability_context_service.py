from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import os

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from fastapi import HTTPException

from ogp_web.server_config import PermissionSet
from ogp_web.services.section_capability_context_service import (
    ensure_section_permission,
    ensure_section_runtime_requirement,
    resolve_section_capability_context,
)
from ogp_web.services.selected_server_service import SelectedServerContext


class _DummyUserStore:
    def get_server_code(self, username: str) -> str:
        _ = username
        return "blackberry"


class SectionCapabilityContextServiceTests(unittest.TestCase):
    def test_resolve_section_capability_context_serializes_runtime_resolution(self):
        selected_context = SelectedServerContext(
            selected_server_code="orange",
            server_config=type("Cfg", (), {"code": "orange", "name": "Orange County"})(),
            permissions=PermissionSet(codes=frozenset({"court_claims"}), server_code="orange"),
            runtime_resolution_snapshot={
                "resolution_mode": "published_pack",
                "resolution_label": "published pack",
                "is_runtime_addressable": True,
                "has_published_pack": True,
                "has_bootstrap_pack": False,
                "uses_transitional_fallback": False,
                "requires_explicit_runtime_pack": False,
                "pack": {"id": 12, "version": 3, "status": "published"},
            },
        )

        with patch(
            "ogp_web.services.section_capability_context_service.resolve_selected_server_context",
            return_value=selected_context,
        ):
            context = resolve_section_capability_context(
                _DummyUserStore(),
                "tester",
                section_code="court_claim",
                explicit_server_code="orange",
            )

        payload = context.to_payload()
        self.assertEqual(payload["selected_server_code"], "orange")
        self.assertEqual(payload["capability_code"], "court_claim.build")
        self.assertEqual(payload["access_verdict"]["status"], "allowed")
        self.assertEqual(payload["access_verdict"]["reason_code"], "permission_granted")
        self.assertEqual(payload["runtime_resolution"]["mode"], "published_pack")
        self.assertEqual(payload["runtime_resolution"]["pack_id"], 12)
        self.assertEqual(payload["runtime_requirement"]["status"], "ready")
        self.assertEqual(payload["runtime_requirement"]["reason_code"], "published_pack_ready")
        self.assertEqual(payload["read_inventory"]["route_entries"], ["/court-claim-test", "/api/document-builder/bundle"])

    def test_ensure_section_permission_rejects_missing_permission(self):
        selected_context = SelectedServerContext(
            selected_server_code="blackberry",
            server_config=type("Cfg", (), {"code": "blackberry", "name": "BlackBerry"})(),
            permissions=PermissionSet(codes=frozenset(), server_code="blackberry"),
            runtime_resolution_snapshot={"pack": {}},
        )

        with patch(
            "ogp_web.services.section_capability_context_service.resolve_selected_server_context",
            return_value=selected_context,
        ):
            context = resolve_section_capability_context(
                _DummyUserStore(),
                "user",
                section_code="law_qa",
            )

        with self.assertRaises(HTTPException) as raised:
            ensure_section_permission(context)

        self.assertEqual(raised.exception.status_code, 403)
        self.assertIn("court_claims", raised.exception.detail[0])

    def test_ensure_section_runtime_requirement_rejects_blocked_runtime(self):
        selected_context = SelectedServerContext(
            selected_server_code="orange",
            server_config=type("Cfg", (), {"code": "orange", "name": "Orange County"})(),
            permissions=PermissionSet(codes=frozenset({"court_claims"}), server_code="orange"),
            runtime_resolution_snapshot={
                "resolution_mode": "neutral_fallback",
                "resolution_label": "neutral fallback",
                "is_runtime_addressable": False,
                "has_published_pack": False,
                "has_bootstrap_pack": False,
                "uses_transitional_fallback": True,
                "requires_explicit_runtime_pack": True,
                "pack": {},
            },
        )

        with patch(
            "ogp_web.services.section_capability_context_service.resolve_selected_server_context",
            return_value=selected_context,
        ):
            context = resolve_section_capability_context(
                _DummyUserStore(),
                "tester",
                section_code="law_qa",
                explicit_server_code="orange",
            )

        with self.assertRaises(HTTPException) as raised:
            ensure_section_runtime_requirement(context, route_path="/api/ai/law-qa-test")

        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("server_not_runtime_addressable", raised.exception.detail[0])

    def test_default_strict_cutover_surfaces_in_runtime_requirement_payload(self):
        selected_context = SelectedServerContext(
            selected_server_code="blackberry",
            server_config=type("Cfg", (), {"code": "blackberry", "name": "BlackBerry"})(),
            permissions=PermissionSet(codes=frozenset({"court_claims"}), server_code="blackberry"),
            runtime_resolution_snapshot={
                "resolution_mode": "bootstrap_pack",
                "resolution_label": "bootstrap pack",
                "is_runtime_addressable": True,
                "has_published_pack": False,
                "has_bootstrap_pack": True,
                "uses_transitional_fallback": True,
                "requires_explicit_runtime_pack": False,
                "pack": {"version": 1, "status": "published"},
            },
        )

        with patch(
            "ogp_web.services.section_capability_context_service.resolve_selected_server_context",
            return_value=selected_context,
        ):
            context = resolve_section_capability_context(
                _DummyUserStore(),
                "tester",
                section_code="law_qa",
            )

        payload = context.to_payload()
        self.assertEqual(payload["runtime_requirement"]["status"], "blocked")
        self.assertTrue(payload["runtime_requirement"]["strict_cutover_enabled"])
        self.assertEqual(payload["runtime_requirement"]["reason_code"], "published_pack_cutover_required")

    def test_default_strict_cutover_surfaces_for_court_claim_runtime_requirement_payload(self):
        selected_context = SelectedServerContext(
            selected_server_code="blackberry",
            server_config=type("Cfg", (), {"code": "blackberry", "name": "BlackBerry"})(),
            permissions=PermissionSet(codes=frozenset({"court_claims"}), server_code="blackberry"),
            runtime_resolution_snapshot={
                "resolution_mode": "bootstrap_pack",
                "resolution_label": "bootstrap pack",
                "is_runtime_addressable": True,
                "has_published_pack": False,
                "has_bootstrap_pack": True,
                "uses_transitional_fallback": True,
                "requires_explicit_runtime_pack": False,
                "pack": {"version": 1, "status": "published"},
            },
        )

        with patch(
            "ogp_web.services.section_capability_context_service.resolve_selected_server_context",
            return_value=selected_context,
        ):
            context = resolve_section_capability_context(
                _DummyUserStore(),
                "tester",
                section_code="court_claim",
            )

        payload = context.to_payload()
        self.assertEqual(payload["runtime_requirement"]["status"], "blocked")
        self.assertTrue(payload["runtime_requirement"]["strict_cutover_enabled"])
        self.assertEqual(payload["runtime_requirement"]["reason_code"], "published_pack_cutover_required")

    def test_relaxed_cutover_env_surfaces_bootstrap_compatibility_for_law_qa(self):
        selected_context = SelectedServerContext(
            selected_server_code="blackberry",
            server_config=type("Cfg", (), {"code": "blackberry", "name": "BlackBerry"})(),
            permissions=PermissionSet(codes=frozenset({"court_claims"}), server_code="blackberry"),
            runtime_resolution_snapshot={
                "resolution_mode": "bootstrap_pack",
                "resolution_label": "bootstrap pack",
                "is_runtime_addressable": True,
                "has_published_pack": False,
                "has_bootstrap_pack": True,
                "uses_transitional_fallback": True,
                "requires_explicit_runtime_pack": False,
                "pack": {"version": 1, "status": "published"},
            },
        )

        with patch.dict(os.environ, {"OGP_RELAXED_PUBLISHED_RUNTIME_SECTIONS": "law_qa"}, clear=False), patch(
            "ogp_web.services.section_capability_context_service.resolve_selected_server_context",
            return_value=selected_context,
        ):
            context = resolve_section_capability_context(
                _DummyUserStore(),
                "tester",
                section_code="law_qa",
            )

        payload = context.to_payload()
        self.assertEqual(payload["runtime_requirement"]["status"], "ready")
        self.assertFalse(payload["runtime_requirement"]["strict_cutover_enabled"])
        self.assertEqual(payload["runtime_requirement"]["reason_code"], "bootstrap_pack_compatibility")

    def test_relaxed_cutover_env_surfaces_bootstrap_compatibility_for_court_claim(self):
        selected_context = SelectedServerContext(
            selected_server_code="blackberry",
            server_config=type("Cfg", (), {"code": "blackberry", "name": "BlackBerry"})(),
            permissions=PermissionSet(codes=frozenset({"court_claims"}), server_code="blackberry"),
            runtime_resolution_snapshot={
                "resolution_mode": "bootstrap_pack",
                "resolution_label": "bootstrap pack",
                "is_runtime_addressable": True,
                "has_published_pack": False,
                "has_bootstrap_pack": True,
                "uses_transitional_fallback": True,
                "requires_explicit_runtime_pack": False,
                "pack": {"version": 1, "status": "published"},
            },
        )

        with patch.dict(os.environ, {"OGP_RELAXED_PUBLISHED_RUNTIME_SECTIONS": "court_claim"}, clear=False), patch(
            "ogp_web.services.section_capability_context_service.resolve_selected_server_context",
            return_value=selected_context,
        ):
            context = resolve_section_capability_context(
                _DummyUserStore(),
                "tester",
                section_code="court_claim",
            )

        payload = context.to_payload()
        self.assertEqual(payload["runtime_requirement"]["status"], "ready")
        self.assertFalse(payload["runtime_requirement"]["strict_cutover_enabled"])
        self.assertEqual(payload["runtime_requirement"]["reason_code"], "bootstrap_pack_compatibility")

    def test_strict_cutover_env_surfaces_for_complaint_runtime_requirement_payload(self):
        selected_context = SelectedServerContext(
            selected_server_code="blackberry",
            server_config=type("Cfg", (), {"code": "blackberry", "name": "BlackBerry"})(),
            permissions=PermissionSet(codes=frozenset(), server_code="blackberry"),
            runtime_resolution_snapshot={
                "resolution_mode": "bootstrap_pack",
                "resolution_label": "bootstrap pack",
                "is_runtime_addressable": True,
                "has_published_pack": False,
                "has_bootstrap_pack": True,
                "uses_transitional_fallback": True,
                "requires_explicit_runtime_pack": False,
                "pack": {"version": 1, "status": "published"},
            },
        )

        with patch.dict(os.environ, {"OGP_STRICT_PUBLISHED_RUNTIME_SECTIONS": "complaint"}, clear=False), patch(
            "ogp_web.services.section_capability_context_service.resolve_selected_server_context",
            return_value=selected_context,
        ):
            context = resolve_section_capability_context(
                _DummyUserStore(),
                "tester",
                section_code="complaint",
            )

        payload = context.to_payload()
        self.assertEqual(payload["runtime_requirement"]["status"], "blocked")
        self.assertTrue(payload["runtime_requirement"]["strict_cutover_enabled"])
        self.assertEqual(payload["runtime_requirement"]["reason_code"], "published_pack_cutover_required")


if __name__ == "__main__":
    unittest.main()

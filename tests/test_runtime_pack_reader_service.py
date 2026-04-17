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

from ogp_web.services.runtime_pack_reader_service import (
    read_runtime_pack_snapshot,
    resolve_runtime_pack_feature_flags,
    resolve_runtime_pack_law_bundle_path,
    resolve_runtime_pack_law_sources,
)


class RuntimePackReaderServiceTests(unittest.TestCase):
    def test_reader_marks_published_pack_when_database_pack_has_id(self):
        with patch(
            "ogp_web.services.runtime_pack_reader_service.effective_server_pack",
            return_value={"id": 10, "version": 3, "metadata": {"template_bindings": {"complaint": {}}}},
        ):
            snapshot = read_runtime_pack_snapshot(server_code="orange")

        self.assertEqual(snapshot.resolution_mode, "published_pack")
        self.assertEqual(snapshot.pack_version, 3)
        self.assertTrue(snapshot.has_published_pack)

    def test_reader_marks_bootstrap_pack_when_metadata_exists_without_database_id(self):
        with patch(
            "ogp_web.services.runtime_pack_reader_service.effective_server_pack",
            return_value={"version": 1, "metadata": {"document_builder": {"validators": {}}}},
        ):
            snapshot = read_runtime_pack_snapshot(server_code="blackberry")

        self.assertEqual(snapshot.resolution_mode, "bootstrap_pack")
        self.assertTrue(snapshot.uses_bootstrap_pack)

    def test_reader_resolves_runtime_pack_law_sources(self):
        with patch(
            "ogp_web.services.runtime_pack_reader_service.effective_server_pack",
            return_value={"version": 1, "metadata": {"law_qa_sources": [" https://laws.example/a ", "", "https://laws.example/a"]}},
        ):
            sources = resolve_runtime_pack_law_sources(server_code="blackberry")

        self.assertEqual(sources, ("https://laws.example/a",))

    def test_reader_resolves_runtime_pack_law_bundle_path(self):
        with patch(
            "ogp_web.services.runtime_pack_reader_service.effective_server_pack",
            return_value={"version": 1, "metadata": {"law_qa_bundle_path": " law_bundles/blackberry.json "}},
        ):
            bundle_path = resolve_runtime_pack_law_bundle_path(server_code="blackberry")

        self.assertEqual(bundle_path, "law_bundles/blackberry.json")

    def test_reader_resolves_runtime_pack_feature_flags(self):
        with patch(
            "ogp_web.services.runtime_pack_reader_service.effective_server_pack",
            return_value={"version": 1, "metadata": {"feature_flags": [" beta ", "", "alpha", "beta"]}},
        ):
            feature_flags = resolve_runtime_pack_feature_flags(server_code="blackberry")

        self.assertEqual(feature_flags, ("alpha", "beta"))


if __name__ == "__main__":
    unittest.main()

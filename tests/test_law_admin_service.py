from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.services.law_admin_service import LawAdminService, normalize_source_urls, validate_source_urls


class LawAdminServiceHelpersTests(unittest.TestCase):
    def test_normalize_source_urls_removes_empty_and_duplicates(self):
        normalized = normalize_source_urls(
            [
                "",
                "  ",
                "https://example.com/law/a",
                "https://example.com/law/a",
                "https://example.com/law/b",
            ]
        )
        self.assertEqual(
            normalized,
            (
                "https://example.com/law/a",
                "https://example.com/law/b",
            ),
        )

    def test_validate_source_urls_reports_invalid_and_duplicates(self):
        validation = validate_source_urls(
            [
                "https://example.com/law/a",
                "ftp://example.com/law/a",
                "https://example.com/law/a",
                "invalid-url",
                "http://user:pass@",
                "http://example.com/law/b",
            ]
        )

        self.assertEqual(
            validation.accepted_urls,
            (
                "https://example.com/law/a",
                "http://example.com/law/b",
            ),
        )
        self.assertEqual(
            validation.invalid_urls,
            (
                "ftp://example.com/law/a",
                "invalid-url",
                "http://user:pass@",
            ),
        )
        self.assertEqual(validation.duplicate_count, 1)

    def test_list_recent_versions_returns_serialized_payload(self):
        service = LawAdminService(workflow_service=types.SimpleNamespace(repository=types.SimpleNamespace()))
        with patch("ogp_web.services.law_admin_service.list_recent_law_versions") as fake_list:
            fake_list.return_value = (
                types.SimpleNamespace(
                    id=12,
                    server_code="blackberry",
                    generated_at_utc="2026-04-14T12:00:00+00:00",
                    effective_from="2026-04-14T12:00:00+00:00",
                    effective_to="",
                    fingerprint="abc123",
                    chunk_count=345,
                ),
            )
            payload = service.list_recent_versions(server_code="blackberry", limit=5)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["id"], 12)
        self.assertEqual(payload["items"][0]["chunk_count"], 345)

    def test_get_effective_sources_uses_shared_server_config_resolver(self):
        repository = types.SimpleNamespace(
            get_content_item_by_identity=lambda **_: None,
        )
        service = LawAdminService(workflow_service=types.SimpleNamespace(repository=repository))

        with patch(
            "ogp_web.services.law_admin_service.resolve_server_law_sources",
            return_value=("https://example.com/law/a",),
        ) as resolve_server_law_sources_mock, patch(
            "ogp_web.services.law_admin_service.resolve_server_law_bundle_path",
            return_value="",
        ), patch(
            "ogp_web.services.law_admin_service.resolve_active_law_version",
            return_value=None,
        ), patch(
            "ogp_web.services.law_admin_service.load_law_bundle_meta",
            return_value=None,
        ):
            snapshot = service.get_effective_sources(server_code="blackberry")

        self.assertEqual(snapshot.server_code, "blackberry")
        self.assertEqual(snapshot.source_urls, ("https://example.com/law/a",))
        resolve_server_law_sources_mock.assert_called_once_with(server_code="blackberry")

    def test_rebuild_index_dry_run_skips_snapshot_import(self):
        service = LawAdminService(workflow_service=types.SimpleNamespace(repository=types.SimpleNamespace()))
        with patch("ogp_web.services.law_admin_service.resolve_server_law_bundle_path") as fake_bundle_path, \
            patch("ogp_web.services.law_admin_service.build_law_bundle") as fake_bundle, \
            patch("ogp_web.services.law_admin_service.import_law_snapshot") as fake_import:
            fake_bundle_path.return_value = ""
            fake_bundle.return_value = {
                "sources": [{"url": "https://example.com/law/a"}],
                "articles": [{"article_label": "1", "text": "t", "url": "https://example.com/law/a", "document_title": "Doc"}],
            }
            result = service.rebuild_index(
                server_code="blackberry",
                source_urls=["https://example.com/law/a"],
                actor_user_id=1,
                request_id="req-1",
                persist_sources=False,
                dry_run=True,
            )

        self.assertTrue(result["ok"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["article_count"], 1)
        fake_import.assert_not_called()

    def test_rollback_active_version_switches_target(self):
        class _FakeConn:
            def __init__(self):
                self.queries = []
                self.committed = False

            def execute(self, query, params=()):
                self.queries.append((query, params))
                return self

            def commit(self):
                self.committed = True

            def rollback(self):
                self.committed = False

            def close(self):
                return None

        class _FakeBackend:
            def __init__(self, conn):
                self.conn = conn

            def connect(self):
                return self.conn

        fake_conn = _FakeConn()
        service = LawAdminService(
            workflow_service=types.SimpleNamespace(repository=types.SimpleNamespace(backend=_FakeBackend(fake_conn)))
        )
        with patch("ogp_web.services.law_admin_service.list_recent_law_versions") as fake_list, \
            patch("ogp_web.services.law_admin_service.resolve_active_law_version") as fake_active:
            fake_list.return_value = (
                types.SimpleNamespace(id=11),
                types.SimpleNamespace(id=10),
            )
            fake_active.return_value = types.SimpleNamespace(id=10)
            result = service.rollback_active_version(server_code="blackberry", law_version_id=None)

        self.assertTrue(result["ok"])
        self.assertEqual(result["rolled_back_to_version_id"], 10)
        self.assertTrue(fake_conn.committed)
        self.assertEqual(len(fake_conn.queries), 2)

    def test_describe_sources_dependencies_uses_shared_law_qa_server_list(self):
        repository = types.SimpleNamespace()
        service = LawAdminService(workflow_service=types.SimpleNamespace(repository=repository))
        service.get_effective_sources = lambda server_code: types.SimpleNamespace(
            source_origin="content_workflow",
            source_urls=("https://example.com/law/a",),
            active_law_version={"id": 42},
        )

        with patch(
            "ogp_web.services.law_admin_service.list_servers_with_law_qa_context",
            return_value=[{"code": "orange", "name": "Orange County"}],
        ):
            payload = service.describe_sources_dependencies()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["server_count"], 1)
        self.assertEqual(payload["servers"][0]["server_code"], "orange")
        self.assertEqual(payload["servers"][0]["server_name"], "Orange County")


if __name__ == "__main__":
    unittest.main()

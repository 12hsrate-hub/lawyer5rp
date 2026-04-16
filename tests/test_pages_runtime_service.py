from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.server_config.blackberry import BLACKBERRY_SERVER_CONFIG
from ogp_web.services import pages_runtime_service


class _FakeExamStore:
    def __init__(self):
        self.calls: list[tuple[str, int, int] | tuple[str]] = []

    def list_entries(self, *, limit: int, offset: int):
        self.calls.append(("list_entries", limit, offset))
        return [{"source_row": 2}]

    def count(self):
        self.calls.append(("count",))
        return 17


class PagesRuntimeServiceTests(unittest.TestCase):
    def test_build_exam_import_page_data_reads_store_and_sheet_url(self):
        store = _FakeExamStore()

        payload = pages_runtime_service.build_exam_import_page_data(
            server_config=BLACKBERRY_SERVER_CONFIG,
            exam_store=store,
        )

        self.assertEqual(payload["exam_sheet_url"], BLACKBERRY_SERVER_CONFIG.exam_sheet_url)
        self.assertEqual(payload["exam_entries"], [{"source_row": 2}])
        self.assertEqual(payload["exam_total_rows"], 17)
        self.assertEqual(store.calls, [("list_entries", 20, 0), ("count",)])

    def test_build_law_qa_test_page_data_prefers_workflow_backed_sources(self):
        snapshot = SimpleNamespace(source_urls=("https://workflow.example/law",))
        with patch.object(
            pages_runtime_service,
            "_build_law_admin_service",
            return_value=SimpleNamespace(get_effective_sources=lambda **_: snapshot),
        ), patch.object(
            pages_runtime_service,
            "list_servers_with_law_qa_context",
            return_value=[{"code": "blackberry", "name": "BlackBerry"}],
        ), patch.object(
            pages_runtime_service,
            "resolve_server_law_sources",
            return_value=("https://fallback.example/law",),
        ), patch.object(
            pages_runtime_service,
            "get_default_law_qa_model",
            return_value="gpt-5.4-mini",
        ):
            payload = pages_runtime_service.build_law_qa_test_page_data(server_config=BLACKBERRY_SERVER_CONFIG)

        self.assertEqual(payload["law_qa_sources"], ["https://workflow.example/law"])
        self.assertEqual(payload["law_qa_servers"], [{"code": "blackberry", "name": "BlackBerry"}])
        self.assertEqual(payload["law_qa_default_model"], "gpt-5.4-mini")

    def test_build_law_qa_test_page_data_falls_back_when_workflow_lookup_fails(self):
        with patch.object(
            pages_runtime_service,
            "_build_law_admin_service",
            return_value=SimpleNamespace(get_effective_sources=lambda **_: (_ for _ in ()).throw(RuntimeError("db down"))),
        ), patch.object(
            pages_runtime_service,
            "list_servers_with_law_qa_context",
            return_value=[{"code": "blackberry", "name": "BlackBerry"}],
        ), patch.object(
            pages_runtime_service,
            "resolve_server_law_sources",
            return_value=("https://fallback.example/law",),
        ), patch.object(
            pages_runtime_service,
            "get_default_law_qa_model",
            return_value="gpt-5.4-mini",
        ):
            payload = pages_runtime_service.build_law_qa_test_page_data(server_config=BLACKBERRY_SERVER_CONFIG)

        self.assertEqual(payload["law_qa_sources"], ["https://fallback.example/law"])
        self.assertEqual(payload["law_qa_servers"], [{"code": "blackberry", "name": "BlackBerry"}])
        self.assertEqual(payload["law_qa_default_model"], "gpt-5.4-mini")


if __name__ == "__main__":
    unittest.main()

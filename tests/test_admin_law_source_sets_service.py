from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

os.environ.setdefault("OGP_WEB_SECRET", "test-secret")
os.environ.setdefault("OGP_DB_BACKEND", "postgres")
os.environ.setdefault("OGP_SKIP_DEFAULT_APP_INIT", "1")

from ogp_web.services.admin_law_source_sets_service import (
    list_server_source_set_bindings_payload,
    list_source_set_revisions_payload,
    list_source_sets_payload,
)
from ogp_web.storage.law_source_sets_store import (
    ServerSourceSetBindingRecord,
    SourceSetRecord,
    SourceSetRevisionRecord,
)


class _FakeLawSourceSetsStore:
    def list_source_sets(self):
        return [
            SourceSetRecord(
                source_set_key="orange-core",
                title="Orange core",
                description="Primary containers",
                scope="global",
                created_at="2026-04-16T00:00:00+00:00",
                updated_at="2026-04-16T00:00:00+00:00",
            )
        ]

    def get_source_set(self, *, source_set_key: str):
        if source_set_key != "orange-core":
            return None
        return self.list_source_sets()[0]

    def list_revisions(self, *, source_set_key: str):
        if source_set_key != "orange-core":
            return []
        return [
            SourceSetRevisionRecord(
                id=7,
                source_set_key="orange-core",
                revision=2,
                status="published",
                container_urls=("https://example.com/a", "https://example.com/b"),
                adapter_policy_json={"extractor": "forum_topic"},
                metadata_json={"promotion_mode": "hybrid"},
                created_at="2026-04-16T00:05:00+00:00",
                published_at="2026-04-16T00:06:00+00:00",
            )
        ]

    def list_bindings(self, *, server_code: str):
        if server_code != "orange":
            return []
        return [
            ServerSourceSetBindingRecord(
                id=3,
                server_code="orange",
                source_set_key="orange-core",
                priority=10,
                is_active=True,
                include_law_keys=("law.alpha",),
                exclude_law_keys=("law.beta",),
                pin_policy_json={"freeze": True},
                metadata_json={"origin": "phase2"},
                created_at="2026-04-16T00:10:00+00:00",
                updated_at="2026-04-16T00:10:00+00:00",
            )
        ]


class AdminLawSourceSetsServiceTests(unittest.TestCase):
    def test_list_source_sets_payload(self):
        payload = list_source_sets_payload(store=_FakeLawSourceSetsStore())
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["source_set_key"], "orange-core")

    def test_list_source_set_revisions_payload_requires_existing_source_set(self):
        with self.assertRaises(KeyError):
            list_source_set_revisions_payload(store=_FakeLawSourceSetsStore(), source_set_key="missing")

    def test_list_source_set_revisions_payload(self):
        payload = list_source_set_revisions_payload(store=_FakeLawSourceSetsStore(), source_set_key=" Orange-Core ")
        self.assertEqual(payload["source_set"]["source_set_key"], "orange-core")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["revision"], 2)
        self.assertEqual(payload["items"][0]["container_urls"][0], "https://example.com/a")

    def test_list_server_source_set_bindings_payload(self):
        payload = list_server_source_set_bindings_payload(store=_FakeLawSourceSetsStore(), server_code=" Orange ")
        self.assertEqual(payload["server_code"], "orange")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["source_set_key"], "orange-core")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.storage.canonical_law_document_versions_store import CanonicalLawDocumentVersionsStore


class _Cursor:
    def __init__(self, *, one=None, rows=None):
        self._one = one
        self._rows = rows or []

    def fetchone(self):
        if self._one is not None:
            return self._one
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _Connection:
    def __init__(self):
        self.versions: list[dict[str, object]] = []
        self.next_version_id = 1

    def _joined_row(self, row: dict[str, object]) -> dict[str, object]:
        return {
            **row,
            "canonical_identity_key": "url_seed:abc",
            "display_title": "Procedural Code",
            "source_set_key": "orange-core",
            "revision": 2,
            "normalized_url": "https://example.com/law/a",
            "source_container_url": "https://example.com/topic/1",
        }

    def execute(self, query: str, params=()):
        normalized = " ".join(query.split())
        if normalized.startswith("SELECT v.id, v.canonical_law_document_id, d.canonical_identity_key, d.display_title, v.source_discovery_run_id, v.discovered_law_link_id, rev.source_set_key, l.source_set_revision_id, rev.revision, l.normalized_url, l.source_container_url, v.fetch_status, v.parse_status, v.content_checksum, v.raw_title, v.parsed_title, v.body_text, v.metadata_json, v.created_at, v.updated_at FROM canonical_law_document_versions AS v JOIN canonical_law_documents AS d ON d.id = v.canonical_law_document_id JOIN discovered_law_links AS l ON l.id = v.discovered_law_link_id JOIN source_set_revisions AS rev ON rev.id = l.source_set_revision_id WHERE v.source_discovery_run_id = %s ORDER BY v.created_at DESC, v.id DESC"):
            run_id = int(params[0])
            rows = [self._joined_row(item) for item in self.versions if int(item["source_discovery_run_id"]) == run_id]
            rows.sort(key=lambda item: (str(item["created_at"]), int(item["id"])), reverse=True)
            return _Cursor(rows=rows)
        if normalized.startswith("SELECT v.id, v.canonical_law_document_id, d.canonical_identity_key, d.display_title, v.source_discovery_run_id, v.discovered_law_link_id, rev.source_set_key, l.source_set_revision_id, rev.revision, l.normalized_url, l.source_container_url, v.fetch_status, v.parse_status, v.content_checksum, v.raw_title, v.parsed_title, v.body_text, v.metadata_json, v.created_at, v.updated_at FROM canonical_law_document_versions AS v JOIN canonical_law_documents AS d ON d.id = v.canonical_law_document_id JOIN discovered_law_links AS l ON l.id = v.discovered_law_link_id JOIN source_set_revisions AS rev ON rev.id = l.source_set_revision_id WHERE v.canonical_law_document_id = %s ORDER BY v.created_at DESC, v.id DESC"):
            document_id = int(params[0])
            rows = [self._joined_row(item) for item in self.versions if int(item["canonical_law_document_id"]) == document_id]
            rows.sort(key=lambda item: (str(item["created_at"]), int(item["id"])), reverse=True)
            return _Cursor(rows=rows)
        if normalized.startswith("SELECT v.id, v.canonical_law_document_id, d.canonical_identity_key, d.display_title, v.source_discovery_run_id, v.discovered_law_link_id, rev.source_set_key, l.source_set_revision_id, rev.revision, l.normalized_url, l.source_container_url, v.fetch_status, v.parse_status, v.content_checksum, v.raw_title, v.parsed_title, v.body_text, v.metadata_json, v.created_at, v.updated_at FROM canonical_law_document_versions AS v JOIN canonical_law_documents AS d ON d.id = v.canonical_law_document_id JOIN discovered_law_links AS l ON l.id = v.discovered_law_link_id JOIN source_set_revisions AS rev ON rev.id = l.source_set_revision_id WHERE v.discovered_law_link_id = %s LIMIT 1"):
            link_id = int(params[0])
            row = next((self._joined_row(item) for item in self.versions if int(item["discovered_law_link_id"]) == link_id), None)
            return _Cursor(rows=[row] if row else [])
        if normalized.startswith("INSERT INTO canonical_law_document_versions ( canonical_law_document_id, source_discovery_run_id, discovered_law_link_id, fetch_status, parse_status, content_checksum, raw_title, parsed_title, body_text, metadata_json ) VALUES"):
            canonical_law_document_id, source_discovery_run_id, discovered_law_link_id, fetch_status, parse_status, content_checksum, raw_title, parsed_title, body_text, metadata_json = params
            if any(item for item in self.versions if int(item["discovered_law_link_id"]) == int(discovered_law_link_id)):
                raise Exception('duplicate key value violates unique constraint "canonical_law_document_versions_discovered_law_link_id_key"')
            row = {
                "id": self.next_version_id,
                "canonical_law_document_id": int(canonical_law_document_id),
                "source_discovery_run_id": int(source_discovery_run_id),
                "discovered_law_link_id": int(discovered_law_link_id),
                "source_set_revision_id": 7,
                "fetch_status": fetch_status,
                "parse_status": parse_status,
                "content_checksum": content_checksum,
                "raw_title": raw_title,
                "parsed_title": parsed_title,
                "body_text": body_text,
                "metadata_json": dict(metadata_json),
                "created_at": "2026-04-16T02:00:00+00:00",
                "updated_at": "2026-04-16T02:00:00+00:00",
            }
            self.next_version_id += 1
            self.versions.append(row)
            return _Cursor(one={"id": row["id"]})
        if normalized.startswith("SELECT v.id, v.canonical_law_document_id, d.canonical_identity_key, d.display_title, v.source_discovery_run_id, v.discovered_law_link_id, rev.source_set_key, l.source_set_revision_id, rev.revision, l.normalized_url, l.source_container_url, v.fetch_status, v.parse_status, v.content_checksum, v.raw_title, v.parsed_title, v.body_text, v.metadata_json, v.created_at, v.updated_at FROM canonical_law_document_versions AS v JOIN canonical_law_documents AS d ON d.id = v.canonical_law_document_id JOIN discovered_law_links AS l ON l.id = v.discovered_law_link_id JOIN source_set_revisions AS rev ON rev.id = l.source_set_revision_id WHERE v.id = %s"):
            version_id = int(params[0])
            row = next((self._joined_row(item) for item in self.versions if int(item["id"]) == version_id), None)
            return _Cursor(rows=[row] if row else [])
        if normalized.startswith("UPDATE canonical_law_document_versions SET fetch_status = %s, content_checksum = %s, raw_title = %s, body_text = %s, metadata_json = %s::jsonb, updated_at = NOW() WHERE id = %s RETURNING id"):
            fetch_status, content_checksum, raw_title, body_text, metadata_json, version_id = params
            row = next((item for item in self.versions if int(item["id"]) == int(version_id)), None)
            if row is None:
                return _Cursor(one=None)
            row["fetch_status"] = fetch_status
            row["content_checksum"] = content_checksum
            row["raw_title"] = raw_title
            row["body_text"] = body_text
            row["metadata_json"] = dict(metadata_json)
            row["updated_at"] = "2026-04-16T03:00:00+00:00"
            return _Cursor(one={"id": row["id"]})
        if normalized.startswith("UPDATE canonical_law_document_versions SET parse_status = %s, parsed_title = %s, body_text = %s, metadata_json = %s::jsonb, updated_at = NOW() WHERE id = %s RETURNING id"):
            parse_status, parsed_title, body_text, metadata_json, version_id = params
            row = next((item for item in self.versions if int(item["id"]) == int(version_id)), None)
            if row is None:
                return _Cursor(one=None)
            row["parse_status"] = parse_status
            row["parsed_title"] = parsed_title
            row["body_text"] = body_text
            row["metadata_json"] = dict(metadata_json)
            row["updated_at"] = "2026-04-16T03:10:00+00:00"
            return _Cursor(one={"id": row["id"]})
        raise AssertionError(f"Unsupported query: {normalized}")

    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        return None


class _Backend:
    def __init__(self):
        self.conn = _Connection()

    def connect(self):
        return self.conn


def test_canonical_law_document_versions_store_creates_and_lists_versions():
    store = CanonicalLawDocumentVersionsStore(_Backend())
    version = store.create_version(
        canonical_law_document_id=1,
        source_discovery_run_id=5,
        discovered_law_link_id=11,
        fetch_status="seeded",
        parse_status="pending",
        content_checksum="abc123",
    )
    assert version.id == 1
    assert version.fetch_status == "seeded"
    by_run = store.list_versions_for_run(source_discovery_run_id=5)
    assert [item.id for item in by_run] == [1]
    by_document = store.list_versions_for_document(canonical_law_document_id=1)
    assert [item.id for item in by_document] == [1]


def test_canonical_law_document_versions_store_duplicate_link_returns_value_error():
    store = CanonicalLawDocumentVersionsStore(_Backend())
    created = store.create_version(
        canonical_law_document_id=1,
        source_discovery_run_id=5,
        discovered_law_link_id=11,
    )
    assert created.id == 1
    try:
        store.create_version(
            canonical_law_document_id=1,
            source_discovery_run_id=5,
            discovered_law_link_id=11,
        )
        assert False, "expected ValueError"
    except ValueError as exc:
        assert str(exc) == "canonical_law_document_version_already_exists"


def test_canonical_law_document_versions_store_updates_fetch_result():
    store = CanonicalLawDocumentVersionsStore(_Backend())
    created = store.create_version(
        canonical_law_document_id=1,
        source_discovery_run_id=5,
        discovered_law_link_id=11,
    )
    updated = store.update_fetch_result(
        version_id=created.id,
        fetch_status="fetched",
        content_checksum="def456",
        raw_title="Fetched Title",
        body_text="Fetched body",
        metadata_json={"fetch_mode": "manual_admin_fetch"},
    )
    assert updated.fetch_status == "fetched"
    assert updated.content_checksum == "def456"
    assert updated.raw_title == "Fetched Title"
    assert updated.body_text == "Fetched body"
    fetched = store.get_version(version_id=created.id)
    assert fetched is not None
    assert fetched.fetch_status == "fetched"


def test_canonical_law_document_versions_store_updates_parse_result():
    store = CanonicalLawDocumentVersionsStore(_Backend())
    created = store.create_version(
        canonical_law_document_id=1,
        source_discovery_run_id=5,
        discovered_law_link_id=11,
        fetch_status="fetched",
        body_text="<html><title>Fetched Title</title><body>Fetched body</body></html>",
    )
    updated = store.update_parse_result(
        version_id=created.id,
        parse_status="parsed",
        parsed_title="Fetched Title",
        body_text="Fetched Title Fetched body",
        metadata_json={"parse_mode": "manual_admin_parse"},
    )
    assert updated.parse_status == "parsed"
    assert updated.parsed_title == "Fetched Title"
    assert updated.body_text == "Fetched Title Fetched body"

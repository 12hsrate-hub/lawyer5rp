from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.storage.canonical_law_documents_store import CanonicalLawDocumentsStore


class _Cursor:
    def __init__(self, *, one=None, rows=None):
        self._one = one
        self._rows = rows or []

    def fetchone(self):
        return self._one

    def fetchall(self):
        return list(self._rows)


class _Connection:
    def __init__(self):
        self.documents: list[dict[str, object]] = []
        self.aliases: list[dict[str, object]] = []
        self.next_document_id = 1
        self.next_alias_id = 1

    def execute(self, query: str, params=()):
        normalized = " ".join(query.split())
        if normalized.startswith("SELECT id, canonical_identity_key, identity_source, display_title, metadata_json, created_at, updated_at FROM canonical_law_documents ORDER BY canonical_identity_key ASC"):
            rows = sorted(self.documents, key=lambda item: str(item["canonical_identity_key"]))
            return _Cursor(rows=rows)
        if normalized.startswith("SELECT id, canonical_identity_key, identity_source, display_title, metadata_json, created_at, updated_at FROM canonical_law_documents WHERE canonical_identity_key = %s"):
            key = params[0]
            row = next((item for item in self.documents if str(item["canonical_identity_key"]) == str(key)), None)
            return _Cursor(one=row)
        if normalized.startswith("INSERT INTO canonical_law_documents ( canonical_identity_key, identity_source, display_title, metadata_json ) VALUES"):
            canonical_identity_key, identity_source, display_title, metadata_json = params
            if any(item for item in self.documents if str(item["canonical_identity_key"]) == str(canonical_identity_key)):
                raise Exception('duplicate key value violates unique constraint "canonical_law_documents_canonical_identity_key_key"')
            row = {
                "id": self.next_document_id,
                "canonical_identity_key": canonical_identity_key,
                "identity_source": identity_source,
                "display_title": display_title,
                "metadata_json": dict(metadata_json),
                "created_at": "2026-04-16T01:00:00+00:00",
                "updated_at": "2026-04-16T01:00:00+00:00",
            }
            self.next_document_id += 1
            self.documents.append(row)
            return _Cursor(one=row)
        if normalized.startswith("SELECT id, canonical_law_document_id, normalized_url, alias_kind, is_active, metadata_json, created_at, updated_at FROM canonical_law_document_aliases WHERE canonical_law_document_id = %s ORDER BY normalized_url ASC, id ASC"):
            document_id = int(params[0])
            rows = [row for row in self.aliases if int(row["canonical_law_document_id"]) == document_id]
            rows.sort(key=lambda item: (str(item["normalized_url"]), int(item["id"])))
            return _Cursor(rows=rows)
        if normalized.startswith("INSERT INTO canonical_law_document_aliases ( canonical_law_document_id, normalized_url, alias_kind, is_active, metadata_json ) VALUES"):
            canonical_law_document_id, normalized_url, alias_kind, is_active, metadata_json = params
            if any(item for item in self.aliases if str(item["normalized_url"]) == str(normalized_url)):
                raise Exception('duplicate key value violates unique constraint "canonical_law_document_aliases_normalized_url_key"')
            row = {
                "id": self.next_alias_id,
                "canonical_law_document_id": int(canonical_law_document_id),
                "normalized_url": normalized_url,
                "alias_kind": alias_kind,
                "is_active": bool(is_active),
                "metadata_json": dict(metadata_json),
                "created_at": "2026-04-16T01:05:00+00:00",
                "updated_at": "2026-04-16T01:05:00+00:00",
            }
            self.next_alias_id += 1
            self.aliases.append(row)
            return _Cursor(one=row)
        if normalized.startswith("SELECT d.id AS document_id, d.canonical_identity_key, d.identity_source, d.display_title, d.metadata_json AS document_metadata_json, a.id AS alias_id, a.normalized_url, a.alias_kind, a.is_active, a.metadata_json AS alias_metadata_json FROM canonical_law_document_aliases AS a JOIN canonical_law_documents AS d ON d.id = a.canonical_law_document_id WHERE a.normalized_url = %s LIMIT 1"):
            normalized_url = params[0]
            alias = next((item for item in self.aliases if str(item["normalized_url"]) == str(normalized_url)), None)
            if alias is None:
                return _Cursor(one=None)
            document = next(item for item in self.documents if int(item["id"]) == int(alias["canonical_law_document_id"]))
            return _Cursor(
                one={
                    "document_id": document["id"],
                    "canonical_identity_key": document["canonical_identity_key"],
                    "identity_source": document["identity_source"],
                    "display_title": document["display_title"],
                    "document_metadata_json": dict(document["metadata_json"]),
                    "alias_id": alias["id"],
                    "normalized_url": alias["normalized_url"],
                    "alias_kind": alias["alias_kind"],
                    "is_active": alias["is_active"],
                    "alias_metadata_json": dict(alias["metadata_json"]),
                }
            )
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


def test_canonical_law_documents_store_creates_document_and_alias():
    store = CanonicalLawDocumentsStore(_Backend())
    document = store.create_document(
        canonical_identity_key="url_seed:abc",
        display_title="Procedural Code",
        metadata_json={"seed_url": "https://example.com/law/a"},
    )
    assert document.id == 1
    alias = store.create_alias(
        canonical_law_document_id=document.id,
        normalized_url="https://example.com/law/a",
        alias_kind="canonical",
    )
    assert alias.id == 1
    resolved = store.resolve_document_by_alias(normalized_url="https://example.com/law/a")
    assert resolved is not None
    assert resolved.canonical_identity_key == "url_seed:abc"
    assert resolved.alias_kind == "canonical"


def test_canonical_law_documents_store_duplicate_alias_returns_value_error():
    store = CanonicalLawDocumentsStore(_Backend())
    document = store.create_document(canonical_identity_key="url_seed:abc")
    created = store.create_alias(canonical_law_document_id=document.id, normalized_url="https://example.com/law/a")
    assert created.id == 1
    try:
        store.create_alias(canonical_law_document_id=document.id, normalized_url="https://example.com/law/a")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert str(exc) == "canonical_law_document_alias_already_exists"

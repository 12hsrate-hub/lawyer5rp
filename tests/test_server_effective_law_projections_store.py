from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.storage.server_effective_law_projections_store import ServerEffectiveLawProjectionsStore


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
        self.runs: list[dict[str, object]] = []
        self.items: list[dict[str, object]] = []
        self.next_run_id = 1
        self.next_item_id = 1

    def execute(self, query: str, params=()):
        normalized = " ".join(query.split())
        if normalized.startswith("SELECT id, server_code, trigger_mode, status, summary_json, created_at FROM server_effective_law_projection_runs WHERE server_code = %s ORDER BY created_at DESC, id DESC"):
            server_code = str(params[0])
            rows = [row for row in self.runs if str(row["server_code"]) == server_code]
            rows.sort(key=lambda row: (str(row["created_at"]), int(row["id"])), reverse=True)
            return _Cursor(rows=rows)
        if normalized.startswith("SELECT id, server_code, trigger_mode, status, summary_json, created_at FROM server_effective_law_projection_runs WHERE id = %s"):
            run_id = int(params[0])
            row = next((row for row in self.runs if int(row["id"]) == run_id), None)
            return _Cursor(one=row)
        if normalized.startswith("SELECT id, projection_run_id, canonical_law_document_id, canonical_identity_key, normalized_url, selected_document_version_id, selected_source_set_key, selected_revision, precedence_rank, contributor_count, status, provenance_json, created_at FROM server_effective_law_projection_items WHERE projection_run_id = %s ORDER BY precedence_rank ASC, canonical_identity_key ASC, id ASC"):
            run_id = int(params[0])
            rows = [row for row in self.items if int(row["projection_run_id"]) == run_id]
            rows.sort(key=lambda row: (int(row["precedence_rank"]), str(row["canonical_identity_key"]), int(row["id"])))
            return _Cursor(rows=rows)
        if normalized.startswith("INSERT INTO server_effective_law_projection_runs ( server_code, trigger_mode, status, summary_json ) VALUES"):
            server_code, trigger_mode, status, summary_json = params
            row = {
                "id": self.next_run_id,
                "server_code": str(server_code),
                "trigger_mode": str(trigger_mode),
                "status": str(status),
                "summary_json": dict(summary_json),
                "created_at": "2026-04-16T05:00:00+00:00",
            }
            self.next_run_id += 1
            self.runs.append(row)
            return _Cursor(one=row)
        if normalized.startswith("INSERT INTO server_effective_law_projection_items ( projection_run_id, canonical_law_document_id, canonical_identity_key, normalized_url, selected_document_version_id, selected_source_set_key, selected_revision, precedence_rank, contributor_count, status, provenance_json ) VALUES"):
            projection_run_id, canonical_law_document_id, canonical_identity_key, normalized_url, selected_document_version_id, selected_source_set_key, selected_revision, precedence_rank, contributor_count, status, provenance_json = params
            row = {
                "id": self.next_item_id,
                "projection_run_id": int(projection_run_id),
                "canonical_law_document_id": int(canonical_law_document_id),
                "canonical_identity_key": str(canonical_identity_key),
                "normalized_url": str(normalized_url),
                "selected_document_version_id": int(selected_document_version_id),
                "selected_source_set_key": str(selected_source_set_key),
                "selected_revision": int(selected_revision),
                "precedence_rank": int(precedence_rank),
                "contributor_count": int(contributor_count),
                "status": str(status),
                "provenance_json": dict(provenance_json),
                "created_at": "2026-04-16T05:01:00+00:00",
            }
            self.next_item_id += 1
            self.items.append(row)
            return _Cursor(one=row)
        if normalized.startswith("UPDATE server_effective_law_projection_runs SET status = %s, summary_json = %s::jsonb WHERE id = %s RETURNING id, server_code, trigger_mode, status, summary_json, created_at"):
            status, summary_json, run_id = params
            row = next((row for row in self.runs if int(row["id"]) == int(run_id)), None)
            if row is None:
                return _Cursor(one=None)
            row["status"] = str(status)
            row["summary_json"] = dict(summary_json)
            return _Cursor(one=row)
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


def test_server_effective_law_projections_store_creates_and_lists_runs_and_items():
    store = ServerEffectiveLawProjectionsStore(_Backend())
    run = store.create_projection_run(server_code="orange", summary_json={"selected_count": 1})
    assert run.id == 1
    item = store.create_projection_item(
        projection_run_id=run.id,
        canonical_law_document_id=2,
        canonical_identity_key="url_seed:law-a",
        normalized_url="https://example.com/law/a",
        selected_document_version_id=5,
        selected_source_set_key="orange-core",
        selected_revision=3,
        precedence_rank=1,
        contributor_count=2,
        provenance_json={"contributors": []},
    )
    assert item.id == 1
    assert store.list_runs(server_code="orange")[0].id == 1
    assert store.list_items(projection_run_id=run.id)[0].selected_document_version_id == 5


def test_server_effective_law_projections_store_updates_run_status():
    store = ServerEffectiveLawProjectionsStore(_Backend())
    run = store.create_projection_run(server_code="orange", summary_json={"selected_count": 1})
    updated = store.update_run_status(
        run_id=run.id,
        status="approved",
        summary_json={"selected_count": 1, "decision_status": "approved"},
    )
    assert updated.status == "approved"
    assert updated.summary_json["decision_status"] == "approved"

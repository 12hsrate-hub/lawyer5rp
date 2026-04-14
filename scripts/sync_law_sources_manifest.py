from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.db.factory import get_database_backend
from ogp_web.env import load_web_env
from ogp_web.services.content_workflow_service import ContentWorkflowService
from ogp_web.services.law_admin_service import LawAdminService
from ogp_web.storage.content_workflow_repository import ContentWorkflowRepository
from ogp_web.storage.user_store import get_default_user_store


def _resolve_actor_user_id() -> int:
    user_store = get_default_user_store()
    for username in ("admin", "system"):
        actor_user_id = user_store.get_user_id(username)
        if actor_user_id is not None:
            return int(actor_user_id)
    conn = user_store.backend.connect()
    try:
        row = conn.execute(
            """
            SELECT id
            FROM users
            ORDER BY created_at ASC, id ASC
            LIMIT 1
            """
        ).fetchone()
    finally:
        conn.close()
    if row is not None and row.get("id") is not None:
        return int(row["id"])
    raise RuntimeError("Cannot sync law sources manifest: no users found in database")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync server law sources into DB-backed manifest and optionally rebuild DB law index.")
    parser.add_argument("--server", default="blackberry")
    parser.add_argument("--safe-rerun", action="store_true")
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()

    load_web_env()
    backend = get_database_backend()
    service = ContentWorkflowService(ContentWorkflowRepository(backend), legacy_store=None)
    law_admin_service = LawAdminService(service)
    actor_user_id = _resolve_actor_user_id()

    result = {
        "sync": law_admin_service.sync_sources_manifest_from_server_config(
            server_code=args.server,
            actor_user_id=actor_user_id,
            request_id="sync-law-sources-manifest",
            safe_rerun=bool(args.safe_rerun),
        )
    }
    if args.rebuild:
        result["rebuild"] = law_admin_service.rebuild_index(
            server_code=args.server,
            actor_user_id=actor_user_id,
            request_id="sync-law-sources-manifest",
            persist_sources=False,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

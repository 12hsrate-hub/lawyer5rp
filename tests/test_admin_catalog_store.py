import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.storage.admin_catalog_store import AdminCatalogStore


def test_catalog_crud_and_workflow(tmp_path: Path):
    store = AdminCatalogStore(tmp_path / "catalog.json")

    created = store.create_item("servers", title="Main", config={"host": "127.0.0.1"}, author="admin")
    assert created["state"] == "draft"

    updated = store.update_item("servers", created["id"], title="Main-2", config={"host": "localhost"}, author="editor")
    assert updated["title"] == "Main-2"
    assert len(updated["versions"]) == 2

    reviewed = store.transition_item("servers", created["id"], target_state="review", author="reviewer")
    assert reviewed["state"] == "review"

    published = store.transition_item("servers", created["id"], target_state="publish", author="publisher")
    assert published["state"] == "publish"

    rolled_back = store.rollback_item("servers", created["id"], version=1, author="admin")
    assert rolled_back["state"] == "draft"
    assert rolled_back["config"]["host"] == "127.0.0.1"

    audit = store.recent_audit(limit=20, entity_type="servers")
    assert audit

    store.delete_item("servers", created["id"], author="admin")
    assert store.list_items("servers") == []

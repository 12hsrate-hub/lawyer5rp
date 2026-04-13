import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ogp_web.storage.admin_catalog_store import AdminCatalogStore


def test_catalog_legacy_adapter_is_read_only(tmp_path: Path):
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps({"items": {"servers": [{"id": "x1", "title": "Main"}]}, "audit": []}), encoding="utf-8")
    store = AdminCatalogStore(path)

    assert store.list_items("servers")[0]["id"] == "x1"
    assert store.iter_legacy_items()

    for fn in (store.create_item, store.update_item, store.delete_item, store.transition_item, store.rollback_item):
        try:
            fn("servers")
            assert False, "expected RuntimeError"
        except RuntimeError as exc:
            assert str(exc) == "legacy_store_read_only"

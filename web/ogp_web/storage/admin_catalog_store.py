from __future__ import annotations

import json
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT_DIR / "web" / "data"
CATALOG_PATH = DATA_DIR / "admin_catalog.json"

ALLOWED_ENTITY_TYPES = ("servers", "laws", "templates", "features", "rules")


class AdminCatalogStore:
    """Legacy catalog adapter.

    This store is intentionally read-only and is used only for fallback reads/import
    during staged migration to DB-backed content workflow.
    """

    def __init__(self, path: Path = CATALOG_PATH):
        self.path = path
        self._lock = threading.RLock()
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    def _empty_payload(self) -> dict[str, Any]:
        return {
            "items": {entity: [] for entity in ALLOWED_ENTITY_TYPES},
            "audit": [],
        }

    def _read_payload(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty_payload()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return self._empty_payload()
        if not isinstance(payload, dict):
            return self._empty_payload()
        payload.setdefault("items", {entity: [] for entity in ALLOWED_ENTITY_TYPES})
        payload.setdefault("audit", [])
        for entity in ALLOWED_ENTITY_TYPES:
            payload["items"].setdefault(entity, [])
        return payload

    def _validate_entity_type(self, entity_type: str) -> str:
        normalized = str(entity_type or "").strip().lower()
        if normalized not in ALLOWED_ENTITY_TYPES:
            raise ValueError("unsupported_entity_type")
        return normalized

    def list_items(self, entity_type: str) -> list[dict[str, Any]]:
        with self._lock:
            normalized = self._validate_entity_type(entity_type)
            payload = self._read_payload()
            return deepcopy(payload["items"][normalized])

    def recent_audit(self, limit: int = 100, entity_type: str = "") -> list[dict[str, Any]]:
        with self._lock:
            payload = self._read_payload()
            events = list(payload.get("audit") or [])
            normalized = str(entity_type or "").strip().lower()
            if normalized:
                events = [item for item in events if str(item.get("entity_type") or "") == normalized]
            events = sorted(events, key=lambda item: str(item.get("created_at") or ""), reverse=True)
            return deepcopy(events[: max(1, int(limit or 100))])

    def iter_legacy_items(self) -> list[tuple[str, dict[str, Any]]]:
        with self._lock:
            payload = self._read_payload()
            results: list[tuple[str, dict[str, Any]]] = []
            for entity in ALLOWED_ENTITY_TYPES:
                for item in payload.get("items", {}).get(entity, []):
                    if isinstance(item, dict):
                        results.append((entity, deepcopy(item)))
            return results

    def create_item(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("legacy_store_read_only")

    def update_item(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("legacy_store_read_only")

    def delete_item(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("legacy_store_read_only")

    def transition_item(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("legacy_store_read_only")

    def rollback_item(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("legacy_store_read_only")


_DEFAULT_STORE: AdminCatalogStore | None = None


def get_default_admin_catalog_store() -> AdminCatalogStore:
    global _DEFAULT_STORE
    if _DEFAULT_STORE is None:
        _DEFAULT_STORE = AdminCatalogStore()
    return _DEFAULT_STORE

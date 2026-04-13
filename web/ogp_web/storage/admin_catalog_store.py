from __future__ import annotations

import json
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from difflib import unified_diff
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT_DIR / "web" / "data"
CATALOG_PATH = DATA_DIR / "admin_catalog.json"

ALLOWED_ENTITY_TYPES = ("servers", "laws", "templates", "features", "rules")
ALLOWED_STATES = ("draft", "review", "publish")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _build_diff(before: dict[str, Any], after: dict[str, Any]) -> str:
    before_lines = _json_dump(before).splitlines()
    after_lines = _json_dump(after).splitlines()
    return "\n".join(
        unified_diff(before_lines, after_lines, fromfile="before", tofile="after", lineterm="")
    )


class AdminCatalogStore:
    def __init__(self, path: Path = CATALOG_PATH):
        self.path = path
        self._lock = threading.RLock()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write_payload(self._empty_payload())

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

    def _write_payload(self, payload: dict[str, Any]) -> None:
        self.path.write_text(_json_dump(payload), encoding="utf-8")

    def _validate_entity_type(self, entity_type: str) -> str:
        normalized = str(entity_type or "").strip().lower()
        if normalized not in ALLOWED_ENTITY_TYPES:
            raise ValueError("unsupported_entity_type")
        return normalized

    def _find_item(self, payload: dict[str, Any], entity_type: str, item_id: str) -> dict[str, Any] | None:
        for item in payload["items"][entity_type]:
            if str(item.get("id")) == item_id:
                return item
        return None

    def _append_audit(
        self,
        *,
        payload: dict[str, Any],
        action: str,
        entity_type: str,
        item_id: str,
        author: str,
        diff_text: str,
        workflow_from: str = "",
        workflow_to: str = "",
    ) -> None:
        payload["audit"].append(
            {
                "id": uuid.uuid4().hex,
                "created_at": _utc_now(),
                "action": action,
                "entity_type": entity_type,
                "item_id": item_id,
                "author": author,
                "workflow_from": workflow_from,
                "workflow_to": workflow_to,
                "diff": diff_text,
            }
        )

    def list_items(self, entity_type: str) -> list[dict[str, Any]]:
        with self._lock:
            normalized = self._validate_entity_type(entity_type)
            payload = self._read_payload()
            return deepcopy(payload["items"][normalized])

    def create_item(self, entity_type: str, *, title: str, config: dict[str, Any], author: str) -> dict[str, Any]:
        with self._lock:
            normalized = self._validate_entity_type(entity_type)
            payload = self._read_payload()
            now = _utc_now()
            item = {
                "id": uuid.uuid4().hex,
                "title": str(title or "").strip() or "Untitled",
                "state": "draft",
                "config": config if isinstance(config, dict) else {},
                "created_at": now,
                "updated_at": now,
                "updated_by": author,
                "published_version": None,
                "versions": [
                    {
                        "version": 1,
                        "state": "draft",
                        "config": config if isinstance(config, dict) else {},
                        "created_at": now,
                        "created_by": author,
                    }
                ],
            }
            payload["items"][normalized].append(item)
            self._append_audit(
                payload=payload,
                action="create",
                entity_type=normalized,
                item_id=item["id"],
                author=author,
                diff_text=_build_diff({}, item["config"]),
                workflow_to="draft",
            )
            self._write_payload(payload)
            return deepcopy(item)

    def update_item(self, entity_type: str, item_id: str, *, title: str, config: dict[str, Any], author: str) -> dict[str, Any]:
        with self._lock:
            normalized = self._validate_entity_type(entity_type)
            payload = self._read_payload()
            item = self._find_item(payload, normalized, item_id)
            if item is None:
                raise KeyError("not_found")
            before_config = deepcopy(item.get("config") or {})
            item["title"] = str(title or item.get("title") or "").strip() or "Untitled"
            item["config"] = config if isinstance(config, dict) else {}
            item["updated_at"] = _utc_now()
            item["updated_by"] = author
            versions = item.setdefault("versions", [])
            next_version = (int(versions[-1].get("version") or 0) + 1) if versions else 1
            versions.append(
                {
                    "version": next_version,
                    "state": item.get("state") or "draft",
                    "config": deepcopy(item["config"]),
                    "created_at": item["updated_at"],
                    "created_by": author,
                }
            )
            self._append_audit(
                payload=payload,
                action="update",
                entity_type=normalized,
                item_id=item_id,
                author=author,
                diff_text=_build_diff(before_config, item["config"]),
            )
            self._write_payload(payload)
            return deepcopy(item)

    def delete_item(self, entity_type: str, item_id: str, *, author: str) -> None:
        with self._lock:
            normalized = self._validate_entity_type(entity_type)
            payload = self._read_payload()
            items = payload["items"][normalized]
            index = next((i for i, item in enumerate(items) if str(item.get("id")) == item_id), -1)
            if index < 0:
                raise KeyError("not_found")
            removed = items.pop(index)
            self._append_audit(
                payload=payload,
                action="delete",
                entity_type=normalized,
                item_id=item_id,
                author=author,
                diff_text=_build_diff(removed.get("config") or {}, {}),
                workflow_from=str(removed.get("state") or ""),
            )
            self._write_payload(payload)

    def transition_item(self, entity_type: str, item_id: str, *, target_state: str, author: str) -> dict[str, Any]:
        with self._lock:
            normalized = self._validate_entity_type(entity_type)
            target = str(target_state or "").strip().lower()
            if target not in ALLOWED_STATES:
                raise ValueError("unsupported_state")
            payload = self._read_payload()
            item = self._find_item(payload, normalized, item_id)
            if item is None:
                raise KeyError("not_found")
            prev = str(item.get("state") or "draft")
            allowed = {
                "draft": {"review"},
                "review": {"publish", "draft"},
                "publish": {"draft"},
            }
            if target not in allowed.get(prev, set()):
                raise ValueError("invalid_transition")
            item["state"] = target
            item["updated_at"] = _utc_now()
            item["updated_by"] = author
            if target == "publish":
                versions = item.get("versions") or []
                if versions:
                    item["published_version"] = int(versions[-1].get("version") or 0)
            self._append_audit(
                payload=payload,
                action="workflow",
                entity_type=normalized,
                item_id=item_id,
                author=author,
                diff_text="",
                workflow_from=prev,
                workflow_to=target,
            )
            self._write_payload(payload)
            return deepcopy(item)

    def rollback_item(self, entity_type: str, item_id: str, *, version: int, author: str) -> dict[str, Any]:
        with self._lock:
            normalized = self._validate_entity_type(entity_type)
            payload = self._read_payload()
            item = self._find_item(payload, normalized, item_id)
            if item is None:
                raise KeyError("not_found")
            versions = item.get("versions") or []
            snapshot = next((v for v in versions if int(v.get("version") or 0) == int(version)), None)
            if snapshot is None:
                raise KeyError("version_not_found")
            before_config = deepcopy(item.get("config") or {})
            item["config"] = deepcopy(snapshot.get("config") or {})
            item["state"] = "draft"
            item["updated_at"] = _utc_now()
            item["updated_by"] = author
            versions.append(
                {
                    "version": int(versions[-1].get("version") or 0) + 1 if versions else 1,
                    "state": "draft",
                    "config": deepcopy(item["config"]),
                    "created_at": item["updated_at"],
                    "created_by": author,
                    "rollback_from": int(version),
                }
            )
            self._append_audit(
                payload=payload,
                action="rollback",
                entity_type=normalized,
                item_id=item_id,
                author=author,
                diff_text=_build_diff(before_config, item["config"]),
                workflow_from="publish",
                workflow_to="draft",
            )
            self._write_payload(payload)
            return deepcopy(item)

    def recent_audit(self, limit: int = 100, entity_type: str = "") -> list[dict[str, Any]]:
        with self._lock:
            payload = self._read_payload()
            events = list(payload.get("audit") or [])
            normalized = str(entity_type or "").strip().lower()
            if normalized:
                events = [item for item in events if str(item.get("entity_type") or "") == normalized]
            events = sorted(events, key=lambda item: str(item.get("created_at") or ""), reverse=True)
            return deepcopy(events[: max(1, int(limit or 100))])


_DEFAULT_STORE: AdminCatalogStore | None = None


def get_default_admin_catalog_store() -> AdminCatalogStore:
    global _DEFAULT_STORE
    if _DEFAULT_STORE is None:
        _DEFAULT_STORE = AdminCatalogStore()
    return _DEFAULT_STORE

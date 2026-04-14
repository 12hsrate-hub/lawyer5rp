from __future__ import annotations

from copy import deepcopy
from typing import Any


def find_active_law_rebuild_task(*, tasks: dict[str, dict[str, Any]], server_code: str) -> dict[str, Any] | None:
    for item in tasks.values():
        if not isinstance(item, dict):
            continue
        if str(item.get("scope") or "") != "law_sources_rebuild":
            continue
        if str(item.get("server_code") or "") != server_code:
            continue
        status_value = str(item.get("status") or "").lower()
        if status_value in {"queued", "running"}:
            return deepcopy(item)
    return None

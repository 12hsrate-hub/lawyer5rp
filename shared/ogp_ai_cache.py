from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _default_cache_dir() -> Path:
    root_dir = Path(__file__).resolve().parents[1]
    return root_dir / "web" / "data" / "ai_cache"


@dataclass(frozen=True)
class AiCacheKey:
    operation: str
    model: str
    payload_hash: str


class AiCache:
    def __init__(self, *, enabled: bool, base_dir: Path):
        self.enabled = enabled
        self.base_dir = base_dir

    @classmethod
    def from_env(cls) -> "AiCache":
        enabled = _is_truthy(os.getenv("OGP_AI_CACHE_ENABLED", "0"))
        base_dir_raw = os.getenv("OGP_AI_CACHE_DIR", "").strip()
        base_dir = Path(base_dir_raw) if base_dir_raw else _default_cache_dir()
        return cls(enabled=enabled, base_dir=base_dir)

    def build_key(self, *, operation: str, model: str, payload: Any) -> AiCacheKey:
        normalized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        payload_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return AiCacheKey(operation=operation, model=model, payload_hash=payload_hash)

    def get(self, key: AiCacheKey) -> Any | None:
        if not self.enabled:
            return None
        path = self._path_for(key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def set(self, key: AiCacheKey, value: Any) -> None:
        if not self.enabled:
            return
        path = self._path_for(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            return

    def _path_for(self, key: AiCacheKey) -> Path:
        safe_operation = key.operation.replace("/", "_").replace("\\", "_")
        safe_model = key.model.replace("/", "_").replace("\\", "_")
        return self.base_dir / safe_operation / safe_model / f"{key.payload_hash}.json"


def get_ai_cache() -> AiCache:
    return AiCache.from_env()

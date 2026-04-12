from __future__ import annotations

import hashlib
import json
import os
import time
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
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if isinstance(payload, dict) and "_meta" in payload and "value" in payload:
            meta = payload.get("_meta") if isinstance(payload.get("_meta"), dict) else {}
            expires_at = meta.get("expires_at")
            try:
                expires_at_float = float(expires_at) if expires_at not in (None, "") else 0.0
            except (TypeError, ValueError):
                expires_at_float = 0.0
            if expires_at_float > 0 and time.time() >= expires_at_float:
                try:
                    path.unlink(missing_ok=True)
                except Exception:
                    pass
                return None
            return payload.get("value")
        return payload

    def set(self, key: AiCacheKey, value: Any, *, ttl_seconds: int | None = None) -> None:
        if not self.enabled:
            return
        path = self._path_for(key)
        ttl_value = None
        if ttl_seconds is not None:
            try:
                ttl_value = int(ttl_seconds)
            except (TypeError, ValueError):
                ttl_value = None
        expires_at = 0.0
        if ttl_value is not None and ttl_value > 0:
            expires_at = time.time() + ttl_value
        payload = {
            "_meta": {
                "created_at": time.time(),
                "ttl_seconds": ttl_value or 0,
                "expires_at": expires_at,
            },
            "value": value,
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            return

    def _path_for(self, key: AiCacheKey) -> Path:
        safe_operation = key.operation.replace("/", "_").replace("\\", "_")
        safe_model = key.model.replace("/", "_").replace("\\", "_")
        return self.base_dir / safe_operation / safe_model / f"{key.payload_hash}.json"


def get_ai_cache() -> AiCache:
    return AiCache.from_env()

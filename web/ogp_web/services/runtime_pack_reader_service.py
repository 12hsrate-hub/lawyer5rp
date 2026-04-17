from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ogp_web.server_config import effective_server_pack
from ogp_web.services.law_sources_validation import normalize_source_urls


@dataclass(frozen=True)
class RuntimePackSnapshot:
    server_code: str
    pack: dict[str, Any]
    metadata: dict[str, Any]
    resolution_mode: str
    source_label: str

    @property
    def pack_version(self) -> int | None:
        return int(self.pack.get("version") or 0) or None

    @property
    def has_published_pack(self) -> bool:
        return self.resolution_mode == "published_pack"

    @property
    def uses_bootstrap_pack(self) -> bool:
        return self.resolution_mode == "bootstrap_pack"

    @property
    def uses_neutral_fallback(self) -> bool:
        return self.resolution_mode == "neutral_fallback"

    def to_payload(self) -> dict[str, object]:
        return {
            "server_code": self.server_code,
            "pack_version": self.pack_version,
            "resolution_mode": self.resolution_mode,
            "source_label": self.source_label,
            "has_published_pack": self.has_published_pack,
            "uses_bootstrap_pack": self.uses_bootstrap_pack,
            "uses_neutral_fallback": self.uses_neutral_fallback,
        }


def read_runtime_pack_snapshot(*, server_code: str) -> RuntimePackSnapshot:
    normalized_server = str(server_code or "").strip().lower()
    pack = effective_server_pack(normalized_server)
    metadata = dict(pack.get("metadata") or {}) if isinstance(pack, dict) else {}
    if pack.get("id") is not None:
        resolution_mode = "published_pack"
        source_label = "published pack"
    elif metadata:
        resolution_mode = "bootstrap_pack"
        source_label = "bootstrap pack"
    else:
        resolution_mode = "neutral_fallback"
        source_label = "neutral fallback"
    return RuntimePackSnapshot(
        server_code=normalized_server,
        pack=dict(pack or {}),
        metadata=metadata,
        resolution_mode=resolution_mode,
        source_label=source_label,
    )


def resolve_runtime_pack_law_sources(*, server_code: str) -> tuple[str, ...]:
    snapshot = read_runtime_pack_snapshot(server_code=server_code)
    return normalize_source_urls(snapshot.metadata.get("law_qa_sources") or ())


def resolve_runtime_pack_law_bundle_path(*, server_code: str) -> str:
    snapshot = read_runtime_pack_snapshot(server_code=server_code)
    return str(snapshot.metadata.get("law_qa_bundle_path") or "").strip()


def resolve_runtime_pack_feature_flags(*, server_code: str) -> tuple[str, ...]:
    snapshot = read_runtime_pack_snapshot(server_code=server_code)
    values = {
        str(item or "").strip()
        for item in (snapshot.metadata.get("feature_flags") or ())
        if str(item or "").strip()
    }
    return tuple(sorted(values))

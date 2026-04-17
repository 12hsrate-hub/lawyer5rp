from __future__ import annotations

import json
from pathlib import Path


def blackberry_published_pack() -> dict[str, object]:
    path = Path(__file__).resolve().parents[1] / "web" / "ogp_web" / "server_config" / "packs" / "blackberry.bootstrap.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["id"] = 101
    payload["version"] = int(payload.get("version") or 1)
    payload["status"] = "published"
    return payload


def orange_published_pack() -> dict[str, object]:
    path = Path(__file__).resolve().parents[1] / "web" / "ogp_web" / "server_config" / "packs" / "orange.bootstrap.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["id"] = int(payload.get("id") or 202)
    payload["status"] = "published"
    return payload

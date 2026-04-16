from __future__ import annotations

import json
from pathlib import Path


def orange_published_pack() -> dict[str, object]:
    path = Path(__file__).resolve().parents[1] / "web" / "ogp_web" / "server_config" / "packs" / "orange.bootstrap.json"
    return json.loads(path.read_text(encoding="utf-8"))

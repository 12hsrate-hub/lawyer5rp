from __future__ import annotations

import os
from pathlib import Path

from fastapi.templating import Jinja2Templates


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
STATIC_ASSET_VERSION = os.getenv("OGP_STATIC_ASSET_VERSION", "20260414-law-qa-submit-fix-1")


def _normalized_url(value: str) -> str:
    return str(value or "").strip().rstrip("/")


def page_context(**extra: object) -> dict[str, object]:
    public_base_url = _normalized_url(os.getenv("OGP_WEB_BASE_URL", "https://www.lawyer5rp.online"))
    alternate_public_base_url = _normalized_url(
        os.getenv("OGP_WEB_ALTERNATE_BASE_URL", "https://www.lawyer5rp.su")
    )
    server_name = str(extra.get("server_name") or "BlackBerry")
    app_title = str(extra.get("app_title") or "OGP Builder Web")
    context: dict[str, object] = {
        "app_title": app_title,
        "openai_enabled": bool(os.getenv("OPENAI_API_KEY")),
        "is_admin": False,
        "static_asset_version": STATIC_ASSET_VERSION,
        "public_base_url": public_base_url,
        "alternate_public_base_url": alternate_public_base_url,
        "server_name": server_name,
        "page_nav_items": [],
        "complaint_nav_items": [],
    }
    context.update(extra)
    return context

from __future__ import annotations

import json
import logging
from typing import Any


LOGGER = logging.getLogger(__name__)


def load_profile_json(raw_profile: str | None, defaults: dict[str, str]) -> dict[str, str]:
    if not raw_profile:
        return defaults.copy()
    try:
        profile = json.loads(raw_profile)
    except json.JSONDecodeError as exc:
        LOGGER.warning("Profile JSON corrupted, falling back to defaults: %s | raw=%r", exc, raw_profile[:160])
        return defaults.copy()
    if not isinstance(profile, dict):
        LOGGER.warning("Profile JSON is not a dict (type=%s), falling back to defaults", type(profile).__name__)
        return defaults.copy()
    return {
        key: str(profile.get(key, "") or "").strip()
        for key in defaults
    }


def dump_profile_json(profile: dict[str, Any], defaults: dict[str, str]) -> str:
    sanitized = {
        key: str(profile.get(key, "") or "").strip()
        for key in defaults
    }
    return json.dumps(sanitized, ensure_ascii=False)

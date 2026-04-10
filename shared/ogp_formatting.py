from __future__ import annotations

import re
from typing import List, Tuple
from urllib.parse import urlparse

from shared.ogp_constants import PHONE_DIGITS_PATTERN, VIDEO_FIXED_LABEL, VIDEO_PROVIDED_LABEL


def _record_part_label(index: int) -> str:
    labels = {
        1: "первая часть записи",
        2: "вторая часть записи",
        3: "третья часть записи",
        4: "четвертая часть записи",
        5: "пятая часть записи",
    }
    return labels.get(index, f"часть записи №{index}")


def normalize_discord_to_email(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if "@" in raw:
        return raw
    return f"{raw}@sa.com"


def is_valid_http_url(url: str) -> bool:
    raw = (url or "").strip()
    if not raw:
        return False
    parsed = urlparse(raw)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def sanitize_url(url: str) -> str:
    return (url or "").strip().replace("'", "%27")


def escape_bbcode_text(value: str) -> str:
    raw = str(value or "").strip()
    return raw.replace("[", "(").replace("]", ")")


def normalize_phone_digits(value: str) -> str:
    raw = (value or "").strip()
    return re.sub(r"\D", "", raw)


def format_phone_for_bbcode(value: str) -> str:
    digits = normalize_phone_digits(value)
    if PHONE_DIGITS_PATTERN.fullmatch(digits):
        return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"
    return str(value or "").strip()


def bb_url(url: str, title: str) -> str:
    return f"[URL='{sanitize_url(url)}']{escape_bbcode_text(title)}[/URL]"


def build_evidence_line(evidence_items: List[Tuple[str, str]]) -> str:
    parts = [bb_url(url, title) for title, url in evidence_items if (url or "").strip()]
    return ", ".join(parts) + "." if parts else ""


def collect_evidence_items(
    contract_url: str = "",
    bar_request_url: str = "",
    official_answer_url: str = "",
    mail_notice_url: str = "",
    arrest_record_url: str = "",
    personnel_file_url: str = "",
    video_fix_urls: List[str] | None = None,
    provided_video_urls: List[str] | None = None,
) -> List[Tuple[str, str]]:
    mapping = [
        ("Договор на оказание юридических услуг", contract_url),
        ("Адвокатский запрос", bar_request_url),
        ("Официальный ответ на адвокатский запрос", official_answer_url),
        ("Уведомление посредством почты", mail_notice_url),
        ("Запись об аресте", arrest_record_url),
        ("Личное дело", personnel_file_url),
    ]

    for index, url in enumerate(video_fix_urls or [], start=1):
        if (url or "").strip():
            mapping.append((f"{VIDEO_FIXED_LABEL}: {_record_part_label(index)}", url))

    for index, url in enumerate(provided_video_urls or [], start=1):
        if (url or "").strip():
            mapping.append((f"{VIDEO_PROVIDED_LABEL}: {_record_part_label(index)}", url))

    return [(title, url.strip()) for title, url in mapping if (url or "").strip()]

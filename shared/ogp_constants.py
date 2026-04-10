from __future__ import annotations

import re
from typing import List, Tuple


DT_PATTERN = re.compile(r"^\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}$")
DATE_PATTERN = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
PHONE_DIGITS_PATTERN = re.compile(r"^\d{7}$")

DEFAULT_SITUATION_PLACEHOLDER = "%%SITUATION_DESCRIPTION%%"
DEFAULT_VIOLATION_PLACEHOLDER = "%%VIOLATION_SHORT%%"

BASE_EVIDENCE_FIELDS: List[Tuple[str, str]] = [
    ("contract_url", "Договор на оказание юридических услуг"),
    ("bar_request_url", "Адвокатский запрос"),
    ("official_answer_url", "Официальный ответ на адвокатский запрос"),
    ("mail_notice_url", "Уведомление посредством почты"),
    ("arrest_record_url", "Запись об аресте"),
    ("personnel_file_url", "Личное дело"),
]

VIDEO_FIXED_LABEL = "Видеофиксация процессуальных действий"
VIDEO_PROVIDED_LABEL = "Предоставленная запись процессуальных действий"

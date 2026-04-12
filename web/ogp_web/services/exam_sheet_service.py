from __future__ import annotations

import csv
import io
import json
import time
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

import httpx
from fastapi import HTTPException, status


EXAM_SHEET_ID = "1JpmG1N30TvVs-1P9kp00MDhzBnIxUG-HgAlcAW_cwn4"
EXAM_SHEET_NAME = "Ответы на экзамены"
EXAM_SHEET_URL = f"https://docs.google.com/spreadsheets/d/{EXAM_SHEET_ID}/edit?usp=sharing"
EXAM_SHEET_CSV_URL = (
    f"https://docs.google.com/spreadsheets/d/{EXAM_SHEET_ID}/gviz/tq"
    f"?tqx=out:csv&sheet={quote(EXAM_SHEET_NAME)}"
)
EXAM_BASE_COLUMNS = 5
EXAM_REFERENCE_ROW_MARKER = "эталонные ответы"
EXAM_ANSWER_KEY_PATH = Path(__file__).resolve().parents[1] / "exam_answer_key.json"
EXAM_QUESTION_COLUMNS_PATH = Path(__file__).resolve().parents[1] / "exam_question_columns.json"
EXAM_SHEET_CACHE_TTL = 300  # секунд
EXAM_LICENSE_TYPE = "Получение лицензии адвоката"
EXAM_STATE_TYPE = "Государственный адвокат"

EXAM_KEY_POINTS: dict[str, list[str]] = {
    "F": ["АК и ДК", "залог определяется по санкции инкриминируемой статьи"],
    "G": ["при нескольких статьях берется наибольшая сумма залога"],
    "H": ["если хотя бы одна статья без суммы залога, выпуск под залог запрещен"],
    "I": ["залог запрещен при указании постановления ОГП", "залог запрещен при указании решения суда"],
    "J": ['п. "в" ст. 23 ПК'],
    "K": ["ч. 1 ст. 22 АК"],
    "L": ["право на адвоката не реализуется при задержании по приказам высших должностных лиц / ордерам / иным нормативным документам"],
    "M": ["48 часов через ОГП", "72 часа через суд", "7 дней только в исключительно мотивированных случаях"],
    "N": ["для обоих режимов: КПЗ LSPD, КПЗ LSSD, Федеральная тюрьма (блок оформления)", 'только для "Государственный адвокат": Мэрия Los-Santos и округ Блейн'],
    "O": ["адвокатская тайна = любые сведения, связанные с оказанием юридической помощи доверителю"],
    "P": ["необходимая оборона", "причинение вреда при задержании лица, совершившего преступление", "крайняя необходимость", "обоснованный риск", "исполнение приказа или распоряжения"],
    "Q": ["при трафик-стопе", "при обыске / досмотре вне задержания"],
    "R": ["лицо считается невиновным, пока вина не доказана", "не обязано доказывать невиновность", "сомнения толкуются в пользу обвиняемого", "обвинительный приговор не может быть основан на предположениях", "исключение: BOLO"],
    "S": ['для "Государственный адвокат": при исполнении прямых обязанностей, реагировании на запрос адвоката, представлении интересов в суде, внесении залога, юридической консультации', 'для "Получение лицензии адвоката": неприкосновенность не действует, кроме представления интересов в суде'],
    "T": ["ОГП", "руководство Коллегии адвокатов", "судья / судейская коллегия"],
    "U": ["ч. 1 ст. 48 АК", "4 дня не образуют нужный рецидив при штрафе"],
    "V": ["сотрудник не прав / задержание неправомерно", "после исполнения требования визор можно снова опустить"],
    "W": ["задержание недопустимо / офицер не прав", "почта — исключение по ст. 18 АК"],
    "X": ["договор на юр. услуги", "запись об отправке уведомления по почте", "адвокатский запрос", "доказательства ареста либо сам факт процессуальных действий", "ответ руководства, если имеется"],
    "Y": ["нужно потребовать документы на право ношения оружия", "ч. 3 ст. 16 ПК", "не переходить сразу к задержанию"],
    "Z": ["нарушение прецедента Asandr Dark", "требование должно быть корректным, четким и официально-деловым", "нарушение ч. 4 ст. 29 ПК", "должны быть названы основания обыска / досмотра вне задержания"],
    "AA": ["нет, это не основание для освобождения", "ст. 20 ПК"],
    "AB": ["запросить подтверждение отсутствия денег", "выписка / F10", "при подтверждении ссылаться на ст. 6 ч. 4 АК"],
    "AC": ["задержание неправомерно", 'п. "б" ст. 18 АК', "маски допустимы в развлекательных учреждениях и на прилегающей территории, включая казино"],
    "AD": ["Поправка 7 к Конституции", "незнание закона не освобождает от ответственности"],
}

_sheet_cache: list[dict[str, object]] | None = None
_sheet_cache_at: float = 0.0


def _column_to_index(column: str) -> int:
    value = 0
    for symbol in str(column or "").strip().upper():
        if "A" <= symbol <= "Z":
            value = value * 26 + (ord(symbol) - ord("A") + 1)
    return value


def _normalize_match_text(value: str) -> str:
    text = str(value or "").lower().replace("ё", "е")
    normalized_chars: list[str] = []
    for char in text:
        if char.isalnum() or char.isspace():
            normalized_chars.append(char)
        else:
            normalized_chars.append(" ")
    return " ".join("".join(normalized_chars).split())


def _detect_question_start_index(headers: list[str]) -> int:
    for index, header in enumerate(headers):
        normalized = str(header or "").strip().lower()
        if normalized in {"формат экзамена", "format", "exam_format"}:
            return index + 1
    return EXAM_BASE_COLUMNS


def _is_reference_marker(value: object) -> bool:
    return _normalize_match_text(str(value or "")) == _normalize_match_text(EXAM_REFERENCE_ROW_MARKER)


def _is_non_scoring_header(header: str) -> bool:
    normalized = str(header or "").strip().lower()
    if not normalized:
        return True
    blocked_fragments = (
        "отметка времени",
        "submitted",
        "time",
        "ваше имя",
        "имя/фамилия",
        "full_name",
        "discord",
        "passport",
        "номер паспорта",
        "формат экзамена",
        "exam_format",
        "exam_type",
        "format",
    )
    return any(fragment in normalized for fragment in blocked_fragments)


def build_exam_correct_answers_from_payload(payload: dict[str, str]) -> dict[str, str]:
    items = list((payload or {}).items())
    question_start_index = _detect_question_start_index([str(header) for header, _ in items])
    answers: dict[str, str] = {}
    question_offset = 0
    for index, (header, answer) in enumerate(items):
        if index < question_start_index:
            continue
        if _is_non_scoring_header(str(header)):
            continue
        logical_index = EXAM_BASE_COLUMNS + question_offset
        question_offset += 1
        value = str(answer or "").strip()
        if not value:
            continue
        column = _column_letter(logical_index).upper()
        answers[column] = value
    return answers


def is_exam_reference_payload(
    payload: dict[str, object] | None,
    *,
    full_name: object = "",
    exam_format: object = "",
) -> bool:
    candidates: list[object] = [full_name, exam_format]
    if isinstance(payload, dict):
        for key in ("full_name", "exam_format", "format", "exam_type_extra"):
            candidates.append(payload.get(key))
        for header, value in payload.items():
            normalized_header = _normalize_match_text(str(header))
            if not normalized_header:
                continue
            if normalized_header in {"full name", "exam format", "format", "exam_type_extra"}:
                candidates.append(value)
                continue
            if "ваше имя" in normalized_header or "имя фамилия" in normalized_header:
                candidates.append(value)
                continue
            if "формат экзамена" in normalized_header:
                candidates.append(value)
    return any(_is_reference_marker(candidate) for candidate in candidates)


def is_exam_reference_row(row: dict[str, object] | None) -> bool:
    if not isinstance(row, dict):
        return False
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else None
    return is_exam_reference_payload(
        payload,
        full_name=row.get("full_name"),
        exam_format=row.get("exam_format"),
    )


@lru_cache(maxsize=1)
def load_exam_correct_answers() -> dict[str, str]:
    with EXAM_ANSWER_KEY_PATH.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    normalized: dict[str, str] = {}
    for column, answer in data.items():
        key = str(column).strip().upper()
        if not key:
            continue
        if answer is None:
            continue
        value = str(answer).strip()
        if not value:
            continue
        normalized[key] = value
    return normalized


@lru_cache(maxsize=1)
def load_exam_question_fragments() -> dict[str, list[str]]:
    with EXAM_QUESTION_COLUMNS_PATH.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    normalized: dict[str, list[str]] = {}
    for raw_column, raw_fragments in dict(data or {}).items():
        column = str(raw_column or "").strip().upper()
        if not column:
            continue
        fragments: list[str] = []
        for fragment in list(raw_fragments or []):
            normalized_fragment = _normalize_match_text(str(fragment or ""))
            if normalized_fragment:
                fragments.append(normalized_fragment)
        if fragments:
            normalized[column] = fragments
    return normalized


def _extract_exam_type(payload: dict[str, str]) -> str:
    direct_value = payload.get("Формат экзамена") or payload.get("format") or payload.get("exam_format")
    if direct_value:
        return normalize_exam_type(direct_value)
    for header, value in payload.items():
        normalized_header = _normalize_match_text(str(header))
        if "формат экзамена" in normalized_header or normalized_header == "exam format":
            return normalize_exam_type(value)
    return ""


def _map_payload_answers_by_column(payload: dict[str, str], columns: list[str]) -> dict[str, tuple[str, str]]:
    question_entries: list[tuple[str, str, str]] = []
    for header, value in payload.items():
        header_text = str(header or "").strip()
        if _is_non_scoring_header(header_text):
            continue
        question_entries.append((header_text, str(value or "").strip(), _normalize_match_text(header_text)))

    by_column: dict[str, tuple[str, str]] = {}
    used_headers: set[str] = set()
    fragments_by_column = load_exam_question_fragments()
    for column in columns:
        fragments = fragments_by_column.get(column, [])
        if not fragments:
            continue
        for header, answer, normalized_header in question_entries:
            if header in used_headers:
                continue
            if any(fragment in normalized_header for fragment in fragments):
                by_column[column] = (header, answer)
                used_headers.add(header)
                break

    fallback_entries = [(header, answer) for header, answer, _ in question_entries if header not in used_headers]
    unresolved_columns = [column for column in columns if column not in by_column]
    for index, column in enumerate(unresolved_columns):
        if index >= len(fallback_entries):
            break
        by_column[column] = fallback_entries[index]
    return by_column


def _normalize_headers(raw_headers: list[str]) -> list[str]:
    return [str(header or "").strip() or f"column_{index + 1}" for index, header in enumerate(raw_headers)]


def _column_letter(index: int) -> str:
    result = ""
    current = index
    while current >= 0:
        result = chr(ord("A") + (current % 26)) + result
        current = current // 26 - 1
    return result


def normalize_exam_type(raw_value: object) -> str:
    value = str(raw_value or "").strip()
    lowered = value.lower()
    if "государ" in lowered:
        return EXAM_STATE_TYPE
    if "лиценз" in lowered:
        return EXAM_LICENSE_TYPE
    return value


def parse_exam_sheet_csv(csv_text: str) -> list[dict[str, object]]:
    reader = list(csv.reader(io.StringIO(csv_text)))
    if not reader:
        return []

    headers = _normalize_headers(reader[0])
    question_start_index = _detect_question_start_index(headers)
    rows: list[dict[str, object]] = []
    for index, row in enumerate(reader[1:], start=2):
        if not any(str(cell or "").strip() for cell in row):
            continue

        normalized = list(row[: len(headers)])
        if len(normalized) < len(headers):
            normalized.extend([""] * (len(headers) - len(normalized)))

        payload = {
            header: str(normalized[column_index] or "").strip()
            for column_index, header in enumerate(headers)
        }
        rows.append(
            {
                "source_row": index,
                "submitted_at": payload.get(headers[0], ""),
                "full_name": payload.get(headers[1], ""),
                "discord_tag": payload.get(headers[2], ""),
                "passport": payload.get(headers[3], ""),
                "exam_format": payload.get(headers[4], ""),
                "answer_count": max(len(headers) - question_start_index, 0),
                "payload": payload,
            }
        )
    return rows


def fetch_exam_sheet_rows(*, force_refresh: bool = False) -> list[dict[str, object]]:
    global _sheet_cache, _sheet_cache_at

    now = time.monotonic()
    if not force_refresh and _sheet_cache is not None and (now - _sheet_cache_at) < EXAM_SHEET_CACHE_TTL:
        return _sheet_cache

    try:
        response = httpx.get(EXAM_SHEET_CSV_URL, timeout=30.0, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=["Не удалось получить данные из Google Sheets."],
        ) from exc

    rows = parse_exam_sheet_csv(response.text)
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=["В таблице не найдено строк с ответами."],
        )

    _sheet_cache = rows
    _sheet_cache_at = now
    return rows


def build_exam_score_items(payload: dict[str, str], *, correct_answers: dict[str, str] | None = None) -> list[dict[str, str]]:
    answer_key = dict(load_exam_correct_answers())
    if correct_answers:
        for column, answer in correct_answers.items():
            key = str(column or "").strip().upper()
            value = str(answer or "").strip()
            if key and value:
                answer_key[key] = value
    ordered_columns = sorted(answer_key.keys(), key=_column_to_index)
    mapped_answers = _map_payload_answers_by_column(payload, ordered_columns)
    exam_type = _extract_exam_type(payload)
    scored_items: list[dict[str, str]] = []
    for column in ordered_columns:
        correct_answer = answer_key.get(column)
        if not correct_answer:
            continue
        mapped_item = mapped_answers.get(column)
        if mapped_item is None:
            continue
        header, user_answer = mapped_item
        scored_items.append(
            {
                "column": column,
                "exam_type": exam_type,
                "question": str(header),
                "header": str(header),
                "user_answer": str(user_answer or "").strip(),
                "correct_answer": correct_answer,
                "key_points": list(EXAM_KEY_POINTS.get(column, [])),
            }
        )
    return scored_items

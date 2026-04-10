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
EXAM_ANSWER_KEY_PATH = Path(__file__).resolve().parents[1] / "exam_answer_key.json"
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
                "answer_count": max(len(headers) - EXAM_BASE_COLUMNS, 0),
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


def build_exam_score_items(payload: dict[str, str]) -> list[dict[str, str]]:
    answer_key = load_exam_correct_answers()
    items = list(payload.items())
    exam_type = normalize_exam_type(payload.get("Формат экзамена") or payload.get("format") or payload.get("exam_format"))
    scored_items: list[dict[str, str]] = []
    for index, (header, user_answer) in enumerate(items):
        if index < EXAM_BASE_COLUMNS:
            continue
        column = _column_letter(index)
        correct_answer = answer_key.get(column)
        if not correct_answer:
            continue
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

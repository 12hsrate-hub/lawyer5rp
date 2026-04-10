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

_sheet_cache: list[dict[str, object]] | None = None
_sheet_cache_at: float = 0.0


@lru_cache(maxsize=1)
def load_exam_correct_answers() -> dict[str, str]:
    with EXAM_ANSWER_KEY_PATH.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return {str(column).strip().upper(): str(answer).strip() for column, answer in data.items()}


def _normalize_headers(raw_headers: list[str]) -> list[str]:
    return [str(header or "").strip() or f"column_{index + 1}" for index, header in enumerate(raw_headers)]


def _column_letter(index: int) -> str:
    result = ""
    current = index
    while current >= 0:
        result = chr(ord("A") + (current % 26)) + result
        current = current // 26 - 1
    return result


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
                "header": str(header),
                "user_answer": str(user_answer or "").strip(),
                "correct_answer": correct_answer,
            }
        )
    return scored_items

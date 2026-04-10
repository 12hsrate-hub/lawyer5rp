from __future__ import annotations

from datetime import datetime
from typing import List

from shared.ogp_constants import DATE_PATTERN, DT_PATTERN, PHONE_DIGITS_PATTERN
from shared.ogp_formatting import is_valid_http_url, normalize_phone_digits
from shared.ogp_types import ComplaintInput, RehabInput


def validate_event_dt(event_dt: str) -> str | None:
    raw = (event_dt or "").strip()
    if not DT_PATTERN.match(raw):
        return "Дата и время события должны быть в формате ДД.ММ.ГГГГ ЧЧ:ММ."
    try:
        datetime.strptime(raw, "%d.%m.%Y %H:%M")
    except ValueError:
        return "Указана несуществующая дата или время."
    return None


def validate_date_only(value: str, label: str) -> str | None:
    raw = (value or "").strip()
    if not DATE_PATTERN.match(raw):
        return f"{label} должна быть в формате ДД.ММ.ГГГГ."
    try:
        datetime.strptime(raw, "%d.%m.%Y")
    except ValueError:
        return f"Указана несуществующая дата: {label}."
    return None


def validate_appeal_no(value: str) -> str | None:
    raw = (value or "").strip()
    if len(raw) != 4 or not raw.isdigit():
        return "Номер обращения должен содержать ровно 4 цифры."
    return None


def validate_passport_value(label: str, value: str) -> str | None:
    raw = (value or "").strip()
    if raw and len(raw) > 6:
        return f"{label} должен содержать не более 6 символов."
    return None


def validate_phone_value(label: str, value: str) -> str | None:
    raw = (value or "").strip()
    if raw and not PHONE_DIGITS_PATTERN.fullmatch(normalize_phone_digits(raw)):
        return f"{label} должен содержать ровно 7 цифр."
    return None


def validate_complaint_input(data: ComplaintInput) -> List[str]:
    missing: List[str] = []

    rep_required = [
        ("Профиль: ФИО представителя", data.representative.name),
        ("Профиль: паспорт", data.representative.passport),
        ("Профиль: адрес", data.representative.address),
        ("Профиль: телефон", data.representative.phone),
        ("Профиль: Discord", data.representative.discord),
        ("Профиль: скан паспорта (URL)", data.representative.passport_scan_url),
    ]
    missing.extend(name for name, value in rep_required if not (value or "").strip())

    required = [
        ("Номер обращения", data.appeal_no),
        ("Организация", data.org),
        ("Объект заявления", data.subject_names),
        ("ФИО потерпевшего", data.victim.name),
        ("Паспорт потерпевшего", data.victim.passport),
        ("Телефон потерпевшего", data.victim.phone),
        ("Discord потерпевшего", data.victim.discord),
        ("Скан паспорта потерпевшего (URL)", data.victim.passport_scan_url),
    ]
    missing.extend(name for name, value in required if not (value or "").strip())

    if not any(title == "Договор на оказание юридических услуг" for title, _ in data.evidence_items):
        missing.append("Договор (доказательство)")

    url_fields = [
        ("Скан паспорта представителя", data.representative.passport_scan_url),
        ("Скан паспорта потерпевшего", data.victim.passport_scan_url),
    ]
    url_fields.extend((title, url) for title, url in data.evidence_items)

    for title, url in url_fields:
        if not is_valid_http_url(url):
            missing.append(f"Некорректный URL: {title}")

    event_dt_error = validate_event_dt(data.event_dt)
    if event_dt_error:
        missing.append(event_dt_error)

    appeal_no_error = validate_appeal_no(data.appeal_no)
    if appeal_no_error:
        missing.append(appeal_no_error)

    field_errors = [
        validate_passport_value("Профиль: паспорт", data.representative.passport),
        validate_phone_value("Профиль: телефон", data.representative.phone),
        validate_passport_value("Паспорт потерпевшего", data.victim.passport),
        validate_phone_value("Телефон потерпевшего", data.victim.phone),
    ]
    missing.extend(error for error in field_errors if error)
    return missing


def validate_rehab_input(data: RehabInput) -> List[str]:
    missing: List[str] = []

    rep_required = [
        ("Профиль: ФИО представителя", data.representative.name),
        ("Профиль: паспорт", data.representative.passport),
        ("Профиль: телефон", data.representative.phone),
        ("Профиль: Discord", data.representative.discord),
        ("Профиль: скан паспорта (URL)", data.representative.passport_scan_url),
    ]
    missing.extend(name for name, value in rep_required if not (value or "").strip())

    required = [
        ("ФИО доверителя", data.principal_name),
        ("Паспорт доверителя", data.principal_passport),
        ("Скан паспорта доверителя", data.principal_passport_scan_url),
        ("Договор на оказание юридических услуг", data.contract_url),
    ]
    missing.extend(name for name, value in required if not (value or "").strip())

    field_errors = [
        validate_passport_value("Профиль: паспорт", data.representative.passport),
        validate_phone_value("Профиль: телефон", data.representative.phone),
        validate_passport_value("Паспорт доверителя", data.principal_passport),
    ]
    missing.extend(error for error in field_errors if error)

    url_fields = [
        ("Скан паспорта представителя", data.representative.passport_scan_url),
        ("Скан паспорта доверителя", data.principal_passport_scan_url),
        ("Договор на оказание юридических услуг", data.contract_url),
    ]
    for title, url in url_fields:
        if not is_valid_http_url(url):
            missing.append(f"Некорректный URL: {title}")

    return missing

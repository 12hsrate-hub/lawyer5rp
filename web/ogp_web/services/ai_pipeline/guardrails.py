from __future__ import annotations

import re


def clean_suggest_text(text: str) -> str:
    normalized = str(text or "").replace("\r\n", "\n").strip()
    if not normalized:
        return ""
    normalized = re.sub(r"```(?:[\w+-]+)?\s*([\s\S]*?)```", lambda match: match.group(1).strip(), normalized)
    normalized = re.sub(r"\n?\s*(?:источники|sources)\s*:\s*[\s\S]*$", "", normalized, flags=re.IGNORECASE)
    cleaned_lines: list[str] = []
    for raw_line in normalized.splitlines():
        line = raw_line.strip()
        if not line:
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
            continue
        if re.fullmatch(r"(?i)(?:пункт\s*3|описательная\s+часть\s+жалобы|текст\s+жалобы|вариант\s+текста|готовый\s+текст)", line):
            continue
        if re.match(r"(?i)^(?:вот|ниже|готовый|обновленный|переписанный)\b.*(?:текст|вариант|пункт\s*3)", line):
            continue
        line = re.sub(r"^[-*•]\s+", "", line)
        line = re.sub(r"^\d+\.\s+", "", line)
        cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def truncate_suggest_value(value: str, *, max_chars: int) -> str:
    normalized = str(value or "").strip()
    if max_chars <= 0 or len(normalized) <= max_chars:
        return normalized
    head = normalized[: max_chars + 1]
    split_index = head.rfind(" ")
    if split_index < max(0, int(max_chars * 0.6)):
        split_index = max_chars
    return head[:split_index].rstrip(" ,;:-") + "..."

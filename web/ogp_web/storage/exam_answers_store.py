from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
from typing import Any

from ogp_web.db.factory import get_database_backend
from ogp_web.db.types import DatabaseBackend
from ogp_web.services.exam_sheet_service import is_exam_reference_payload, is_exam_reference_row

ROOT_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT_DIR / "web" / "data"
DB_PATH = DATA_DIR / "exam_answers.db"
REFERENCE_SOURCE_ROW = 0
INVALID_BATCH_RATIONALE = "Модель не вернула корректную оценку по этому пункту."


class ExamAnswersStore:
    @staticmethod
    def _has_invalid_score_result(scores: list[dict[str, object]]) -> bool:
        for item in scores:
            rationale = str(item.get("rationale") or "").strip()
            if rationale == INVALID_BATCH_RATIONALE:
                return True
        return False

    @staticmethod
    def build_import_key(
        submitted_at: str,
        full_name: str,
        discord_tag: str,
        passport: str,
        exam_format: str,
    ) -> str:
        return "||".join(
            [
                str(submitted_at or "").strip(),
                str(full_name or "").strip(),
                str(discord_tag or "").strip(),
                str(passport or "").strip(),
                str(exam_format or "").strip(),
            ]
        )

    @staticmethod
    def _build_score_signature(*, payload: dict[str, object], exam_format: str) -> str:
        ordered_items = list((payload or {}).items())
        scoring_items: list[list[str]] = []
        for index, (header, value) in enumerate(ordered_items):
            if index < 5:
                continue
            header_text = str(header or "").strip()
            if not header_text:
                continue
            scoring_items.append([header_text, str(value or "").strip()])
        return json.dumps(
            {
                "exam_format": str(exam_format or "").strip(),
                "answers": scoring_items,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def __init__(self, db_path: Path, backend: DatabaseBackend | None = None):
        self.db_path = db_path
        self.backend = backend or get_database_backend()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self):
        return self.backend.connect()

    @property
    def is_postgres_backend(self) -> bool:
        return True

    def _placeholder(self) -> str:
        return "%s"

    def _cast_json_value(self, placeholder: str) -> str:
        return f"{placeholder}::jsonb"

    def _current_timestamp_sql(self) -> str:
        return "NOW()"

    def _needs_rescore_predicate(self) -> str:
        return "needs_rescore IS TRUE"

    def _json_present_predicate(self, column_name: str) -> str:
        return f"{column_name} IS NOT NULL AND {column_name}::text <> 'null'"

    def _bool_true_value(self) -> bool | int:
        return True

    def _decode_json_value(self, raw: Any, default: Any):
        if raw in (None, ""):
            return default
        if isinstance(raw, (dict, list)):
            return raw
        try:
            value = json.loads(str(raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            return default
        return value

    def _encode_json_value(self, value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _row_value(row: Any, key: str, default: Any = None) -> Any:
        if isinstance(row, dict):
            return row.get(key, default)
        try:
            return row[key]
        except (KeyError, TypeError, IndexError):
            return default

    def _build_existing_import_snapshot(self, row: Any) -> dict[str, object]:
        payload = self._decode_json_value(self._row_value(row, "payload_json"), {})
        if not isinstance(payload, dict):
            payload = {}
        exam_scores = self._decode_json_value(self._row_value(row, "exam_scores_json"), [])
        if not isinstance(exam_scores, list):
            exam_scores = []
        source_row = int(self._row_value(row, "source_row") or 0)
        submitted_at = str(self._row_value(row, "submitted_at") or "")
        return {
            "id": int(self._row_value(row, "id") or 0),
            "source_row": source_row,
            "submitted_at": submitted_at,
            "full_name": str(self._row_value(row, "full_name") or ""),
            "discord_tag": str(self._row_value(row, "discord_tag") or ""),
            "passport": str(self._row_value(row, "passport") or ""),
            "exam_format": str(self._row_value(row, "exam_format") or ""),
            "payload_json": self._encode_json_value(payload),
            "answer_count": int(self._row_value(row, "answer_count") or 0),
            "import_key": str(self._row_value(row, "import_key") or ""),
            "score_signature": self._build_score_signature(
                payload=payload,
                exam_format=str(self._row_value(row, "exam_format") or ""),
            ),
            "has_scores": bool(exam_scores)
            or self._row_value(row, "average_score") is not None
            or self._row_value(row, "question_g_score") is not None,
        }

    @staticmethod
    def _is_reference_snapshot(row: dict[str, object] | None) -> bool:
        if not isinstance(row, dict):
            return False
        payload = row.get("payload")
        if not isinstance(payload, dict):
            payload_json = row.get("payload_json")
            if isinstance(payload_json, str):
                try:
                    payload = json.loads(payload_json)
                except (TypeError, ValueError, json.JSONDecodeError):
                    payload = {}
        if int(row.get("source_row") or 0) == REFERENCE_SOURCE_ROW:
            return True
        return is_exam_reference_payload(
            payload if isinstance(payload, dict) else {},
            full_name=row.get("full_name"),
            exam_format=row.get("exam_format"),
        )

    def _load_entry_by_source_row(self, source_row: int) -> dict[str, object] | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"""
                SELECT
                    source_row,
                    submitted_at,
                    full_name,
                    discord_tag,
                    passport,
                    exam_format,
                    answer_count,
                    imported_at,
                    updated_at,
                    question_g_score,
                    question_g_rationale,
                    question_g_scored_at,
                    exam_scores_json,
                    exam_scores_scored_at,
                    average_score,
                    average_score_answer_count,
                    average_score_scored_at,
                    needs_rescore,
                    payload_json
                FROM exam_answers
                WHERE source_row = {self._placeholder()}
                """,
                (source_row,),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        payload = self._decode_json_value(result.pop("payload_json"), {})
        if not isinstance(payload, dict):
            payload = {}
        exam_scores_json = result.pop("exam_scores_json", None)
        result["payload"] = payload
        exam_scores = self._decode_json_value(exam_scores_json, [])
        result["exam_scores"] = exam_scores if isinstance(exam_scores, list) else []
        return result

    @staticmethod
    def _import_match_sort_key(item: dict[str, object], *, source_row: int, submitted_at: str) -> tuple[int, int, int, int, int, int]:
        item_source_row = int(item.get("source_row") or 0)
        return (
            1 if item_source_row > 0 else 0,
            1 if item_source_row == source_row else 0,
            1 if str(item.get("submitted_at") or "") == submitted_at else 0,
            1 if bool(item.get("has_scores")) else 0,
            -abs(item_source_row - source_row),
            int(item.get("id") or 0),
        )

    def _select_import_match(
        self,
        *,
        row: dict[str, object],
        existing_rows: list[dict[str, object]],
        matched_ids: set[int],
    ) -> dict[str, object] | None:
        import_key = str(row["import_key"])
        source_row = int(row["source_row"])
        submitted_at = str(row["submitted_at"])
        score_signature = str(row["score_signature"])

        exact_matches = [
            item
            for item in existing_rows
            if int(item["id"]) not in matched_ids and str(item.get("import_key") or "") == import_key
        ]
        if exact_matches:
            return max(
                exact_matches,
                key=lambda item: self._import_match_sort_key(
                    item,
                    source_row=source_row,
                    submitted_at=submitted_at,
                ),
            )

        signature_matches = [
            item
            for item in existing_rows
            if int(item["id"]) not in matched_ids and str(item.get("score_signature") or "") == score_signature
        ]
        if not signature_matches:
            return None

        return max(
            signature_matches,
            key=lambda item: self._import_match_sort_key(
                item,
                source_row=source_row,
                submitted_at=submitted_at,
            ),
        )

    def healthcheck(self) -> dict[str, object]:
        return self.backend.healthcheck()

    def _ensure_schema(self) -> None:
        return

    def _next_archived_source_row(self, conn) -> int:
        row = conn.execute("SELECT MIN(source_row) AS min_source_row FROM exam_answers").fetchone()
        min_source_row = int(row["min_source_row"]) if row and row["min_source_row"] is not None else 0
        return min_source_row - 1 if min_source_row <= 0 else -1

    @staticmethod
    def _calculate_average_score(scores: list[dict[str, object]]) -> tuple[float | None, int]:
        numeric_scores: list[int] = []
        for item in scores:
            raw_score = item.get("score")
            if isinstance(raw_score, int):
                numeric_scores.append(raw_score)
        if not numeric_scores:
            return None, 0
        average = round(sum(numeric_scores) / len(numeric_scores), 1)
        return average, len(numeric_scores)

    def import_rows(self, rows: list[dict[str, object]]) -> dict[str, object]:
        inserted_count = 0
        updated_count = 0
        skipped_count = 0
        changed_rows: list[int] = []
        placeholder = self._placeholder()
        current_timestamp = self._current_timestamp_sql()
        payload_placeholder = self._cast_json_value(placeholder)
        needs_rescore_value = self._bool_true_value()
        reference_needs_rescore_value = False if isinstance(needs_rescore_value, bool) else 0

        normalized_rows: list[dict[str, object]] = []
        for row in rows:
            submitted_at = str(row.get("submitted_at", "") or "")
            full_name = str(row.get("full_name", "") or "")
            discord_tag = str(row.get("discord_tag", "") or "")
            passport = str(row.get("passport", "") or "")
            exam_format = str(row.get("exam_format", "") or "")
            payload = row.get("payload") or {}
            if not isinstance(payload, dict):
                payload = {}
            normalized_rows.append(
                {
                    **row,
                    "submitted_at": submitted_at,
                    "full_name": full_name,
                    "discord_tag": discord_tag,
                    "passport": passport,
                    "exam_format": exam_format,
                    "payload": payload,
                    "import_key": self.build_import_key(
                        submitted_at=submitted_at,
                        full_name=full_name,
                        discord_tag=discord_tag,
                        passport=passport,
                        exam_format=exam_format,
                    ),
                    "score_signature": self._build_score_signature(payload=payload, exam_format=exam_format),
                }
            )
        normalized_rows = list({str(row["import_key"]): row for row in normalized_rows}.values())
        reference_rows = [row for row in normalized_rows if is_exam_reference_row(row)]
        normalized_rows = [row for row in normalized_rows if not is_exam_reference_row(row)]
        imported_reference_row = reference_rows[-1] if reference_rows else None

        with closing(self._connect()) as conn:
            existing_rows = conn.execute(
                """
                SELECT
                    id,
                    source_row,
                    submitted_at,
                    full_name,
                    discord_tag,
                    passport,
                    exam_format,
                    payload_json,
                    answer_count,
                    import_key,
                    question_g_score,
                    exam_scores_json,
                    average_score
                FROM exam_answers
                """
            ).fetchall()
            existing_snapshots = [self._build_existing_import_snapshot(row) for row in existing_rows]
            reference_snapshots = [item for item in existing_snapshots if self._is_reference_snapshot(item)]
            existing_snapshots = [item for item in existing_snapshots if not self._is_reference_snapshot(item)]
            reference_existing = next(
                (item for item in reference_snapshots if int(item.get("source_row") or 0) == REFERENCE_SOURCE_ROW),
                None,
            )
            if reference_existing is None and reference_snapshots:
                reference_existing = max(reference_snapshots, key=lambda item: int(item.get("id") or 0))
            matched_ids: set[int] = set()
            matched_rows: list[dict[str, object] | None] = []
            for row in normalized_rows:
                match = self._select_import_match(
                    row=row,
                    existing_rows=existing_snapshots,
                    matched_ids=matched_ids,
                )
                if match is not None:
                    matched_ids.add(int(match["id"]))
                matched_rows.append(match)

            archived_source_row = self._next_archived_source_row(conn)
            if reference_existing is not None and int(reference_existing.get("source_row") or 0) > 0:
                conn.execute(
                    f"UPDATE exam_answers SET source_row = {placeholder} WHERE id = {placeholder}",
                    (REFERENCE_SOURCE_ROW, reference_existing["id"]),
                )
                reference_existing["source_row"] = REFERENCE_SOURCE_ROW
            for existing in reference_snapshots:
                if reference_existing is not None and int(existing["id"]) == int(reference_existing["id"]):
                    continue
                if int(existing["source_row"] or 0) <= 0:
                    continue
                conn.execute(
                    f"UPDATE exam_answers SET import_key = NULL, source_row = {placeholder} WHERE id = {placeholder}",
                    (archived_source_row, existing["id"]),
                )
                archived_source_row -= 1

            for existing in existing_snapshots:
                if int(existing["id"]) in matched_ids or int(existing["source_row"] or 0) <= 0:
                    continue
                conn.execute(
                    f"UPDATE exam_answers SET import_key = NULL, source_row = {placeholder} WHERE id = {placeholder}",
                    (archived_source_row, existing["id"]),
                )
                archived_source_row -= 1

            for row, existing in zip(normalized_rows, matched_rows):
                if existing is None:
                    continue
                existing_source_row = int(existing.get("source_row") or 0)
                target_source_row = int(row["source_row"])
                if existing_source_row <= 0 or existing_source_row == target_source_row:
                    continue
                conn.execute(
                    f"UPDATE exam_answers SET source_row = {placeholder} WHERE id = {placeholder}",
                    (archived_source_row, existing["id"]),
                )
                existing["source_row"] = archived_source_row
                archived_source_row -= 1

            for row, existing in zip(normalized_rows, matched_rows):
                source_row = int(row["source_row"])
                submitted_at = str(row["submitted_at"])
                full_name = str(row["full_name"])
                discord_tag = str(row["discord_tag"])
                passport = str(row["passport"])
                exam_format = str(row["exam_format"])
                payload_json = self._encode_json_value(row["payload"])
                answer_count = int(row.get("answer_count", 0) or 0)
                import_key = str(row["import_key"])

                if existing is not None and str(existing.get("import_key") or "") != import_key:
                    conn.execute(
                        f"UPDATE exam_answers SET import_key = {placeholder} WHERE id = {placeholder}",
                        (import_key, existing["id"]),
                    )

                if existing is None:
                    conn.execute(
                        f"""
                        INSERT INTO exam_answers (
                            source_row,
                            submitted_at,
                            full_name,
                            discord_tag,
                            passport,
                            exam_format,
                            payload_json,
                            answer_count,
                            needs_rescore,
                            import_key
                        )
                        VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {payload_placeholder}, {placeholder}, {placeholder}, {placeholder})
                        """,
                        (
                            source_row,
                            submitted_at,
                            full_name,
                            discord_tag,
                            passport,
                            exam_format,
                            payload_json,
                            answer_count,
                            needs_rescore_value,
                            import_key,
                        ),
                    )
                    inserted_count += 1
                    changed_rows.append(source_row)
                else:
                    has_changes = any(
                        [
                            int(existing.get("source_row") or 0) != source_row,
                            str(existing.get("submitted_at") or "") != submitted_at,
                            str(existing.get("full_name") or "") != full_name,
                            str(existing.get("discord_tag") or "") != discord_tag,
                            str(existing.get("passport") or "") != passport,
                            str(existing.get("exam_format") or "") != exam_format,
                            str(existing.get("payload_json") or "") != payload_json,
                            int(existing.get("answer_count") or 0) != answer_count,
                        ]
                    )
                    if has_changes:
                        if str(existing.get("score_signature") or "") == str(row["score_signature"]):
                            conn.execute(
                                f"""
                                UPDATE exam_answers
                                SET source_row = {placeholder},
                                    submitted_at = {placeholder},
                                    full_name = {placeholder},
                                    discord_tag = {placeholder},
                                    passport = {placeholder},
                                    exam_format = {placeholder},
                                    payload_json = {payload_placeholder},
                                    answer_count = {placeholder},
                                    updated_at = {current_timestamp}
                                WHERE id = {placeholder}
                                """,
                                (
                                    source_row,
                                    submitted_at,
                                    full_name,
                                    discord_tag,
                                    passport,
                                    exam_format,
                                    payload_json,
                                    answer_count,
                                    existing["id"],
                                ),
                            )
                        else:
                            conn.execute(
                                f"""
                                UPDATE exam_answers
                                SET source_row = {placeholder},
                                    submitted_at = {placeholder},
                                    full_name = {placeholder},
                                    discord_tag = {placeholder},
                                    passport = {placeholder},
                                    exam_format = {placeholder},
                                    payload_json = {payload_placeholder},
                                    answer_count = {placeholder},
                                    question_g_score = NULL,
                                    question_g_rationale = NULL,
                                    question_g_scored_at = NULL,
                                    exam_scores_json = NULL,
                                    exam_scores_scored_at = NULL,
                                    average_score = NULL,
                                    average_score_answer_count = NULL,
                                    average_score_scored_at = NULL,
                                    needs_rescore = {placeholder},
                                    updated_at = {current_timestamp}
                                WHERE id = {placeholder}
                                """,
                                (
                                    source_row,
                                    submitted_at,
                                    full_name,
                                    discord_tag,
                                    passport,
                                    exam_format,
                                    payload_json,
                                    answer_count,
                                    needs_rescore_value,
                                    existing["id"],
                                ),
                            )
                        updated_count += 1
                        changed_rows.append(source_row)
                    else:
                        skipped_count += 1

            if imported_reference_row is not None or reference_existing is not None:
                reference_payload: dict[str, object] = {}
                if imported_reference_row is not None:
                    reference_payload = dict(imported_reference_row.get("payload") or {})
                elif isinstance(reference_existing, dict):
                    reference_payload = self._decode_json_value(reference_existing.get("payload_json"), {})
                    if not isinstance(reference_payload, dict):
                        reference_payload = {}

                reference_source_row = REFERENCE_SOURCE_ROW
                reference_submitted_at = str(
                    (imported_reference_row or {}).get("submitted_at")
                    or (reference_existing or {}).get("submitted_at")
                    or ""
                )
                reference_full_name = str(
                    (imported_reference_row or {}).get("full_name")
                    or (reference_existing or {}).get("full_name")
                    or ""
                )
                reference_discord_tag = str(
                    (imported_reference_row or {}).get("discord_tag")
                    or (reference_existing or {}).get("discord_tag")
                    or ""
                )
                reference_passport = str(
                    (imported_reference_row or {}).get("passport")
                    or (reference_existing or {}).get("passport")
                    or ""
                )
                reference_exam_format = str(
                    (imported_reference_row or {}).get("exam_format")
                    or (reference_existing or {}).get("exam_format")
                    or ""
                )
                reference_answer_count = int(
                    (imported_reference_row or {}).get("answer_count")
                    or (reference_existing or {}).get("answer_count")
                    or 0
                )
                reference_payload_json = self._encode_json_value(reference_payload)
                reference_import_key = str(
                    (imported_reference_row or {}).get("import_key")
                    or (reference_existing or {}).get("import_key")
                    or ""
                )

                if reference_existing is not None and str(reference_existing.get("import_key") or "") != reference_import_key:
                    conn.execute(
                        f"UPDATE exam_answers SET import_key = {placeholder} WHERE id = {placeholder}",
                        (reference_import_key, reference_existing["id"]),
                    )

                reference_has_changes = reference_existing is None or any(
                    [
                        int((reference_existing or {}).get("source_row") or 0) != reference_source_row,
                        str((reference_existing or {}).get("submitted_at") or "") != reference_submitted_at,
                        str((reference_existing or {}).get("full_name") or "") != reference_full_name,
                        str((reference_existing or {}).get("discord_tag") or "") != reference_discord_tag,
                        str((reference_existing or {}).get("passport") or "") != reference_passport,
                        str((reference_existing or {}).get("exam_format") or "") != reference_exam_format,
                        str((reference_existing or {}).get("payload_json") or "") != reference_payload_json,
                        int((reference_existing or {}).get("answer_count") or 0) != reference_answer_count,
                        str((reference_existing or {}).get("import_key") or "") != reference_import_key,
                        bool((reference_existing or {}).get("has_scores")),
                    ]
                )

                if reference_existing is None:
                    conn.execute(
                        f"""
                        INSERT INTO exam_answers (
                            source_row,
                            submitted_at,
                            full_name,
                            discord_tag,
                            passport,
                            exam_format,
                            payload_json,
                            answer_count,
                            needs_rescore,
                            import_key
                        )
                        VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {payload_placeholder}, {placeholder}, {placeholder}, {placeholder})
                        """,
                        (
                            reference_source_row,
                            reference_submitted_at,
                            reference_full_name,
                            reference_discord_tag,
                            reference_passport,
                            reference_exam_format,
                            reference_payload_json,
                            reference_answer_count,
                            reference_needs_rescore_value,
                            reference_import_key,
                        ),
                    )
                elif reference_has_changes:
                    conn.execute(
                        f"""
                        UPDATE exam_answers
                        SET source_row = {placeholder},
                            submitted_at = {placeholder},
                            full_name = {placeholder},
                            discord_tag = {placeholder},
                            passport = {placeholder},
                            exam_format = {placeholder},
                            payload_json = {payload_placeholder},
                            answer_count = {placeholder},
                            question_g_score = NULL,
                            question_g_rationale = NULL,
                            question_g_scored_at = NULL,
                            exam_scores_json = NULL,
                            exam_scores_scored_at = NULL,
                            average_score = NULL,
                            average_score_answer_count = NULL,
                            average_score_scored_at = NULL,
                            needs_rescore = {placeholder},
                            updated_at = {current_timestamp}
                        WHERE id = {placeholder}
                        """,
                        (
                            reference_source_row,
                            reference_submitted_at,
                            reference_full_name,
                            reference_discord_tag,
                            reference_passport,
                            reference_exam_format,
                            reference_payload_json,
                            reference_answer_count,
                            reference_needs_rescore_value,
                            reference_existing["id"],
                        ),
                    )
            conn.commit()

        return {
            "inserted_count": inserted_count,
            "updated_count": updated_count,
            "skipped_count": skipped_count,
            "total_rows": self.count(),
            "changed_rows": changed_rows,
        }

    def list_entries_needing_scores(self, limit: int = 500) -> list[dict[str, object]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"""
                SELECT
                    source_row,
                    submitted_at,
                    full_name,
                    discord_tag,
                    passport,
                    exam_format,
                    answer_count,
                    average_score,
                    average_score_answer_count,
                    imported_at
                FROM exam_answers
                WHERE source_row > 0 AND (average_score IS NULL OR {self._needs_rescore_predicate()})
                ORDER BY source_row ASC
                LIMIT {self._placeholder()}
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_entries_with_failed_scores(self, limit: int = 500) -> list[dict[str, object]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"""
                SELECT
                    source_row,
                    submitted_at,
                    full_name,
                    discord_tag,
                    passport,
                    exam_format,
                    answer_count,
                    average_score,
                    COALESCE(average_score_answer_count, 0) AS average_score_answer_count,
                    needs_rescore,
                    imported_at,
                    exam_scores_json
                FROM exam_answers
                WHERE source_row > 0 AND {self._json_present_predicate('exam_scores_json')}
                ORDER BY source_row ASC
                LIMIT {self._placeholder()}
                """,
                (limit,),
            ).fetchall()

        failed_entries: list[dict[str, object]] = []
        for row in rows:
            item = dict(row)
            exam_scores_raw = item.pop("exam_scores_json", None)
            exam_scores = self._decode_json_value(exam_scores_raw, [])
            if not isinstance(exam_scores, list):
                exam_scores = []
            if bool(int(item.get("needs_rescore") or 0)) or self._has_invalid_score_result(exam_scores):
                failed_entries.append(item)
        return failed_entries

    def count(self) -> int:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT COUNT(*) AS total FROM exam_answers WHERE source_row > 0").fetchone()
        return int(row["total"] if row else 0)

    def count_entries_needing_scores(self) -> int:
        with closing(self._connect()) as conn:
            row = conn.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM exam_answers
                WHERE source_row > 0 AND (average_score IS NULL OR {self._needs_rescore_predicate()})
                """
            ).fetchone()
        return int(row["total"] if row else 0)

    def list_entries(self, limit: int = 20) -> list[dict[str, object]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"""
                SELECT
                    source_row,
                    submitted_at,
                    full_name,
                    discord_tag,
                    passport,
                    exam_format,
                    answer_count,
                    average_score,
                    COALESCE(average_score_answer_count, 0) AS average_score_answer_count,
                    needs_rescore,
                    imported_at
                FROM exam_answers
                WHERE source_row > 0
                ORDER BY source_row DESC
                LIMIT {self._placeholder()}
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_reference_entry(self) -> dict[str, object] | None:
        return self._load_entry_by_source_row(REFERENCE_SOURCE_ROW)

    def get_entry(self, source_row: int) -> dict[str, object] | None:
        if int(source_row or 0) <= 0:
            return None
        return self._load_entry_by_source_row(source_row)

    def save_question_g_score(self, source_row: int, score: int, rationale: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                f"""
                UPDATE exam_answers
                SET question_g_score = {self._placeholder()},
                    question_g_rationale = {self._placeholder()},
                    question_g_scored_at = {self._current_timestamp_sql()}
                WHERE source_row = {self._placeholder()}
                """,
                (score, rationale, source_row),
            )
            conn.commit()

    def save_exam_scores(self, source_row: int, scores: list[dict[str, object]]) -> None:
        average_score, average_score_answer_count = self._calculate_average_score(scores)
        needs_rescore = self._has_invalid_score_result(scores)
        with closing(self._connect()) as conn:
            conn.execute(
                f"""
                UPDATE exam_answers
                SET exam_scores_json = {self._cast_json_value(self._placeholder())},
                    exam_scores_scored_at = {self._current_timestamp_sql()},
                    average_score = {self._placeholder()},
                    average_score_answer_count = {self._placeholder()},
                    average_score_scored_at = {self._current_timestamp_sql()},
                    needs_rescore = {self._placeholder()}
                WHERE source_row = {self._placeholder()}
                """,
                (
                    json.dumps(scores, ensure_ascii=False),
                    average_score,
                    average_score_answer_count,
                    needs_rescore,
                    source_row,
                ),
            )
            conn.commit()


_DEFAULT_EXAM_ANSWERS_STORE: ExamAnswersStore | None = None


def get_default_exam_answers_store() -> ExamAnswersStore:
    global _DEFAULT_EXAM_ANSWERS_STORE
    if _DEFAULT_EXAM_ANSWERS_STORE is None:
        _DEFAULT_EXAM_ANSWERS_STORE = ExamAnswersStore(DB_PATH, backend=get_database_backend())
    return _DEFAULT_EXAM_ANSWERS_STORE

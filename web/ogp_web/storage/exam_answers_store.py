from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from ogp_web.db.factory import get_database_backend
from ogp_web.db.types import DatabaseBackend

ROOT_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT_DIR / "web" / "data"
DB_PATH = DATA_DIR / "exam_answers.db"
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

    def __init__(self, db_path: Path, backend: DatabaseBackend | None = None):
        self.db_path = db_path
        self.backend = backend or get_database_backend()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self):
        return self.backend.connect()

    @property
    def is_postgres_backend(self) -> bool:
        name = self.backend.__class__.__name__
        return name == "PostgresBackend" or name.endswith("PostgresBackend")

    def _placeholder(self) -> str:
        return "%s" if self.is_postgres_backend else "?"

    def _json_column_type(self) -> str:
        return "JSONB" if self.is_postgres_backend else "TEXT"

    def _cast_json_value(self, placeholder: str) -> str:
        return f"{placeholder}::jsonb" if self.is_postgres_backend else placeholder

    def _current_timestamp_sql(self) -> str:
        return "NOW()" if self.is_postgres_backend else "CURRENT_TIMESTAMP"

    def _needs_rescore_predicate(self) -> str:
        return "needs_rescore IS TRUE" if self.is_postgres_backend else "needs_rescore = 1"

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

    def healthcheck(self) -> dict[str, object]:
        return self.backend.healthcheck()

    def _ensure_schema(self) -> None:
        with closing(self._connect()) as conn:
            if self.is_postgres_backend:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS exam_answers (
                        id BIGSERIAL PRIMARY KEY,
                        source_row INTEGER NOT NULL UNIQUE,
                        submitted_at TEXT,
                        full_name TEXT,
                        discord_tag TEXT,
                        passport TEXT,
                        exam_format TEXT,
                        payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                        answer_count INTEGER NOT NULL DEFAULT 0,
                        imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        question_g_score INTEGER,
                        question_g_rationale TEXT,
                        question_g_scored_at TIMESTAMPTZ,
                        exam_scores_json JSONB,
                        exam_scores_scored_at TIMESTAMPTZ,
                        average_score DOUBLE PRECISION,
                        average_score_answer_count INTEGER,
                        average_score_scored_at TIMESTAMPTZ,
                        needs_rescore BOOLEAN NOT NULL DEFAULT FALSE,
                        import_key TEXT
                    )
                    """
                )
            else:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS exam_answers (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        source_row INTEGER NOT NULL UNIQUE,
                        submitted_at TEXT,
                        full_name TEXT,
                        discord_tag TEXT,
                        passport TEXT,
                        exam_format TEXT,
                        payload_json TEXT NOT NULL,
                        answer_count INTEGER NOT NULL DEFAULT 0,
                        imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                columns = {
                    str(row["name"])
                    for row in conn.execute("PRAGMA table_info(exam_answers)").fetchall()
                }
                additions = {
                    "question_g_score": "ALTER TABLE exam_answers ADD COLUMN question_g_score INTEGER",
                    "question_g_rationale": "ALTER TABLE exam_answers ADD COLUMN question_g_rationale TEXT",
                    "question_g_scored_at": "ALTER TABLE exam_answers ADD COLUMN question_g_scored_at TEXT",
                    "exam_scores_json": "ALTER TABLE exam_answers ADD COLUMN exam_scores_json TEXT",
                    "exam_scores_scored_at": "ALTER TABLE exam_answers ADD COLUMN exam_scores_scored_at TEXT",
                    "average_score": "ALTER TABLE exam_answers ADD COLUMN average_score REAL",
                    "average_score_answer_count": "ALTER TABLE exam_answers ADD COLUMN average_score_answer_count INTEGER",
                    "average_score_scored_at": "ALTER TABLE exam_answers ADD COLUMN average_score_scored_at TEXT",
                    "needs_rescore": "ALTER TABLE exam_answers ADD COLUMN needs_rescore INTEGER NOT NULL DEFAULT 0",
                    "import_key": "ALTER TABLE exam_answers ADD COLUMN import_key TEXT",
                }
                for column_name, statement in additions.items():
                    if column_name in columns:
                        continue
                    try:
                        conn.execute(statement)
                    except sqlite3.OperationalError as exc:
                        if "duplicate column name" not in str(exc).lower():
                            raise
                    columns.add(column_name)
            self._normalize_import_keys(conn)
            self._ensure_import_key_index(conn)
            conn.commit()

    def _normalize_import_keys(self, conn) -> None:
        placeholder = self._placeholder()
        rows = conn.execute(
            """
            SELECT
                id,
                source_row,
                submitted_at,
                full_name,
                discord_tag,
                passport,
                exam_format,
                question_g_score,
                exam_scores_json,
                average_score
            FROM exam_answers
            ORDER BY id ASC
            """
        ).fetchall()

        grouped: dict[str, list[sqlite3.Row]] = {}
        for row in rows:
            grouped.setdefault(
                self.build_import_key(
                    row["submitted_at"],
                    row["full_name"],
                    row["discord_tag"],
                    row["passport"],
                    row["exam_format"],
                ),
                [],
            ).append(row)

        archived_source_row = self._next_archived_source_row(conn)
        for import_key, items in grouped.items():
            items = sorted(
                items,
                key=lambda item: (
                    1 if item["exam_scores_json"] else 0,
                    1 if item["average_score"] is not None else 0,
                    1 if item["question_g_score"] is not None else 0,
                    int(item["source_row"] or 0),
                    int(item["id"] or 0),
                ),
                reverse=True,
            )
            keeper = items[0]
            conn.execute(
                f"UPDATE exam_answers SET import_key = {placeholder} WHERE id = {placeholder}",
                (import_key, keeper["id"]),
            )
            for duplicate in items[1:]:
                conn.execute(
                    f"UPDATE exam_answers SET import_key = NULL, source_row = {placeholder} WHERE id = {placeholder}",
                    (archived_source_row, duplicate["id"]),
                )
                archived_source_row -= 1

    def _ensure_import_key_index(self, conn) -> None:
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_exam_answers_import_key
            ON exam_answers(import_key)
            WHERE import_key IS NOT NULL
            """
        )

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

        normalized_rows: list[dict[str, object]] = []
        for row in rows:
            submitted_at = str(row.get("submitted_at", "") or "")
            full_name = str(row.get("full_name", "") or "")
            discord_tag = str(row.get("discord_tag", "") or "")
            passport = str(row.get("passport", "") or "")
            exam_format = str(row.get("exam_format", "") or "")
            normalized_rows.append(
                {
                    **row,
                    "submitted_at": submitted_at,
                    "full_name": full_name,
                    "discord_tag": discord_tag,
                    "passport": passport,
                    "exam_format": exam_format,
                    "import_key": self.build_import_key(
                        submitted_at=submitted_at,
                        full_name=full_name,
                        discord_tag=discord_tag,
                        passport=passport,
                        exam_format=exam_format,
                    ),
                }
            )

        incoming_by_key = {str(row["import_key"]): row for row in normalized_rows}

        with closing(self._connect()) as conn:
            if not self.is_postgres_backend:
                conn.execute("BEGIN IMMEDIATE")
            existing_rows = conn.execute(
                """
                SELECT
                    id,
                    source_row,
                    import_key
                FROM exam_answers
                """
            ).fetchall()

            archived_source_row = self._next_archived_source_row(conn)
            for existing in existing_rows:
                import_key = str(existing["import_key"] or "")
                target_row = incoming_by_key.get(import_key)
                should_archive = target_row is None or int(existing["source_row"] or 0) != int(target_row["source_row"])
                if should_archive and int(existing["source_row"] or 0) > 0:
                    conn.execute(
                        f"UPDATE exam_answers SET source_row = {placeholder} WHERE id = {placeholder}",
                        (archived_source_row, existing["id"]),
                    )
                    archived_source_row -= 1

            for row in normalized_rows:
                source_row = int(row["source_row"])
                submitted_at = str(row["submitted_at"])
                full_name = str(row["full_name"])
                discord_tag = str(row["discord_tag"])
                passport = str(row["passport"])
                exam_format = str(row["exam_format"])
                payload_json = json.dumps(row["payload"], ensure_ascii=False)
                answer_count = int(row.get("answer_count", 0) or 0)
                import_key = str(row["import_key"])
                existing = conn.execute(
                    f"""
                    SELECT
                        id,
                        source_row,
                        submitted_at,
                        full_name,
                        discord_tag,
                        passport,
                        exam_format,
                        payload_json,
                        answer_count
                    FROM exam_answers
                    WHERE import_key = {placeholder}
                    """,
                    (import_key,),
                ).fetchone()

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
                            1,
                            import_key,
                        ),
                    )
                    inserted_count += 1
                    changed_rows.append(source_row)
                else:
                    has_changes = any(
                        [
                            int(existing["source_row"] or 0) != source_row,
                            str(existing["submitted_at"] or "") != submitted_at,
                            str(existing["full_name"] or "") != full_name,
                            str(existing["discord_tag"] or "") != discord_tag,
                            str(existing["passport"] or "") != passport,
                            str(existing["exam_format"] or "") != exam_format,
                            str(existing["payload_json"] or "") != payload_json,
                            int(existing["answer_count"] or 0) != answer_count,
                        ]
                    )
                    if has_changes:
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
                                needs_rescore = 1,
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
                        updated_count += 1
                        changed_rows.append(source_row)
                    else:
                        skipped_count += 1
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
                WHERE source_row > 0 AND exam_scores_json IS NOT NULL AND exam_scores_json <> ''
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

    def get_entry(self, source_row: int) -> dict[str, object] | None:
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
                WHERE source_row = {self._placeholder()} AND source_row > 0
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
        needs_rescore = 1 if self._has_invalid_score_result(scores) else 0
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


EXAM_ANSWERS_STORE = ExamAnswersStore(DB_PATH, backend=get_database_backend())

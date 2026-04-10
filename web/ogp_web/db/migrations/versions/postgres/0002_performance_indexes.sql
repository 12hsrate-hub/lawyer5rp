CREATE INDEX IF NOT EXISTS idx_metric_events_event_type_created_at
ON metric_events (event_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_metric_events_path_created_at
ON metric_events (path, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_metric_events_username_created_at
ON metric_events (username, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_exam_answers_source_row_import_key
ON exam_answers (source_row, import_key);

CREATE INDEX IF NOT EXISTS idx_exam_answers_pending_scores
ON exam_answers (source_row, average_score, needs_rescore);

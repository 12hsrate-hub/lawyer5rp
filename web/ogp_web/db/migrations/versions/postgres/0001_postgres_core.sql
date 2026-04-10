CREATE TABLE IF NOT EXISTS servers (
    code TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

INSERT INTO servers (code, title)
VALUES ('blackberry', 'BlackBerry')
ON CONFLICT (code) DO NOTHING;

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    email TEXT,
    salt TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    email_verified_at TIMESTAMPTZ,
    email_verification_token_hash TEXT,
    email_verification_sent_at TIMESTAMPTZ,
    password_reset_token_hash TEXT,
    password_reset_sent_at TIMESTAMPTZ,
    access_blocked_at TIMESTAMPTZ,
    access_blocked_reason TEXT,
    representative_profile JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique
ON users ((LOWER(email)))
WHERE email IS NOT NULL AND BTRIM(email) <> '';

CREATE TABLE IF NOT EXISTS user_server_roles (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    server_code TEXT NOT NULL REFERENCES servers(code) ON DELETE CASCADE,
    is_tester BOOLEAN NOT NULL DEFAULT FALSE,
    is_gka BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, server_code)
);

CREATE INDEX IF NOT EXISTS idx_user_server_roles_server_code
ON user_server_roles (server_code);

CREATE TABLE IF NOT EXISTS complaint_drafts (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    server_code TEXT NOT NULL REFERENCES servers(code) ON DELETE CASCADE,
    draft_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, server_code)
);

CREATE INDEX IF NOT EXISTS idx_complaint_drafts_server_code
ON complaint_drafts (server_code);

CREATE TABLE IF NOT EXISTS metric_events (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    username TEXT,
    server_code TEXT REFERENCES servers(code) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    path TEXT,
    method TEXT,
    status_code INTEGER,
    duration_ms INTEGER,
    request_bytes INTEGER,
    response_bytes INTEGER,
    resource_units INTEGER,
    meta_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_metric_events_created_at
ON metric_events (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_metric_events_username
ON metric_events (username);

CREATE INDEX IF NOT EXISTS idx_metric_events_server_code
ON metric_events (server_code);

CREATE INDEX IF NOT EXISTS idx_metric_events_event_type
ON metric_events (event_type);

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
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_exam_answers_import_key
ON exam_answers (import_key)
WHERE import_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS exam_import_tasks (
    id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL,
    source_row INTEGER,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    error TEXT NOT NULL DEFAULT '',
    progress_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_exam_import_tasks_created_at
ON exam_import_tasks (created_at DESC);

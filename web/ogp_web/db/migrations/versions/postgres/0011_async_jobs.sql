CREATE TABLE IF NOT EXISTS async_jobs (
    id BIGSERIAL PRIMARY KEY,
    server_scope TEXT NOT NULL CHECK (server_scope IN ('server', 'global')),
    server_id TEXT NULL REFERENCES servers(code) ON DELETE RESTRICT,
    job_type TEXT NOT NULL CHECK (job_type IN ('document_generation', 'document_export', 'content_reindex', 'content_import')),
    status TEXT NOT NULL CHECK (status IN ('pending', 'queued', 'processing', 'succeeded', 'failed', 'dead_lettered', 'cancelled')),
    entity_type TEXT NOT NULL,
    entity_id BIGINT NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    idempotency_key TEXT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3 CHECK (max_attempts > 0),
    next_run_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_error_code TEXT NULL,
    last_error_message TEXT NULL,
    created_by BIGINT NULL REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_async_jobs_server_scope
        CHECK (
            (server_scope = 'global' AND server_id IS NULL)
            OR (server_scope = 'server' AND server_id IS NOT NULL)
        )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_async_jobs_idempotency_key
ON async_jobs (idempotency_key)
WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_async_jobs_status_next_run
ON async_jobs (status, next_run_at);

CREATE INDEX IF NOT EXISTS idx_async_jobs_type_created_at
ON async_jobs (job_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_async_jobs_entity_ref
ON async_jobs (entity_type, entity_id);

CREATE TABLE IF NOT EXISTS job_attempts (
    id BIGSERIAL PRIMARY KEY,
    async_job_id BIGINT NOT NULL REFERENCES async_jobs(id) ON DELETE CASCADE,
    attempt_number INTEGER NOT NULL CHECK (attempt_number > 0),
    status TEXT NOT NULL CHECK (status IN ('started', 'succeeded', 'failed')),
    worker_id TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ NULL,
    error_code TEXT NULL,
    error_message TEXT NULL,
    error_details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (async_job_id, attempt_number)
);

CREATE INDEX IF NOT EXISTS idx_job_attempts_job_attempt
ON job_attempts (async_job_id, attempt_number ASC);

CREATE TABLE IF NOT EXISTS job_dead_letters (
    id BIGSERIAL PRIMARY KEY,
    async_job_id BIGINT NOT NULL REFERENCES async_jobs(id) ON DELETE CASCADE,
    dead_letter_reason TEXT NOT NULL,
    payload_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_error_code TEXT NULL,
    last_error_message TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_job_dead_letters_job
ON job_dead_letters (async_job_id, created_at DESC);

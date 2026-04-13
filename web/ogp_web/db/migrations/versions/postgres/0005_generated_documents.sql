CREATE TABLE IF NOT EXISTS generated_documents (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    server_code TEXT NOT NULL REFERENCES servers(code) ON DELETE CASCADE,
    document_kind TEXT NOT NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_text TEXT NOT NULL DEFAULT '',
    context_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_generated_documents_user_id_created_at
ON generated_documents (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_generated_documents_server_code_created_at
ON generated_documents (server_code, created_at DESC);

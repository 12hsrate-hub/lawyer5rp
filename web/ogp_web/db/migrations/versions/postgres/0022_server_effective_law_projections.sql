CREATE TABLE IF NOT EXISTS server_effective_law_projection_runs (
    id BIGSERIAL PRIMARY KEY,
    server_code TEXT NOT NULL REFERENCES servers(code) ON DELETE CASCADE,
    trigger_mode TEXT NOT NULL DEFAULT 'manual',
    status TEXT NOT NULL DEFAULT 'preview',
    summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_server_effective_law_projection_runs_server_created
    ON server_effective_law_projection_runs (server_code, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS server_effective_law_projection_items (
    id BIGSERIAL PRIMARY KEY,
    projection_run_id BIGINT NOT NULL REFERENCES server_effective_law_projection_runs(id) ON DELETE CASCADE,
    canonical_law_document_id BIGINT NOT NULL REFERENCES canonical_law_documents(id) ON DELETE CASCADE,
    canonical_identity_key TEXT NOT NULL,
    normalized_url TEXT NOT NULL,
    selected_document_version_id BIGINT NOT NULL REFERENCES canonical_law_document_versions(id) ON DELETE CASCADE,
    selected_source_set_key TEXT NOT NULL,
    selected_revision INT NOT NULL DEFAULT 0,
    precedence_rank INT NOT NULL DEFAULT 0,
    contributor_count INT NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'candidate',
    provenance_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_server_effective_law_projection_items_run
    ON server_effective_law_projection_items (projection_run_id, precedence_rank ASC, id ASC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_server_effective_law_projection_items_run_identity_unique
    ON server_effective_law_projection_items (projection_run_id, canonical_identity_key);

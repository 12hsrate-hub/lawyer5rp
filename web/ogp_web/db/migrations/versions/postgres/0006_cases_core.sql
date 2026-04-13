CREATE TABLE IF NOT EXISTS cases (
    id BIGSERIAL PRIMARY KEY,
    server_id TEXT NOT NULL REFERENCES servers(code) ON DELETE RESTRICT,
    owner_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    title TEXT NOT NULL CHECK (btrim(title) <> ''),
    case_type TEXT NOT NULL CHECK (btrim(case_type) <> ''),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'in_progress', 'closed')),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (id, server_id)
);

CREATE TABLE IF NOT EXISTS case_events (
    id BIGSERIAL PRIMARY KEY,
    case_id BIGINT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    server_id TEXT NOT NULL REFERENCES servers(code) ON DELETE RESTRICT,
    event_type TEXT NOT NULL,
    actor_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS case_documents (
    id BIGSERIAL PRIMARY KEY,
    case_id BIGINT NOT NULL,
    server_id TEXT NOT NULL REFERENCES servers(code) ON DELETE RESTRICT,
    document_type TEXT NOT NULL CHECK (btrim(document_type) <> ''),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'generated', 'ready')),
    created_by BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    latest_version_id BIGINT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_case_documents_case_scope
        FOREIGN KEY (case_id, server_id)
        REFERENCES cases(id, server_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS document_versions (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES case_documents(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL CHECK (version_number > 0),
    content_json JSONB NOT NULL,
    created_by BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, version_number)
);

ALTER TABLE case_documents
    DROP CONSTRAINT IF EXISTS fk_case_documents_latest_version;
ALTER TABLE case_documents
    ADD CONSTRAINT fk_case_documents_latest_version
    FOREIGN KEY (latest_version_id)
    REFERENCES document_versions(id)
    ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_cases_server_owner_status
ON cases (server_id, owner_user_id, status);

CREATE INDEX IF NOT EXISTS idx_cases_server_updated_at
ON cases (server_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_case_documents_case_created_at
ON case_documents (case_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_case_documents_server_type_updated_at
ON case_documents (server_id, document_type, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_document_versions_document_created_at
ON document_versions (document_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_case_events_case_created_at
ON case_events (case_id, created_at DESC);

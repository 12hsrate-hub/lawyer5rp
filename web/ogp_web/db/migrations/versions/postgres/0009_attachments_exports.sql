CREATE TABLE IF NOT EXISTS attachments (
    id BIGSERIAL PRIMARY KEY,
    server_id TEXT NOT NULL REFERENCES servers(code) ON DELETE RESTRICT,
    uploaded_by BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    storage_key TEXT NOT NULL CHECK (btrim(storage_key) <> ''),
    filename TEXT NOT NULL CHECK (btrim(filename) <> ''),
    mime_type TEXT NOT NULL DEFAULT 'application/octet-stream',
    size_bytes BIGINT NOT NULL DEFAULT 0 CHECK (size_bytes >= 0),
    checksum TEXT NOT NULL DEFAULT '',
    upload_status TEXT NOT NULL DEFAULT 'pending' CHECK (upload_status IN ('pending', 'uploaded', 'failed')),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_attachments_server_created_at
ON attachments (server_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_attachments_uploaded_by_created_at
ON attachments (uploaded_by, created_at DESC);

CREATE TABLE IF NOT EXISTS document_version_attachment_links (
    id BIGSERIAL PRIMARY KEY,
    document_version_id BIGINT NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
    attachment_id BIGINT NOT NULL REFERENCES attachments(id) ON DELETE CASCADE,
    link_type TEXT NOT NULL DEFAULT 'supporting' CHECK (link_type IN ('evidence', 'supporting', 'source_file', 'other')),
    created_by BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_version_id, attachment_id)
);

CREATE INDEX IF NOT EXISTS idx_dv_attachment_links_version_created_at
ON document_version_attachment_links (document_version_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_dv_attachment_links_attachment_id
ON document_version_attachment_links (attachment_id);

CREATE TABLE IF NOT EXISTS exports (
    id BIGSERIAL PRIMARY KEY,
    document_version_id BIGINT NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
    server_id TEXT NOT NULL REFERENCES servers(code) ON DELETE RESTRICT,
    format TEXT NOT NULL CHECK (btrim(format) <> ''),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'ready', 'failed')),
    storage_key TEXT NOT NULL DEFAULT '',
    mime_type TEXT NOT NULL DEFAULT 'application/octet-stream',
    size_bytes BIGINT NOT NULL DEFAULT 0 CHECK (size_bytes >= 0),
    checksum TEXT NOT NULL DEFAULT '',
    created_by BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    job_run_id TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_exports_version_created_at
ON exports (document_version_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_exports_server_status_updated_at
ON exports (server_id, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_exports_job_run_id
ON exports (job_run_id)
WHERE job_run_id IS NOT NULL;

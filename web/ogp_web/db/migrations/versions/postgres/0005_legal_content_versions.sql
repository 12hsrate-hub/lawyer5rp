CREATE TABLE IF NOT EXISTS law_documents (
    id BIGSERIAL PRIMARY KEY,
    server_code TEXT NOT NULL REFERENCES servers(code) ON DELETE CASCADE,
    source_url TEXT NOT NULL,
    document_title TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (server_code, source_url, document_title)
);

CREATE INDEX IF NOT EXISTS idx_law_documents_server_code
ON law_documents (server_code);

CREATE TABLE IF NOT EXISTS law_versions (
    id BIGSERIAL PRIMARY KEY,
    server_code TEXT NOT NULL REFERENCES servers(code) ON DELETE CASCADE,
    source_type TEXT NOT NULL DEFAULT 'snapshot_import',
    source_ref TEXT NOT NULL DEFAULT '',
    generated_at_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    effective_from TIMESTAMPTZ NOT NULL,
    effective_to TIMESTAMPTZ,
    fingerprint TEXT NOT NULL,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (effective_to IS NULL OR effective_to > effective_from)
);

CREATE INDEX IF NOT EXISTS idx_law_versions_server_effective
ON law_versions (server_code, effective_from DESC, effective_to);

CREATE INDEX IF NOT EXISTS idx_law_versions_fingerprint
ON law_versions (fingerprint);

CREATE TABLE IF NOT EXISTS law_articles (
    id BIGSERIAL PRIMARY KEY,
    law_version_id BIGINT NOT NULL REFERENCES law_versions(id) ON DELETE CASCADE,
    law_document_id BIGINT NOT NULL REFERENCES law_documents(id) ON DELETE RESTRICT,
    article_label TEXT NOT NULL,
    text TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_law_articles_version_position
ON law_articles (law_version_id, position);

CREATE TABLE IF NOT EXISTS templates (
    id BIGSERIAL PRIMARY KEY,
    server_code TEXT NOT NULL REFERENCES servers(code) ON DELETE CASCADE,
    template_key TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (server_code, template_key)
);

CREATE INDEX IF NOT EXISTS idx_templates_server_code
ON templates (server_code);

CREATE TABLE IF NOT EXISTS template_versions (
    id BIGSERIAL PRIMARY KEY,
    template_id BIGINT NOT NULL REFERENCES templates(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL DEFAULT 'manual',
    source_ref TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    effective_from TIMESTAMPTZ NOT NULL,
    effective_to TIMESTAMPTZ,
    fingerprint TEXT NOT NULL,
    meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (effective_to IS NULL OR effective_to > effective_from)
);

CREATE INDEX IF NOT EXISTS idx_template_versions_template_effective
ON template_versions (template_id, effective_from DESC, effective_to);

CREATE TABLE IF NOT EXISTS template_fields (
    id BIGSERIAL PRIMARY KEY,
    template_version_id BIGINT NOT NULL REFERENCES template_versions(id) ON DELETE CASCADE,
    field_key TEXT NOT NULL,
    field_label TEXT NOT NULL DEFAULT '',
    field_type TEXT NOT NULL DEFAULT 'text',
    required BOOLEAN NOT NULL DEFAULT FALSE,
    field_order INTEGER NOT NULL DEFAULT 0,
    default_value TEXT NOT NULL DEFAULT '',
    meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (template_version_id, field_key)
);

CREATE INDEX IF NOT EXISTS idx_template_fields_version_order
ON template_fields (template_version_id, field_order);

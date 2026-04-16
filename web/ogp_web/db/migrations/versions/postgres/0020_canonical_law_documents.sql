CREATE TABLE IF NOT EXISTS canonical_law_documents (
    id BIGSERIAL PRIMARY KEY,
    canonical_identity_key TEXT NOT NULL UNIQUE,
    identity_source TEXT NOT NULL DEFAULT 'url_seed',
    display_title TEXT NOT NULL DEFAULT '',
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'canonical_law_documents_identity_source_check'
    ) THEN
        ALTER TABLE canonical_law_documents
            ADD CONSTRAINT canonical_law_documents_identity_source_check
            CHECK (identity_source IN ('url_seed', 'parsed_metadata', 'manual_remap'));
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'canonical_law_documents_metadata_json_check'
    ) THEN
        ALTER TABLE canonical_law_documents
            ADD CONSTRAINT canonical_law_documents_metadata_json_check
            CHECK (jsonb_typeof(metadata_json) = 'object');
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_canonical_law_documents_title
ON canonical_law_documents (display_title);

CREATE TABLE IF NOT EXISTS canonical_law_document_aliases (
    id BIGSERIAL PRIMARY KEY,
    canonical_law_document_id BIGINT NOT NULL REFERENCES canonical_law_documents(id) ON DELETE CASCADE,
    normalized_url TEXT NOT NULL UNIQUE,
    alias_kind TEXT NOT NULL DEFAULT 'canonical',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'canonical_law_document_aliases_alias_kind_check'
    ) THEN
        ALTER TABLE canonical_law_document_aliases
            ADD CONSTRAINT canonical_law_document_aliases_alias_kind_check
            CHECK (alias_kind IN ('canonical', 'redirect', 'mirror', 'legacy', 'manual_remap'));
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'canonical_law_document_aliases_metadata_json_check'
    ) THEN
        ALTER TABLE canonical_law_document_aliases
            ADD CONSTRAINT canonical_law_document_aliases_metadata_json_check
            CHECK (jsonb_typeof(metadata_json) = 'object');
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_canonical_law_document_aliases_doc_lookup
ON canonical_law_document_aliases (canonical_law_document_id, is_active, normalized_url);

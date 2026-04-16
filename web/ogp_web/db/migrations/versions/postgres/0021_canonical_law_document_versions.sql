CREATE TABLE IF NOT EXISTS canonical_law_document_versions (
    id BIGSERIAL PRIMARY KEY,
    canonical_law_document_id BIGINT NOT NULL REFERENCES canonical_law_documents(id) ON DELETE CASCADE,
    source_discovery_run_id BIGINT NOT NULL REFERENCES source_discovery_runs(id) ON DELETE CASCADE,
    discovered_law_link_id BIGINT NOT NULL REFERENCES discovered_law_links(id) ON DELETE CASCADE,
    fetch_status TEXT NOT NULL DEFAULT 'seeded',
    parse_status TEXT NOT NULL DEFAULT 'pending',
    content_checksum TEXT NOT NULL DEFAULT '',
    raw_title TEXT NOT NULL DEFAULT '',
    parsed_title TEXT NOT NULL DEFAULT '',
    body_text TEXT NOT NULL DEFAULT '',
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (discovered_law_link_id)
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'canonical_law_document_versions_fetch_status_check'
    ) THEN
        ALTER TABLE canonical_law_document_versions
            ADD CONSTRAINT canonical_law_document_versions_fetch_status_check
            CHECK (fetch_status IN ('pending', 'seeded', 'fetched', 'failed'));
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'canonical_law_document_versions_parse_status_check'
    ) THEN
        ALTER TABLE canonical_law_document_versions
            ADD CONSTRAINT canonical_law_document_versions_parse_status_check
            CHECK (parse_status IN ('pending', 'parsed', 'failed', 'skipped'));
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'canonical_law_document_versions_metadata_json_check'
    ) THEN
        ALTER TABLE canonical_law_document_versions
            ADD CONSTRAINT canonical_law_document_versions_metadata_json_check
            CHECK (jsonb_typeof(metadata_json) = 'object');
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_canonical_law_document_versions_document_lookup
ON canonical_law_document_versions (canonical_law_document_id, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_canonical_law_document_versions_run_lookup
ON canonical_law_document_versions (source_discovery_run_id, created_at DESC, id DESC);

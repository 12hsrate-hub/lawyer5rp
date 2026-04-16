CREATE TABLE IF NOT EXISTS source_discovery_runs (
    id BIGSERIAL PRIMARY KEY,
    source_set_revision_id BIGINT NOT NULL REFERENCES source_set_revisions(id) ON DELETE CASCADE,
    trigger_mode TEXT NOT NULL DEFAULT 'manual',
    status TEXT NOT NULL DEFAULT 'pending',
    summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_summary TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ NULL,
    finished_at TIMESTAMPTZ NULL
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'source_discovery_runs_trigger_mode_check'
    ) THEN
        ALTER TABLE source_discovery_runs
            ADD CONSTRAINT source_discovery_runs_trigger_mode_check
            CHECK (trigger_mode IN ('manual', 'scheduled', 'backfill', 'replay'));
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'source_discovery_runs_status_check'
    ) THEN
        ALTER TABLE source_discovery_runs
            ADD CONSTRAINT source_discovery_runs_status_check
            CHECK (status IN ('pending', 'running', 'partial_success', 'succeeded', 'failed'));
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'source_discovery_runs_summary_json_check'
    ) THEN
        ALTER TABLE source_discovery_runs
            ADD CONSTRAINT source_discovery_runs_summary_json_check
            CHECK (jsonb_typeof(summary_json) = 'object');
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_source_discovery_runs_revision_lookup
ON source_discovery_runs (source_set_revision_id, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS discovered_law_links (
    id BIGSERIAL PRIMARY KEY,
    source_discovery_run_id BIGINT NOT NULL REFERENCES source_discovery_runs(id) ON DELETE CASCADE,
    source_set_revision_id BIGINT NOT NULL REFERENCES source_set_revisions(id) ON DELETE CASCADE,
    normalized_url TEXT NOT NULL,
    source_container_url TEXT NOT NULL DEFAULT '',
    discovery_status TEXT NOT NULL DEFAULT 'discovered',
    alias_hints_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_discovery_run_id, normalized_url)
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'discovered_law_links_discovery_status_check'
    ) THEN
        ALTER TABLE discovered_law_links
            ADD CONSTRAINT discovered_law_links_discovery_status_check
            CHECK (discovery_status IN ('discovered', 'broken', 'filtered', 'duplicate'));
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'discovered_law_links_alias_hints_json_check'
    ) THEN
        ALTER TABLE discovered_law_links
            ADD CONSTRAINT discovered_law_links_alias_hints_json_check
            CHECK (jsonb_typeof(alias_hints_json) = 'object');
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'discovered_law_links_metadata_json_check'
    ) THEN
        ALTER TABLE discovered_law_links
            ADD CONSTRAINT discovered_law_links_metadata_json_check
            CHECK (jsonb_typeof(metadata_json) = 'object');
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_discovered_law_links_run_lookup
ON discovered_law_links (source_discovery_run_id, discovery_status, normalized_url);

CREATE INDEX IF NOT EXISTS idx_discovered_law_links_revision_lookup
ON discovered_law_links (source_set_revision_id, normalized_url);

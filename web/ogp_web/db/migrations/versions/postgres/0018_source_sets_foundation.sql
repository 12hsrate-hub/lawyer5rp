CREATE TABLE IF NOT EXISTS source_sets (
    source_set_key TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    scope TEXT NOT NULL DEFAULT 'global',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'source_sets_scope_check'
    ) THEN
        ALTER TABLE source_sets
            ADD CONSTRAINT source_sets_scope_check
            CHECK (scope IN ('global'));
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS source_set_revisions (
    id BIGSERIAL PRIMARY KEY,
    source_set_key TEXT NOT NULL REFERENCES source_sets(source_set_key) ON DELETE CASCADE,
    revision INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    container_urls_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    adapter_policy_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ NULL,
    UNIQUE (source_set_key, revision)
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'source_set_revisions_status_check'
    ) THEN
        ALTER TABLE source_set_revisions
            ADD CONSTRAINT source_set_revisions_status_check
            CHECK (status IN ('draft', 'published', 'archived', 'legacy_flat'));
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'source_set_revisions_container_urls_json_check'
    ) THEN
        ALTER TABLE source_set_revisions
            ADD CONSTRAINT source_set_revisions_container_urls_json_check
            CHECK (jsonb_typeof(container_urls_json) = 'array');
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'source_set_revisions_adapter_policy_json_check'
    ) THEN
        ALTER TABLE source_set_revisions
            ADD CONSTRAINT source_set_revisions_adapter_policy_json_check
            CHECK (jsonb_typeof(adapter_policy_json) = 'object');
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'source_set_revisions_metadata_json_check'
    ) THEN
        ALTER TABLE source_set_revisions
            ADD CONSTRAINT source_set_revisions_metadata_json_check
            CHECK (jsonb_typeof(metadata_json) = 'object');
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_source_set_revisions_lookup
ON source_set_revisions (source_set_key, status, revision DESC);

CREATE TABLE IF NOT EXISTS server_source_set_bindings (
    id BIGSERIAL PRIMARY KEY,
    server_code TEXT NOT NULL REFERENCES servers(code) ON DELETE CASCADE,
    source_set_key TEXT NOT NULL REFERENCES source_sets(source_set_key) ON DELETE CASCADE,
    priority INTEGER NOT NULL DEFAULT 100,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    include_law_keys_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    exclude_law_keys_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    pin_policy_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (server_code, source_set_key)
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'server_source_set_bindings_include_law_keys_json_check'
    ) THEN
        ALTER TABLE server_source_set_bindings
            ADD CONSTRAINT server_source_set_bindings_include_law_keys_json_check
            CHECK (jsonb_typeof(include_law_keys_json) = 'array');
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'server_source_set_bindings_exclude_law_keys_json_check'
    ) THEN
        ALTER TABLE server_source_set_bindings
            ADD CONSTRAINT server_source_set_bindings_exclude_law_keys_json_check
            CHECK (jsonb_typeof(exclude_law_keys_json) = 'array');
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'server_source_set_bindings_pin_policy_json_check'
    ) THEN
        ALTER TABLE server_source_set_bindings
            ADD CONSTRAINT server_source_set_bindings_pin_policy_json_check
            CHECK (jsonb_typeof(pin_policy_json) = 'object');
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'server_source_set_bindings_metadata_json_check'
    ) THEN
        ALTER TABLE server_source_set_bindings
            ADD CONSTRAINT server_source_set_bindings_metadata_json_check
            CHECK (jsonb_typeof(metadata_json) = 'object');
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_server_source_set_bindings_lookup
ON server_source_set_bindings (server_code, is_active, priority ASC, id ASC);

ALTER TABLE servers
    ADD COLUMN IF NOT EXISTS default_law_set_id BIGINT,
    ADD COLUMN IF NOT EXISTS settings_json JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS law_source_registry (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'url',
    url TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_law_source_registry_url_unique
ON law_source_registry ((LOWER(url)));

CREATE INDEX IF NOT EXISTS idx_law_source_registry_active
ON law_source_registry (is_active, kind);

CREATE TABLE IF NOT EXISTS law_sets (
    id BIGSERIAL PRIMARY KEY,
    server_code TEXT NOT NULL REFERENCES servers(code) ON DELETE CASCADE,
    name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_published BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_law_sets_server_name_unique
ON law_sets (server_code, LOWER(name));

CREATE INDEX IF NOT EXISTS idx_law_sets_server_active
ON law_sets (server_code, is_active);

CREATE TABLE IF NOT EXISTS law_set_items (
    id BIGSERIAL PRIMARY KEY,
    law_set_id BIGINT NOT NULL REFERENCES law_sets(id) ON DELETE CASCADE,
    law_code TEXT NOT NULL,
    effective_from DATE,
    priority INTEGER NOT NULL DEFAULT 100,
    source_id BIGINT REFERENCES law_source_registry(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_law_set_items_set_code_effective_priority
ON law_set_items (law_set_id, law_code, COALESCE(effective_from, DATE '1970-01-01'), priority);

CREATE INDEX IF NOT EXISTS idx_law_set_items_source
ON law_set_items (source_id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'servers_default_law_set_fk'
    ) THEN
        ALTER TABLE servers
            ADD CONSTRAINT servers_default_law_set_fk
            FOREIGN KEY (default_law_set_id)
            REFERENCES law_sets(id)
            ON DELETE SET NULL;
    END IF;
END $$;

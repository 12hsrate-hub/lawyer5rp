CREATE TABLE IF NOT EXISTS content_items (
    id BIGSERIAL PRIMARY KEY,
    server_scope TEXT NOT NULL CHECK (server_scope IN ('server', 'global')),
    server_id TEXT NULL REFERENCES servers(code) ON DELETE RESTRICT,
    content_type TEXT NOT NULL CHECK (btrim(content_type) <> ''),
    content_key TEXT NOT NULL CHECK (btrim(content_key) <> ''),
    title TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    current_published_version_id BIGINT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK ((server_scope = 'server' AND server_id IS NOT NULL) OR (server_scope = 'global' AND server_id IS NULL)),
    UNIQUE (server_scope, server_id, content_type, content_key)
);

CREATE INDEX IF NOT EXISTS idx_content_items_scope_type
ON content_items (server_scope, server_id, content_type, updated_at DESC);

CREATE TABLE IF NOT EXISTS content_versions (
    id BIGSERIAL PRIMARY KEY,
    content_item_id BIGINT NOT NULL REFERENCES content_items(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL CHECK (version_number > 0),
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version > 0),
    created_by BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (content_item_id, version_number)
);

CREATE INDEX IF NOT EXISTS idx_content_versions_item_version
ON content_versions (content_item_id, version_number DESC);

ALTER TABLE content_items
    DROP CONSTRAINT IF EXISTS fk_content_items_current_published_version;

ALTER TABLE content_items
    ADD CONSTRAINT fk_content_items_current_published_version
    FOREIGN KEY (current_published_version_id)
    REFERENCES content_versions(id)
    ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS change_requests (
    id BIGSERIAL PRIMARY KEY,
    content_item_id BIGINT NOT NULL REFERENCES content_items(id) ON DELETE CASCADE,
    base_version_id BIGINT NULL REFERENCES content_versions(id) ON DELETE SET NULL,
    candidate_version_id BIGINT NOT NULL REFERENCES content_versions(id) ON DELETE RESTRICT,
    status TEXT NOT NULL CHECK (status IN ('draft', 'in_review', 'approved', 'rejected', 'published', 'rolled_back')),
    proposed_by BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    comment TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_change_requests_item_status
ON change_requests (content_item_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS reviews (
    id BIGSERIAL PRIMARY KEY,
    change_request_id BIGINT NOT NULL REFERENCES change_requests(id) ON DELETE CASCADE,
    reviewer_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    decision TEXT NOT NULL CHECK (decision IN ('approve', 'reject', 'request_changes')),
    comment TEXT NOT NULL DEFAULT '',
    diff_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reviews_change_request
ON reviews (change_request_id, created_at ASC);

CREATE TABLE IF NOT EXISTS publish_batches (
    id BIGSERIAL PRIMARY KEY,
    server_scope TEXT NOT NULL CHECK (server_scope IN ('server', 'global')),
    server_id TEXT NULL REFERENCES servers(code) ON DELETE RESTRICT,
    published_by BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    rollback_of_batch_id BIGINT NULL REFERENCES publish_batches(id) ON DELETE SET NULL,
    summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK ((server_scope = 'server' AND server_id IS NOT NULL) OR (server_scope = 'global' AND server_id IS NULL))
);

CREATE INDEX IF NOT EXISTS idx_publish_batches_scope_created
ON publish_batches (server_scope, server_id, created_at DESC);

CREATE TABLE IF NOT EXISTS publish_batch_items (
    id BIGSERIAL PRIMARY KEY,
    publish_batch_id BIGINT NOT NULL REFERENCES publish_batches(id) ON DELETE CASCADE,
    content_item_id BIGINT NOT NULL REFERENCES content_items(id) ON DELETE CASCADE,
    published_version_id BIGINT NULL REFERENCES content_versions(id) ON DELETE RESTRICT,
    previous_published_version_id BIGINT NULL REFERENCES content_versions(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_publish_batch_items_batch
ON publish_batch_items (publish_batch_id, id ASC);

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    server_id TEXT NULL REFERENCES servers(code) ON DELETE RESTRICT,
    actor_user_id BIGINT NULL REFERENCES users(id) ON DELETE SET NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    before_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    after_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    diff_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    request_id TEXT NOT NULL DEFAULT '',
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_scope_entity_created
ON audit_logs (server_id, entity_type, entity_id, created_at DESC);

CREATE TABLE IF NOT EXISTS generation_snapshots (
    id BIGSERIAL PRIMARY KEY,
    server_id TEXT NOT NULL REFERENCES servers(code) ON DELETE RESTRICT,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    document_kind TEXT NOT NULL CHECK (btrim(document_kind) <> ''),
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_text TEXT NOT NULL DEFAULT '',
    context_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    legacy_generated_document_id BIGINT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE document_versions
    ADD COLUMN IF NOT EXISTS generation_snapshot_id BIGINT NULL;

ALTER TABLE document_versions
    DROP CONSTRAINT IF EXISTS fk_document_versions_generation_snapshot;

ALTER TABLE document_versions
    ADD CONSTRAINT fk_document_versions_generation_snapshot
    FOREIGN KEY (generation_snapshot_id)
    REFERENCES generation_snapshots(id)
    ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_generation_snapshots_user_created_at
ON generation_snapshots (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_generation_snapshots_legacy_id
ON generation_snapshots (legacy_generated_document_id);

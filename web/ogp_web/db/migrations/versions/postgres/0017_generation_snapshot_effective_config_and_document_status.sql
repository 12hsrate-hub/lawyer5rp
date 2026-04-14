ALTER TABLE generation_snapshots
    ADD COLUMN IF NOT EXISTS effective_config_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS content_workflow_ref_json JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE generation_snapshots
    DROP CONSTRAINT IF EXISTS chk_generation_snapshots_effective_config_required;
ALTER TABLE generation_snapshots
    ADD CONSTRAINT chk_generation_snapshots_effective_config_required
    CHECK (
        jsonb_typeof(effective_config_snapshot_json) = 'object'
        AND effective_config_snapshot_json ? 'server_pack_version'
        AND effective_config_snapshot_json ? 'law_set_version'
        AND effective_config_snapshot_json ? 'template_version'
        AND effective_config_snapshot_json ? 'validation_version'
    );

ALTER TABLE generation_snapshots
    DROP CONSTRAINT IF EXISTS chk_generation_snapshots_content_workflow_ref_object;
ALTER TABLE generation_snapshots
    ADD CONSTRAINT chk_generation_snapshots_content_workflow_ref_object
    CHECK (jsonb_typeof(content_workflow_ref_json) = 'object');

CREATE OR REPLACE FUNCTION protect_generation_snapshot_version_binding()
RETURNS trigger AS $$
BEGIN
    IF NEW.effective_config_snapshot_json IS DISTINCT FROM OLD.effective_config_snapshot_json THEN
        RAISE EXCEPTION 'effective_config_snapshot_json is immutable for rollback-safe historical binding';
    END IF;
    IF NEW.content_workflow_ref_json IS DISTINCT FROM OLD.content_workflow_ref_json THEN
        RAISE EXCEPTION 'content_workflow_ref_json is immutable for rollback-safe historical binding';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_generation_snapshot_binding_immutable ON generation_snapshots;
CREATE TRIGGER trg_generation_snapshot_binding_immutable
BEFORE UPDATE ON generation_snapshots
FOR EACH ROW
EXECUTE FUNCTION protect_generation_snapshot_version_binding();

ALTER TABLE case_documents
    DROP CONSTRAINT IF EXISTS case_documents_status_check;

ALTER TABLE case_documents
    ADD CONSTRAINT case_documents_status_check
    CHECK (status IN ('draft', 'reviewed', 'published', 'exported', 'archived'));

CREATE TABLE IF NOT EXISTS document_status_transitions (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES case_documents(id) ON DELETE CASCADE,
    from_status TEXT NULL,
    to_status TEXT NOT NULL CHECK (to_status IN ('draft', 'reviewed', 'published', 'exported', 'archived')),
    actor_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_document_status_transitions_document_created_at
ON document_status_transitions (document_id, created_at DESC);

CREATE OR REPLACE FUNCTION audit_document_status_transition()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO document_status_transitions (document_id, from_status, to_status, actor_user_id, metadata_json)
        VALUES (NEW.id, NULL, NEW.status, NEW.created_by, jsonb_build_object('source', 'insert'));
    ELSIF TG_OP = 'UPDATE' AND NEW.status IS DISTINCT FROM OLD.status THEN
        INSERT INTO document_status_transitions (document_id, from_status, to_status, actor_user_id, metadata_json)
        VALUES (
            NEW.id,
            OLD.status,
            NEW.status,
            COALESCE((NEW.metadata_json->'status_actor_user_id')::bigint, NEW.created_by),
            jsonb_build_object('source', 'status_update')
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_case_documents_status_transition ON case_documents;
CREATE TRIGGER trg_case_documents_status_transition
AFTER INSERT OR UPDATE OF status ON case_documents
FOR EACH ROW
EXECUTE FUNCTION audit_document_status_transition();

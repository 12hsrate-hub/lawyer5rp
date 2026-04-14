ALTER TABLE complaint_drafts
    ADD COLUMN IF NOT EXISTS document_type TEXT NOT NULL DEFAULT 'complaint';

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'complaint_drafts_user_id_server_code_key'
    ) THEN
        ALTER TABLE complaint_drafts
            DROP CONSTRAINT complaint_drafts_user_id_server_code_key;
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_complaint_drafts_user_server_document
ON complaint_drafts (user_id, server_code, document_type);

CREATE INDEX IF NOT EXISTS idx_complaint_drafts_document_type
ON complaint_drafts (document_type);

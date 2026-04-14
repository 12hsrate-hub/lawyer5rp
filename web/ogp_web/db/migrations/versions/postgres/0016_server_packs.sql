CREATE TABLE IF NOT EXISTS server_packs (
    id BIGSERIAL PRIMARY KEY,
    server_code TEXT NOT NULL REFERENCES servers(code) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ,
    UNIQUE (server_code, version)
);

CREATE INDEX IF NOT EXISTS idx_server_packs_lookup
ON server_packs (server_code, status, published_at DESC, version DESC);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'server_packs_status_check'
    ) THEN
        ALTER TABLE server_packs
            ADD CONSTRAINT server_packs_status_check
            CHECK (status IN ('draft', 'published'));
    END IF;
END $$;

WITH blackberry_seed AS (
    SELECT
        'blackberry'::text AS server_code,
        1::integer AS version,
        'published'::text AS status,
        jsonb_build_object(
            'organizations', jsonb_build_array('LSPD', 'GOV', 'FIB', 'LSSD', 'ARMY', 'SANG', 'EMS', 'WN'),
            'procedure_types', jsonb_build_array('detention', 'search', 'inspection', 'arrest'),
            'complaint_bases', jsonb_build_array(
                jsonb_build_object('code', 'wrongful_article', 'label', 'Неверная квалификация', 'description', 'Спор по применённой статье или правовой квалификации.'),
                jsonb_build_object('code', 'no_materials_by_request', 'label', 'Не выдали материалы', 'description', 'Материалы не предоставлены по запросу адвоката.'),
                jsonb_build_object('code', 'no_video_or_no_evidence', 'label', 'Нет видео или доказательств', 'description', 'Отсутствуют видеоматериалы или надлежащая доказательная база.')
            ),
            'form_schema', jsonb_build_object('complaint', jsonb_build_object('version', 'v1', 'sections', jsonb_build_array('incident', 'victim', 'representative', 'evidence'))),
            'validation_profiles', jsonb_build_object('complaint_default', jsonb_build_object('required_sections', jsonb_build_array('incident', 'victim', 'evidence'))),
            'template_bindings', jsonb_build_object(
                'complaint', jsonb_build_object('template_key', 'complaint_v1', 'document_type', 'complaint'),
                'rehab', jsonb_build_object('template_key', 'rehab_v1', 'document_type', 'rehab')
            ),
            'terminology', jsonb_build_object('complaint', 'Жалоба', 'rehab', 'Реабилитация', 'court_claim', 'Исковое заявление')
        ) AS metadata_json
)
INSERT INTO server_packs (server_code, version, status, metadata_json, published_at)
SELECT server_code, version, status, metadata_json, NOW()
FROM blackberry_seed
ON CONFLICT (server_code, version) DO NOTHING;

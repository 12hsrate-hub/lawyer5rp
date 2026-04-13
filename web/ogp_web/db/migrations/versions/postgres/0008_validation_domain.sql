CREATE TABLE IF NOT EXISTS law_qa_runs (
    id BIGSERIAL PRIMARY KEY,
    server_id TEXT NOT NULL REFERENCES servers(code) ON DELETE RESTRICT,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    question TEXT NOT NULL DEFAULT '',
    answer_text TEXT NOT NULL DEFAULT '',
    used_sources_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    selected_norms_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_law_qa_runs_server_created_at
ON law_qa_runs (server_id, created_at DESC);

CREATE TABLE IF NOT EXISTS validation_requirements (
    id BIGSERIAL PRIMARY KEY,
    server_scope TEXT NOT NULL CHECK (server_scope IN ('server', 'global')),
    server_id TEXT NULL REFERENCES servers(code) ON DELETE RESTRICT,
    target_type TEXT NOT NULL CHECK (target_type IN ('document_version', 'law_qa_run')),
    target_subtype TEXT NOT NULL DEFAULT '',
    field_key TEXT NOT NULL CHECK (btrim(field_key) <> ''),
    rule_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_required BOOLEAN NOT NULL DEFAULT TRUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_validation_requirements_server_scope
        CHECK (
            (server_scope = 'global' AND server_id IS NULL)
            OR (server_scope = 'server' AND server_id IS NOT NULL)
        )
);

CREATE INDEX IF NOT EXISTS idx_validation_requirements_lookup
ON validation_requirements (target_type, target_subtype, server_scope, server_id, is_active);

CREATE TABLE IF NOT EXISTS readiness_gates (
    id BIGSERIAL PRIMARY KEY,
    server_scope TEXT NOT NULL CHECK (server_scope IN ('server', 'global')),
    server_id TEXT NULL REFERENCES servers(code) ON DELETE RESTRICT,
    target_type TEXT NOT NULL CHECK (target_type IN ('document_version', 'law_qa_run')),
    target_subtype TEXT NOT NULL DEFAULT '',
    gate_code TEXT NOT NULL CHECK (btrim(gate_code) <> ''),
    enforcement_mode TEXT NOT NULL CHECK (enforcement_mode IN ('off', 'warn', 'hard_block')),
    threshold_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_readiness_gates_server_scope
        CHECK (
            (server_scope = 'global' AND server_id IS NULL)
            OR (server_scope = 'server' AND server_id IS NOT NULL)
        )
);

CREATE INDEX IF NOT EXISTS idx_readiness_gates_lookup
ON readiness_gates (target_type, target_subtype, server_scope, server_id, is_active);

CREATE TABLE IF NOT EXISTS validation_runs (
    id BIGSERIAL PRIMARY KEY,
    target_type TEXT NOT NULL CHECK (target_type IN ('document_version', 'law_qa_run')),
    target_id BIGINT NOT NULL,
    server_id TEXT NOT NULL REFERENCES servers(code) ON DELETE RESTRICT,
    status TEXT NOT NULL CHECK (status IN ('pass', 'warn', 'fail')),
    risk_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    coverage_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    readiness_status TEXT NOT NULL CHECK (readiness_status IN ('ready', 'needs_review', 'blocked')),
    summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    score_breakdown_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    gate_decisions_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_validation_runs_target_created_at
ON validation_runs (target_type, target_id, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS validation_issues (
    id BIGSERIAL PRIMARY KEY,
    validation_run_id BIGINT NOT NULL REFERENCES validation_runs(id) ON DELETE CASCADE,
    issue_code TEXT NOT NULL CHECK (btrim(issue_code) <> ''),
    severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'error')),
    message TEXT NOT NULL,
    field_ref TEXT NOT NULL DEFAULT '',
    details_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_validation_issues_run
ON validation_issues (validation_run_id, created_at ASC, id ASC);

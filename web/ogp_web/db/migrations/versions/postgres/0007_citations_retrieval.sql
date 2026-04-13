CREATE TABLE IF NOT EXISTS retrieval_runs (
    id BIGSERIAL PRIMARY KEY,
    server_id TEXT NOT NULL REFERENCES servers(code) ON DELETE RESTRICT,
    run_type TEXT NOT NULL CHECK (run_type IN ('law_qa', 'document_generation')),
    actor_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    query_text TEXT NOT NULL DEFAULT '',
    effective_versions_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    retrieved_sources_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    policy_status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_retrieval_runs_server_created_at
ON retrieval_runs (server_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_retrieval_runs_actor_created_at
ON retrieval_runs (actor_user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS law_qa_runs (
    id BIGSERIAL PRIMARY KEY,
    server_id TEXT NOT NULL REFERENCES servers(code) ON DELETE RESTRICT,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    question TEXT NOT NULL DEFAULT '',
    answer_text TEXT NOT NULL DEFAULT '',
    retrieval_run_id BIGINT NOT NULL REFERENCES retrieval_runs(id) ON DELETE RESTRICT,
    snapshot_id TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_law_qa_runs_server_created_at
ON law_qa_runs (server_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_law_qa_runs_retrieval_run_id
ON law_qa_runs (retrieval_run_id);

CREATE TABLE IF NOT EXISTS document_version_citations (
    id BIGSERIAL PRIMARY KEY,
    document_version_id BIGINT NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
    retrieval_run_id BIGINT NOT NULL REFERENCES retrieval_runs(id) ON DELETE RESTRICT,
    citation_type TEXT NOT NULL DEFAULT 'norm',
    source_type TEXT NOT NULL,
    source_id BIGINT NOT NULL,
    source_version_id BIGINT NOT NULL,
    canonical_ref TEXT NOT NULL DEFAULT '',
    quoted_text TEXT NOT NULL DEFAULT '',
    usage_type TEXT NOT NULL DEFAULT 'supporting',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_document_version_citations_version_created
ON document_version_citations (document_version_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_document_version_citations_retrieval
ON document_version_citations (retrieval_run_id);

CREATE TABLE IF NOT EXISTS answer_citations (
    id BIGSERIAL PRIMARY KEY,
    law_qa_run_id BIGINT NOT NULL REFERENCES law_qa_runs(id) ON DELETE CASCADE,
    retrieval_run_id BIGINT NOT NULL REFERENCES retrieval_runs(id) ON DELETE RESTRICT,
    citation_type TEXT NOT NULL DEFAULT 'norm',
    source_type TEXT NOT NULL,
    source_id BIGINT NOT NULL,
    source_version_id BIGINT NOT NULL,
    canonical_ref TEXT NOT NULL DEFAULT '',
    quoted_text TEXT NOT NULL DEFAULT '',
    usage_type TEXT NOT NULL DEFAULT 'supporting',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_answer_citations_law_qa_run_created
ON answer_citations (law_qa_run_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_answer_citations_retrieval
ON answer_citations (retrieval_run_id);

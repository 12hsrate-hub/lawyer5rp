CREATE TABLE IF NOT EXISTS auth_rate_limit_events (
    action TEXT NOT NULL,
    subject_key TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_auth_rate_limit_lookup
ON auth_rate_limit_events (action, subject_key, created_at);

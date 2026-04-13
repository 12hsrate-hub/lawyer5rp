CREATE TABLE IF NOT EXISTS permissions (
    id BIGSERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS roles (
    id BIGSERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_id BIGINT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id BIGINT NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE IF NOT EXISTS user_roles (
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id BIGINT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    server_id TEXT NULL REFERENCES servers(code) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, role_id, server_id)
);

CREATE INDEX IF NOT EXISTS idx_user_roles_user_id ON user_roles (user_id);
CREATE INDEX IF NOT EXISTS idx_user_roles_server_id ON user_roles (server_id);

INSERT INTO permissions (code, description)
VALUES
    ('manage_servers', 'Manage admin users, flags, and server level settings'),
    ('manage_laws', 'Manage legal and exam-related administrative actions'),
    ('view_analytics', 'Access metrics dashboards and exports'),
    ('court_claims', 'Access test pages for court claims and law Q&A'),
    ('exam_import', 'Access exam import pages and API'),
    ('complaint_presets', 'Access complaint test presets')
ON CONFLICT (code) DO NOTHING;

INSERT INTO roles (code, name)
VALUES
    ('super_admin', 'Super Admin'),
    ('analytics_viewer', 'Analytics Viewer'),
    ('law_manager', 'Law Manager'),
    ('tester', 'Tester'),
    ('gka', 'GKA')
ON CONFLICT (code) DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r
JOIN permissions p ON (
    (r.code = 'super_admin' AND p.code IN ('manage_servers', 'manage_laws', 'view_analytics', 'court_claims', 'exam_import', 'complaint_presets')) OR
    (r.code = 'analytics_viewer' AND p.code IN ('view_analytics')) OR
    (r.code = 'law_manager' AND p.code IN ('manage_laws', 'exam_import')) OR
    (r.code = 'tester' AND p.code IN ('court_claims')) OR
    (r.code = 'gka' AND p.code IN ('exam_import', 'complaint_presets'))
)
ON CONFLICT (role_id, permission_id) DO NOTHING;

INSERT INTO user_roles (user_id, role_id, server_id)
SELECT usr.user_id, role_tbl.id, usr.server_code
FROM user_server_roles usr
JOIN roles role_tbl ON role_tbl.code = 'tester'
WHERE usr.is_tester = TRUE
ON CONFLICT (user_id, role_id, server_id) DO NOTHING;

INSERT INTO user_roles (user_id, role_id, server_id)
SELECT usr.user_id, role_tbl.id, usr.server_code
FROM user_server_roles usr
JOIN roles role_tbl ON role_tbl.code = 'gka'
WHERE usr.is_gka = TRUE
ON CONFLICT (user_id, role_id, server_id) DO NOTHING;

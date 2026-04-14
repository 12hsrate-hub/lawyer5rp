INSERT INTO permissions (code, description)
VALUES
    ('manage_runtime_servers', 'Manage runtime server entities and activation lifecycle'),
    ('manage_law_sets', 'Create and manage law sets, law set items, and source registry'),
    ('publish_law_sets', 'Publish law sets and execute rollback/promotion actions')
ON CONFLICT (code) DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r
JOIN permissions p ON (
    (r.code = 'super_admin' AND p.code IN ('manage_runtime_servers', 'manage_law_sets', 'publish_law_sets')) OR
    (r.code = 'law_manager' AND p.code IN ('manage_law_sets', 'publish_law_sets'))
)
ON CONFLICT (role_id, permission_id) DO NOTHING;

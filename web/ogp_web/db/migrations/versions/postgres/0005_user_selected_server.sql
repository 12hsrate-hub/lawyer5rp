CREATE TABLE IF NOT EXISTS user_selected_servers (
    user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    server_code TEXT NOT NULL REFERENCES servers(code) ON DELETE CASCADE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_selected_servers_server_code
ON user_selected_servers (server_code);

INSERT INTO user_selected_servers (user_id, server_code)
SELECT usr.user_id, usr.server_code
FROM user_server_roles usr
JOIN (
    SELECT user_id, MIN(server_code) AS server_code
    FROM user_server_roles
    GROUP BY user_id
) first_role
  ON first_role.user_id = usr.user_id
 AND first_role.server_code = usr.server_code
ON CONFLICT (user_id) DO NOTHING;

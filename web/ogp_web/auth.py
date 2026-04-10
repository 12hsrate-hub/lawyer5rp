from __future__ import annotations

from ogp_web.services.auth_service import (
    SESSION_COOKIE_NAME,
    AuthError,
    AuthUser,
    clear_auth_cookie,
    create_session_token,
    get_current_user,
    parse_session_token,
    require_user,
    set_auth_cookie,
)
from ogp_web.storage.user_store import USER_STORE

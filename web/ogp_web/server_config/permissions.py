from __future__ import annotations

from dataclasses import dataclass

from ogp_web.env import is_test_user
from ogp_web.services.auth_service import is_admin_user
from ogp_web.storage.user_store import UserStore

from .types import ServerConfig


@dataclass(frozen=True)
class PermissionSet:
    is_admin: bool
    is_tester: bool
    is_gka: bool
    server_code: str

    @property
    def can_access_exam_import(self) -> bool:
        return self.is_gka

    @property
    def can_access_complaint_presets(self) -> bool:
        return self.is_gka

    @property
    def can_access_court_claims(self) -> bool:
        return self.is_tester

    def allows(self, permission: str) -> bool:
        if not permission:
            return True
        if permission == "admin":
            return self.is_admin
        if permission == "exam_import":
            return self.can_access_exam_import
        if permission == "court_claims":
            return self.can_access_court_claims
        return False


def build_permission_set(store: UserStore, username: str, server_config: ServerConfig) -> PermissionSet:
    normalized_username = str(username or "").strip().lower()
    is_admin = is_admin_user(normalized_username)
    test_user = is_test_user(normalized_username)
    is_gka = test_user or store.is_gka_user(normalized_username, server_code=server_config.code)
    is_tester = test_user or store.is_tester_user(normalized_username, server_code=server_config.code)
    return PermissionSet(
        is_admin=is_admin,
        is_tester=is_tester,
        is_gka=is_gka,
        server_code=server_config.code,
    )

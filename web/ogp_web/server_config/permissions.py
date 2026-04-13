from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ogp_web.env import is_test_user
from ogp_web.services.auth_service import is_admin_user

from .types import ServerConfig

if TYPE_CHECKING:
    from ogp_web.storage.user_store import UserStore


@dataclass(frozen=True)
class PermissionSet:
    codes: frozenset[str]
    server_code: str

    def has(self, permission: str) -> bool:
        normalized = str(permission or "").strip().lower()
        if not normalized:
            return True
        return normalized in self.codes

    @property
    def is_admin(self) -> bool:
        return self.has("manage_servers")

    @property
    def is_tester(self) -> bool:
        return self.has("court_claims")

    @property
    def is_gka(self) -> bool:
        return self.has("exam_import")

    @property
    def can_access_exam_import(self) -> bool:
        return self.has("exam_import")

    @property
    def can_access_complaint_presets(self) -> bool:
        return self.has("complaint_presets")

    @property
    def can_access_court_claims(self) -> bool:
        return self.has("court_claims")

    def allows(self, permission: str) -> bool:
        return self.has(permission)


def build_permission_set(store: UserStore, username: str, server_config: ServerConfig) -> PermissionSet:
    normalized_username = str(username or "").strip().lower()
    codes = set(store.get_permission_codes(normalized_username, server_code=server_config.code))

    if is_admin_user(normalized_username):
        codes.update({"manage_servers", "manage_laws", "view_analytics"})
    if is_test_user(normalized_username):
        codes.update({"court_claims", "exam_import", "complaint_presets"})

    return PermissionSet(codes=frozenset(codes), server_code=server_config.code)

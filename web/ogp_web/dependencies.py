from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status

from ogp_web.server_config import PermissionSet, build_permission_set, get_server_config
from ogp_web.services.auth_service import AuthUser, require_user
from ogp_web.storage.admin_metrics_store import AdminMetricsStore, get_default_admin_metrics_store
from ogp_web.storage.admin_catalog_store import AdminCatalogStore, get_default_admin_catalog_store
from ogp_web.services.exam_import_tasks import ExamImportTaskRegistry
from ogp_web.storage.exam_answers_store import ExamAnswersStore, get_default_exam_answers_store
from ogp_web.storage.user_store import UserStore, get_default_user_store


def get_user_store(request: Request) -> UserStore:
    store = getattr(request.app.state, "user_store", None)
    if store is None:
        return get_default_user_store()
    return store


def get_exam_answers_store(request: Request) -> ExamAnswersStore:
    store = getattr(request.app.state, "exam_answers_store", None)
    if store is None:
        return get_default_exam_answers_store()
    return store


def get_admin_metrics_store(request: Request) -> AdminMetricsStore:
    store = getattr(request.app.state, "admin_metrics_store", None)
    if store is None:
        return get_default_admin_metrics_store()
    return store




def get_admin_catalog_store(request: Request) -> AdminCatalogStore:
    store = getattr(request.app.state, "admin_catalog_store", None)
    if store is None:
        return get_default_admin_catalog_store()
    return store
def get_exam_import_task_registry(request: Request) -> ExamImportTaskRegistry:
    return request.app.state.exam_import_task_registry


def get_server_config_for_request(request: Request):
    return request.app.state.server_config


def get_server_config_for_user(request: Request | None, user_store: UserStore, username: str):
    return get_server_config(user_store.get_server_code(username))


def get_permission_set_for_user(request: Request, user_store: UserStore, username: str) -> PermissionSet:
    server_config = get_server_config_for_user(request, user_store, username)
    return build_permission_set(user_store, username, server_config)


def requires_permission(permission_code: str = ""):
    def _guard(
        user: AuthUser = Depends(require_user),
        user_store: UserStore = Depends(get_user_store),
    ) -> AuthUser:
        server_config = get_server_config_for_user(None, user_store, user.username)
        permissions = build_permission_set(user_store, user.username, server_config)
        if permission_code and not permissions.has(permission_code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=[f"Недостаточно прав: требуется permission '{permission_code}'."],
            )
        return user

    return _guard

from __future__ import annotations

from fastapi import Request

from ogp_web.server_config import PermissionSet, build_permission_set, get_server_config
from ogp_web.storage.admin_metrics_store import AdminMetricsStore, get_default_admin_metrics_store
from ogp_web.services.exam_import_tasks import ExamImportTaskRegistry
from ogp_web.storage.exam_answers_store import ExamAnswersStore, get_default_exam_answers_store
from ogp_web.storage.law_qa_store import LawQaStore, get_default_law_qa_store
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


def get_law_qa_store(request: Request) -> LawQaStore:
    store = getattr(request.app.state, "law_qa_store", None)
    if store is None:
        return get_default_law_qa_store()
    return store


def get_exam_import_task_registry(request: Request) -> ExamImportTaskRegistry:
    return request.app.state.exam_import_task_registry


def get_server_config_for_request(request: Request):
    return request.app.state.server_config


def get_server_config_for_user(request: Request, user_store: UserStore, username: str):
    return get_server_config(user_store.get_server_code(username))


def get_permission_set_for_user(request: Request, user_store: UserStore, username: str) -> PermissionSet:
    server_config = get_server_config_for_user(request, user_store, username)
    return build_permission_set(user_store, username, server_config)

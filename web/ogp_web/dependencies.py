from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status

from ogp_web.db.factory import get_database_backend
from ogp_web.server_config import PermissionSet, build_permission_set, get_server_config
from ogp_web.services.auth_service import AuthUser, require_user
from ogp_web.storage.admin_metrics_store import AdminMetricsStore, get_default_admin_metrics_store
from ogp_web.storage.admin_catalog_store import AdminCatalogStore, get_default_admin_catalog_store
from ogp_web.services.exam_import_tasks import ExamImportTaskRegistry
from ogp_web.services.feature_flags import FeatureFlagService
from ogp_web.services.content_workflow_service import ContentWorkflowService
from ogp_web.services.admin_dashboard_service import AdminDashboardService
from ogp_web.services.admin_analytics_service import AdminAnalyticsService
from ogp_web.services.admin_ai_pipeline_service import AdminAiPipelineService
from ogp_web.services.admin_task_ops_service import AdminTaskOpsService
from ogp_web.services.jobs_runtime_service import JobsRuntimeService
from ogp_web.storage.exam_answers_store import ExamAnswersStore, get_default_exam_answers_store
from ogp_web.storage.user_store import UserStore, get_default_user_store
from ogp_web.storage.content_workflow_repository import ContentWorkflowRepository
from ogp_web.storage.admin_dashboard_repository import AdminDashboardRepository
from ogp_web.storage.law_source_sets_store import LawSourceSetsStore
from ogp_web.storage.runtime_servers_store import RuntimeServersStore
from ogp_web.storage.runtime_law_sets_store import RuntimeLawSetsStore

_DEFAULT_ADMIN_TASK_OPS_SERVICE = AdminTaskOpsService()
_DEFAULT_JOBS_RUNTIME_SERVICE = JobsRuntimeService()


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



def get_content_workflow_service(request: Request) -> ContentWorkflowService:
    service = getattr(request.app.state, "content_workflow_service", None)
    if service is not None:
        return service
    backend = get_database_backend()
    repository = ContentWorkflowRepository(backend)
    legacy_store = get_admin_catalog_store(request)
    return ContentWorkflowService(repository, legacy_store=legacy_store)



def get_admin_dashboard_repository(request: Request) -> AdminDashboardRepository:
    repository = getattr(request.app.state, "admin_dashboard_repository", None)
    if repository is not None:
        return repository
    backend = get_database_backend()
    return AdminDashboardRepository(backend)


def get_admin_dashboard_service(
    request: Request,
    repository: AdminDashboardRepository = Depends(get_admin_dashboard_repository),
) -> AdminDashboardService:
    service = getattr(request.app.state, "admin_dashboard_service", None)
    if service is not None:
        return service
    return AdminDashboardService(repository)


def get_admin_analytics_service(request: Request) -> AdminAnalyticsService:
    service = getattr(request.app.state, "admin_analytics_service", None)
    if service is not None:
        return service
    return AdminAnalyticsService()


def get_admin_ai_pipeline_service(request: Request) -> AdminAiPipelineService:
    service = getattr(request.app.state, "admin_ai_pipeline_service", None)
    if service is not None:
        return service
    return AdminAiPipelineService()


def get_admin_task_ops_service(request: Request) -> AdminTaskOpsService:
    service = getattr(request.app.state, "admin_task_ops_service", None)
    if service is not None:
        return service
    return _DEFAULT_ADMIN_TASK_OPS_SERVICE


def get_jobs_runtime_service(request: Request) -> JobsRuntimeService:
    service = getattr(request.app.state, "jobs_runtime_service", None)
    if service is not None:
        return service
    return _DEFAULT_JOBS_RUNTIME_SERVICE


def get_runtime_servers_store(_: Request) -> RuntimeServersStore:
    backend = get_database_backend()
    return RuntimeServersStore(backend)


def get_runtime_law_sets_store(_: Request) -> RuntimeLawSetsStore:
    backend = get_database_backend()
    return RuntimeLawSetsStore(backend)


def get_law_source_sets_store(_: Request) -> LawSourceSetsStore:
    backend = get_database_backend()
    return LawSourceSetsStore(backend)

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


def get_feature_flag_service(_: Request) -> FeatureFlagService:
    return FeatureFlagService()

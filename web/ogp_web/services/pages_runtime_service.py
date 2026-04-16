from __future__ import annotations

from ogp_web.db.factory import get_database_backend
from ogp_web.server_config import ServerConfig
from ogp_web.services.ai_service import get_default_law_qa_model
from ogp_web.services.content_workflow_service import ContentWorkflowService
from ogp_web.services.law_admin_service import LawAdminService
from ogp_web.services.server_context_service import (
    extract_server_complaint_settings,
    extract_server_identity_settings,
    list_servers_with_law_qa_context,
    resolve_server_law_sources,
)
from ogp_web.storage.content_workflow_repository import ContentWorkflowRepository
from ogp_web.storage.exam_answers_store import ExamAnswersStore


def _build_law_admin_service() -> LawAdminService:
    return LawAdminService(
        ContentWorkflowService(ContentWorkflowRepository(get_database_backend()), legacy_store=None)
    )


def build_exam_import_page_data(*, server_config: ServerConfig, exam_store: ExamAnswersStore) -> dict[str, object]:
    complaint_settings = extract_server_complaint_settings(server_config)
    return {
        "exam_sheet_url": complaint_settings.exam_sheet_url,
        "exam_entries": exam_store.list_entries(limit=20, offset=0),
        "exam_total_rows": exam_store.count(),
    }


def build_law_qa_test_page_data(*, server_config: ServerConfig) -> dict[str, object]:
    server_identity = extract_server_identity_settings(server_config)
    law_sources = list(resolve_server_law_sources(server_code=server_identity.code))
    try:
        law_sources_snapshot = _build_law_admin_service().get_effective_sources(server_code=server_identity.code)
        law_sources = list(law_sources_snapshot.source_urls)
    except Exception:
        # Allow law QA page rendering in tests/local runtimes without PostgreSQL.
        law_sources = list(resolve_server_law_sources(server_code=server_identity.code))
    return {
        "law_qa_servers": list_servers_with_law_qa_context(),
        "law_qa_sources": law_sources,
        "law_qa_default_model": get_default_law_qa_model(),
    }

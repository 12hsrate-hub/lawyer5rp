from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ogp_web.dependencies import get_feature_flag_service, requires_permission, get_user_store
from ogp_web.schemas_cases import (
    CaseCreateRequest,
    CaseDocumentCreateRequest,
    CaseDocumentResponse,
    CaseResponse,
    DocumentVersionCreateRequest,
    DocumentVersionListResponse,
    DocumentVersionResponse,
)
from ogp_web.services.auth_service import AuthUser
from ogp_web.services.case_service import CaseService
from ogp_web.services.document_service import DocumentService
from ogp_web.storage.case_repository import CaseRepository
from ogp_web.storage.document_repository import DocumentRepository
from ogp_web.storage.user_store import UserStore
from ogp_web.services.feature_flags import FeatureFlagService, RolloutContext


router = APIRouter(tags=["cases"])


def _ensure_enabled(*, flag_service: FeatureFlagService, flag: str, username: str, server_id: str) -> None:
    decision = flag_service.evaluate(flag=flag, context=RolloutContext(username=username, server_id=server_id))
    if not decision.use_new_flow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=[f"Endpoint disabled by feature flag '{flag}' (mode={decision.mode.value}, cohort={decision.cohort.value})."],
        )


def _case_service(store: UserStore) -> CaseService:
    return CaseService(CaseRepository(store.backend))


def _document_service(store: UserStore) -> DocumentService:
    return DocumentService(
        case_repository=CaseRepository(store.backend),
        document_repository=DocumentRepository(store.backend),
    )


@router.post("/api/cases", response_model=CaseResponse)
async def create_case(
    payload: CaseCreateRequest,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
    flag_service: FeatureFlagService = Depends(get_feature_flag_service),
) -> CaseResponse:
    _ensure_enabled(flag_service=flag_service, flag="cases_v1", username=user.username, server_id=user.server_code)
    case_payload = _case_service(store).create_case(
        username=user.username,
        user_server_id=user.server_code,
        server_id=payload.server_id,
        title=payload.title,
        case_type=payload.case_type,
    )
    return CaseResponse(**case_payload)


@router.get("/api/cases/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: int,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
    flag_service: FeatureFlagService = Depends(get_feature_flag_service),
) -> CaseResponse:
    _ensure_enabled(flag_service=flag_service, flag="cases_v1", username=user.username, server_id=user.server_code)
    return CaseResponse(**_case_service(store).get_case(case_id=case_id, user_server_id=user.server_code))


@router.post("/api/cases/{case_id}/documents", response_model=CaseDocumentResponse)
async def add_case_document(
    case_id: int,
    payload: CaseDocumentCreateRequest,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
    flag_service: FeatureFlagService = Depends(get_feature_flag_service),
) -> CaseDocumentResponse:
    _ensure_enabled(flag_service=flag_service, flag="documents_v2", username=user.username, server_id=user.server_code)
    return CaseDocumentResponse(
        **_document_service(store).add_document(
            username=user.username,
            user_server_id=user.server_code,
            case_id=case_id,
            document_type=payload.document_type,
        )
    )


@router.get("/api/cases/{case_id}/documents", response_model=list[CaseDocumentResponse])
async def list_case_documents(
    case_id: int,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
    flag_service: FeatureFlagService = Depends(get_feature_flag_service),
) -> list[CaseDocumentResponse]:
    _ensure_enabled(flag_service=flag_service, flag="documents_v2", username=user.username, server_id=user.server_code)
    items = _document_service(store).list_case_documents(user_server_id=user.server_code, case_id=case_id)
    return [CaseDocumentResponse(**item) for item in items]


@router.post("/api/documents/{document_id}/versions", response_model=DocumentVersionResponse)
async def create_document_version(
    document_id: int,
    payload: DocumentVersionCreateRequest,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
    flag_service: FeatureFlagService = Depends(get_feature_flag_service),
) -> DocumentVersionResponse:
    _ensure_enabled(flag_service=flag_service, flag="documents_v2", username=user.username, server_id=user.server_code)
    item = _document_service(store).create_document_version(
        username=user.username,
        user_server_id=user.server_code,
        document_id=document_id,
        content_json=payload.content_json,
    )
    return DocumentVersionResponse(**item)


@router.get("/api/documents/{document_id}/versions", response_model=DocumentVersionListResponse)
async def list_document_versions(
    document_id: int,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
    flag_service: FeatureFlagService = Depends(get_feature_flag_service),
) -> DocumentVersionListResponse:
    _ensure_enabled(flag_service=flag_service, flag="documents_v2", username=user.username, server_id=user.server_code)
    items = _document_service(store).list_document_versions(
        user_server_id=user.server_code,
        document_id=document_id,
    )
    return DocumentVersionListResponse(items=[DocumentVersionResponse(**item) for item in items])

from __future__ import annotations

from fastapi import APIRouter, Depends

from ogp_web.dependencies import requires_permission, get_user_store
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


router = APIRouter(tags=["cases"])


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
) -> CaseResponse:
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
) -> CaseResponse:
    return CaseResponse(**_case_service(store).get_case(case_id=case_id, user_server_id=user.server_code))


@router.post("/api/cases/{case_id}/documents", response_model=CaseDocumentResponse)
async def add_case_document(
    case_id: int,
    payload: CaseDocumentCreateRequest,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
) -> CaseDocumentResponse:
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
) -> list[CaseDocumentResponse]:
    items = _document_service(store).list_case_documents(user_server_id=user.server_code, case_id=case_id)
    return [CaseDocumentResponse(**item) for item in items]


@router.post("/api/documents/{document_id}/versions", response_model=DocumentVersionResponse)
async def create_document_version(
    document_id: int,
    payload: DocumentVersionCreateRequest,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
) -> DocumentVersionResponse:
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
) -> DocumentVersionListResponse:
    items = _document_service(store).list_document_versions(
        user_server_id=user.server_code,
        document_id=document_id,
    )
    return DocumentVersionListResponse(items=[DocumentVersionResponse(**item) for item in items])

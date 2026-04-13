from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ogp_web.dependencies import get_user_store, requires_permission
from ogp_web.schemas_validation import ValidationRunResponse
from ogp_web.services.auth_service import AuthUser
from ogp_web.services.validation_service import ValidationService
from ogp_web.storage.user_store import UserStore
from ogp_web.storage.validation_repository import ValidationRepository


router = APIRouter(tags=["validation"])


def _validation_service(store: UserStore) -> ValidationService:
    return ValidationService(ValidationRepository(store.backend))


@router.get("/api/document-versions/{version_id}/validation", response_model=ValidationRunResponse)
async def get_document_version_validation(
    version_id: int,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
) -> ValidationRunResponse:
    payload = _validation_service(store).get_latest_target_validation(target_type="document_version", target_id=version_id)
    if not payload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Validation run not found."])
    if str(payload.get("server_id") or "") != user.server_code:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=["Cross-server validation access denied."])
    return ValidationRunResponse(**payload)


@router.get("/api/law-qa-runs/{run_id}/validation", response_model=ValidationRunResponse)
async def get_law_qa_run_validation(
    run_id: int,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
) -> ValidationRunResponse:
    payload = _validation_service(store).get_latest_target_validation(target_type="law_qa_run", target_id=run_id)
    if not payload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Validation run not found."])
    if str(payload.get("server_id") or "") != user.server_code:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=["Cross-server validation access denied."])
    return ValidationRunResponse(**payload)


@router.get("/api/validation-runs/{run_id}", response_model=ValidationRunResponse)
async def get_validation_run(
    run_id: int,
    user: AuthUser = Depends(requires_permission()),
    store: UserStore = Depends(get_user_store),
) -> ValidationRunResponse:
    payload = _validation_service(store).get_validation_run_details(run_id=run_id)
    if not payload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Validation run not found."])
    if str(payload.get("server_id") or "") != user.server_code:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=["Cross-server validation access denied."])
    return ValidationRunResponse(**payload)

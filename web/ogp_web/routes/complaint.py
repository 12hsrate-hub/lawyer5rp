from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ogp_web.dependencies import get_admin_metrics_store, get_user_store
from ogp_web.schemas import (
    ComplaintDraftPayload,
    ComplaintDraftResponse,
    ComplaintPayload,
    GenerateResponse,
    LawQaPayload,
    LawQaResponse,
    PrincipalScanPayload,
    PrincipalScanResult,
    RehabPayload,
    SuggestPayload,
    SuggestResponse,
)
from ogp_web.server_config import get_server_config
from ogp_web.services.ai_service import answer_law_question, extract_principal_scan, suggest_text
from ogp_web.services.auth_service import AuthUser, require_user
from ogp_web.services.complaint_service import generate_bbcode_text, generate_rehab_bbcode_text
from ogp_web.storage.admin_metrics_store import AdminMetricsStore
from ogp_web.storage.user_store import UserStore


router = APIRouter(tags=["complaint"])


def _server_config_for_user(store: UserStore, user: AuthUser):
    return get_server_config(user.server_code or store.get_server_code(user.username))


def _validate_server_payload(store: UserStore, user: AuthUser, *, org: str = "", complaint_basis: str = "") -> None:
    server_config = _server_config_for_user(store, user)
    normalized_org = str(org or "").strip()
    normalized_basis = str(complaint_basis or "").strip()
    if normalized_org and server_config.organizations and normalized_org not in server_config.organizations:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=[f"Организация {normalized_org!r} не относится к серверу {server_config.name}."],
        )
    allowed_bases = set(server_config.complaint_basis_codes())
    if normalized_basis and allowed_bases and normalized_basis not in allowed_bases:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=[f"Основание жалобы {normalized_basis!r} не поддерживается для сервера {server_config.name}."],
        )


@router.get("/api/complaint-draft", response_model=ComplaintDraftResponse)
async def get_complaint_draft(
    user: AuthUser = Depends(require_user),
    store: UserStore = Depends(get_user_store),
) -> ComplaintDraftResponse:
    draft = store.get_complaint_draft(user.username)
    return ComplaintDraftResponse(
        draft=draft.get("draft", {}),
        updated_at=str(draft.get("updated_at", "") or ""),
        message="Черновик жалобы загружен.",
    )


@router.put("/api/complaint-draft", response_model=ComplaintDraftResponse)
async def save_complaint_draft(
    payload: ComplaintDraftPayload,
    user: AuthUser = Depends(require_user),
    store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
) -> ComplaintDraftResponse:
    draft = store.save_complaint_draft(user.username, payload.draft)
    metrics_store.log_event(
        event_type="complaint_draft_saved",
        username=user.username,
        path="/api/complaint-draft",
        method="PUT",
        status_code=200,
        resource_units=len(str(payload.draft or {})),
        meta={"keys_count": len(payload.draft or {}), "server_code": user.server_code},
    )
    return ComplaintDraftResponse(
        draft=draft.get("draft", {}),
        updated_at=str(draft.get("updated_at", "") or ""),
        message="Черновик жалобы сохранён.",
    )


@router.delete("/api/complaint-draft", response_model=ComplaintDraftResponse)
async def clear_complaint_draft(
    user: AuthUser = Depends(require_user),
    store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
) -> ComplaintDraftResponse:
    store.clear_complaint_draft(user.username)
    metrics_store.log_event(
        event_type="complaint_draft_cleared",
        username=user.username,
        path="/api/complaint-draft",
        method="DELETE",
        status_code=200,
        meta={"server_code": user.server_code},
    )
    return ComplaintDraftResponse(draft={}, updated_at="", message="Черновик жалобы очищен.")


@router.post("/api/generate", response_model=GenerateResponse)
async def generate(
    payload: ComplaintPayload,
    user: AuthUser = Depends(require_user),
    store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
) -> GenerateResponse:
    _validate_server_payload(store, user, org=payload.org)
    bbcode = generate_bbcode_text(store, payload, user)
    metrics_store.log_event(
        event_type="complaint_generated",
        username=user.username,
        path="/api/generate",
        method="POST",
        status_code=200,
        resource_units=len(bbcode),
        meta={
            "server_code": user.server_code,
            "event_dt": payload.event_dt,
            "org": payload.org,
            "subject_names": payload.subject_names,
            "result_chars": len(bbcode),
            "description_chars": len(payload.situation_description or ""),
        },
    )
    return GenerateResponse(bbcode=bbcode)


@router.post("/api/generate-rehab", response_model=GenerateResponse)
async def generate_rehab(
    payload: RehabPayload,
    user: AuthUser = Depends(require_user),
    store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
) -> GenerateResponse:
    bbcode = generate_rehab_bbcode_text(store, payload, user)
    metrics_store.log_event(
        event_type="rehab_generated",
        username=user.username,
        path="/api/generate-rehab",
        method="POST",
        status_code=200,
        resource_units=len(bbcode),
        meta={
            "server_code": user.server_code,
            "principal_name": payload.principal_name,
            "served_seven_days": payload.served_seven_days,
            "result_chars": len(bbcode),
        },
    )
    return GenerateResponse(bbcode=bbcode)


@router.post("/api/ai/suggest", response_model=SuggestResponse)
async def suggest(
    payload: SuggestPayload,
    user: AuthUser = Depends(require_user),
    store: UserStore = Depends(get_user_store),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
) -> SuggestResponse:
    _validate_server_payload(store, user, org=payload.org, complaint_basis=payload.complaint_basis)
    text = suggest_text(payload)
    metrics_store.log_event(
        event_type="ai_suggest",
        username=user.username,
        path="/api/ai/suggest",
        method="POST",
        status_code=200,
        resource_units=len(payload.raw_desc or "") + len(text),
        meta={
            "server_code": user.server_code,
            "complaint_basis": payload.complaint_basis,
            "main_focus": payload.main_focus,
            "input_chars": len(payload.raw_desc or ""),
            "output_chars": len(text),
        },
    )
    return SuggestResponse(text=text)


@router.post("/api/ai/extract-principal", response_model=PrincipalScanResult)
async def extract_principal(
    payload: PrincipalScanPayload,
    user: AuthUser = Depends(require_user),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
) -> PrincipalScanResult:
    result = extract_principal_scan(payload)
    metrics_store.log_event(
        event_type="ai_extract_principal",
        username=user.username,
        path="/api/ai/extract-principal",
        method="POST",
        status_code=200,
        resource_units=len(payload.image_data_url or ""),
        meta={
            "server_code": user.server_code,
            "image_data_chars": len(payload.image_data_url or ""),
            "confidence": result.confidence,
            "missing_fields_count": len(result.missing_fields),
        },
    )
    return result


@router.post("/api/ai/law-qa-test", response_model=LawQaResponse)
async def law_qa_test(
    payload: LawQaPayload,
    user: AuthUser = Depends(require_user),
    metrics_store: AdminMetricsStore = Depends(get_admin_metrics_store),
) -> LawQaResponse:
    text, used_sources, indexed_documents = answer_law_question(payload)
    metrics_store.log_event(
        event_type="ai_law_qa_test",
        username=user.username,
        path="/api/ai/law-qa-test",
        method="POST",
        status_code=200,
        resource_units=len(payload.question or "") + len(text),
        meta={
            "server_code": user.server_code,
            "laws_root_url": payload.laws_root_url,
            "indexed_documents": indexed_documents,
            "used_sources_count": len(used_sources),
            "max_answer_chars": payload.max_answer_chars,
        },
    )
    return LawQaResponse(text=text, used_sources=used_sources, indexed_documents=indexed_documents)

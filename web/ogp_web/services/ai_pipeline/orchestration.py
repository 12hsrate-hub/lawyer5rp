from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from fastapi import HTTPException, status

from ogp_web.schemas import LawQaPayload, PrincipalScanPayload, PrincipalScanResult, SuggestPayload


@dataclass(frozen=True)
class LawQaOrchestrationDeps:
    impl: Callable[[LawQaPayload], object]


@dataclass(frozen=True)
class SuggestOrchestrationDeps:
    impl: Callable[[SuggestPayload, str], object]


@dataclass(frozen=True)
class PrincipalScanDeps:
    impl: Callable[[str], dict[str, object]]
    ai_exception_details: Callable[[Exception], list[str]]


def run_law_qa(payload: LawQaPayload, deps: LawQaOrchestrationDeps):
    return deps.impl(payload)


def run_suggest(payload: SuggestPayload, *, server_code: str, deps: SuggestOrchestrationDeps):
    return deps.impl(payload, server_code)


def run_principal_scan(payload: PrincipalScanPayload, deps: PrincipalScanDeps) -> PrincipalScanResult:
    image_data_url = payload.image_data_url.strip()
    if not image_data_url.startswith("data:image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=["Загрузите изображение в формате PNG, JPG, WEBP или GIF."])
    try:
        data = deps.impl(image_data_url)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=deps.ai_exception_details(exc)) from exc
    try:
        result = PrincipalScanResult.model_validate(data)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=[f"Модель вернула ответ в неожиданном формате: {exc}"]) from exc
    if not result.principal_address.strip():
        result.principal_address = "-"
    return result

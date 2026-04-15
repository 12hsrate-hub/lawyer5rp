from __future__ import annotations

import hashlib
import inspect
from datetime import datetime

from fastapi import HTTPException, status

from ogp_web.schemas import ComplaintPayload, RehabPayload
from ogp_web.services.auth_service import AuthUser
from ogp_web.services.profile_service import get_profile_payload
from ogp_web.storage.user_store import UserStore
from shared.ogp_core import (
    ComplaintInput,
    DEFAULT_SITUATION_PLACEHOLDER,
    DEFAULT_VIOLATION_PLACEHOLDER,
    RehabInput,
    Representative,
    Victim,
    build_bbcode,
    build_rehab_bbcode,
    collect_evidence_items,
    validate_complaint_input,
    validate_rehab_input,
)
from ogp_web.server_config import effective_server_pack, get_server_config
from ogp_web.services.law_bundle_service import load_law_bundle_meta


_TEMPLATE_VERSION_IDS = {
    "complaint": "complaint_bbcode_v1",
    "rehab": "rehab_bbcode_v1",
}


def to_domain_model(store: UserStore, payload: ComplaintPayload, user: AuthUser) -> ComplaintInput:
    representative = payload.representative or get_profile_payload(
        store,
        user.username,
        server_code=user.server_code,
    )
    today_date = payload.today_date.strip() or datetime.now().strftime("%d.%m.%Y")
    return ComplaintInput(
        appeal_no=payload.appeal_no.strip(),
        org=payload.org.strip(),
        subject_names=payload.subject_names.strip(),
        situation_description=(payload.situation_description or "").strip() or DEFAULT_SITUATION_PLACEHOLDER,
        violation_short=(payload.violation_short or "").strip() or DEFAULT_VIOLATION_PLACEHOLDER,
        event_dt=payload.event_dt.strip(),
        today_date=today_date,
        representative=Representative(**representative.model_dump()),
        victim=Victim(**payload.victim.model_dump()),
        evidence_items=collect_evidence_items(
            contract_url=payload.contract_url,
            bar_request_url=payload.bar_request_url,
            official_answer_url=payload.official_answer_url,
            mail_notice_url=payload.mail_notice_url,
            arrest_record_url=payload.arrest_record_url,
            personnel_file_url=payload.personnel_file_url,
            video_fix_urls=payload.video_fix_urls,
            provided_video_urls=payload.provided_video_urls,
        ),
    )


def generate_bbcode_text(store: UserStore, payload: ComplaintPayload, user: AuthUser) -> str:
    complaint = to_domain_model(store, payload, user)
    errors = validate_complaint_input(complaint)
    if errors:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=errors)
    return build_bbcode(complaint)


def generate_rehab_bbcode_text(store: UserStore, payload: RehabPayload, user: AuthUser) -> str:
    representative = get_profile_payload(
        store,
        user.username,
        server_code=user.server_code,
    )
    today_date = payload.today_date.strip() or datetime.now().strftime("%d.%m.%Y")
    rehab = RehabInput(
        representative=Representative(**representative.model_dump()),
        principal_name=payload.principal_name.strip(),
        principal_passport=payload.principal_passport.strip(),
        principal_passport_scan_url=payload.principal_passport_scan_url.strip(),
        served_seven_days=payload.served_seven_days,
        contract_url=payload.contract_url.strip(),
        today_date=today_date,
    )
    errors = validate_rehab_input(rehab)
    if errors:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=errors)
    return build_rehab_bbcode(rehab)


def _short_hash(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _template_hash(document_kind: str) -> str:
    if document_kind == "rehab":
        return _short_hash(inspect.getsource(build_rehab_bbcode))
    return _short_hash(inspect.getsource(build_bbcode))


def _validation_rules_version(document_kind: str) -> str:
    if document_kind == "rehab":
        source = inspect.getsource(validate_rehab_input)
    else:
        source = inspect.getsource(validate_complaint_input)
    return _short_hash(source)


def _generation_server_snapshot(*, server_code: str) -> dict[str, str]:
    return {
        "id": server_code,
        "code": server_code,
    }


def _content_workflow_snapshot(effective_config_snapshot: dict[str, str]) -> dict[str, object]:
    return {
        "applied_published_versions": dict(effective_config_snapshot),
        "rollback_safe": True,
    }


def _effective_generation_config_snapshot(
    *,
    server_pack_version: str,
    law_set_hash: str,
    template_version_id: str,
    validation_rules_version: str,
) -> dict[str, str]:
    return {
        "server_pack_version": str(server_pack_version or "0"),
        "law_set_version": str(law_set_hash or "unknown"),
        "template_version": str(template_version_id or "unknown"),
        "validation_version": str(validation_rules_version or "unknown"),
    }


def build_generation_context_snapshot(store: UserStore, user: AuthUser, *, document_kind: str) -> dict[str, object]:
    server_code = user.server_code or store.get_server_code(user.username)
    server_config = get_server_config(server_code)
    server_pack = effective_server_pack(server_code)
    bundle_meta = load_law_bundle_meta(server_code, server_config.law_qa_bundle_path)
    template_version = {
        "id": _TEMPLATE_VERSION_IDS.get(document_kind, "complaint_bbcode_v1"),
        "hash": _template_hash(document_kind),
    }
    law_version_set = {
        "hash": str(getattr(bundle_meta, "fingerprint", "") or "").strip(),
    }
    validation_rules_version = _validation_rules_version(document_kind)
    effective_config_snapshot = _effective_generation_config_snapshot(
        server_pack_version=str(server_pack.get("version") or "0"),
        law_set_hash=str(law_version_set["hash"] or "unknown"),
        template_version_id=str(template_version["id"] or "unknown"),
        validation_rules_version=str(validation_rules_version or "unknown"),
    )
    return {
        "server": _generation_server_snapshot(server_code=server_config.code),
        "template_version": template_version,
        "law_version_set": law_version_set,
        "validation_rules_version": validation_rules_version,
        "effective_config_snapshot": effective_config_snapshot,
        "content_workflow": _content_workflow_snapshot(effective_config_snapshot),
        "feature_flags": sorted(server_config.feature_flags),
    }

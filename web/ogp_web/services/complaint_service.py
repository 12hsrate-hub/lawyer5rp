from __future__ import annotations

import hashlib
import inspect
from datetime import datetime

from fastapi import HTTPException, status

from ogp_web.schemas import ComplaintPayload, RehabPayload
from ogp_web.server_config.types import ComplaintTemplateProfile
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
    build_evidence_line,
    build_rehab_bbcode,
    collect_evidence_items,
    escape_bbcode_text,
    format_phone_for_bbcode,
    normalize_discord_to_email,
    sanitize_url,
    validate_complaint_input,
    validate_rehab_input,
)
from ogp_web.server_config import get_server_config
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
    errors = validate_complaint_with_profile(store, complaint, user)
    if errors:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=errors)
    return render_complaint_with_server_template(store, complaint, user)


def validate_complaint_with_profile(store: UserStore, complaint: ComplaintInput, user: AuthUser) -> list[str]:
    errors = list(validate_complaint_input(complaint))
    profile = _get_template_profile(store, user)
    if profile is None:
        return errors
    errors.extend(_validate_profile_required_requisites(profile, complaint))
    errors.extend(_validate_profile_required_evidence(profile, complaint))
    return errors


def render_complaint_preview(store: UserStore, payload: ComplaintPayload, user: AuthUser) -> str:
    complaint = to_domain_model(store, payload, user)
    errors = validate_complaint_with_profile(store, complaint, user)
    if errors:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=errors)
    return render_complaint_with_server_template(store, complaint, user)


def render_complaint_with_server_template(store: UserStore, complaint: ComplaintInput, user: AuthUser) -> str:
    profile = _get_template_profile(store, user)
    if profile is None or not profile.bundle_template.strip():
        return build_bbcode(complaint)
    template_data = _build_template_data(complaint, profile)
    return str(profile.bundle_template).format_map(template_data)


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
    return "complaint_template_bundle_v1"


def _validation_rules_version(document_kind: str) -> str:
    if document_kind == "rehab":
        source = inspect.getsource(validate_rehab_input)
    else:
        source = inspect.getsource(validate_complaint_input)
    return _short_hash(source)


def build_generation_context_snapshot(store: UserStore, user: AuthUser, *, document_kind: str) -> dict[str, object]:
    server_code = user.server_code or store.get_server_code(user.username)
    server_config = get_server_config(server_code)
    bundle_meta = load_law_bundle_meta(server_code, server_config.law_qa_bundle_path)
    return {
        "server": {
            "id": server_config.code,
            "code": server_config.code,
        },
        "template_version": {
            "id": _TEMPLATE_VERSION_IDS.get(document_kind, "complaint_bbcode_v1"),
            "hash": _template_hash(document_kind),
        },
        "law_version_set": {
            "hash": str(getattr(bundle_meta, "fingerprint", "") or "").strip(),
        },
        "validation_rules_version": _validation_rules_version(document_kind),
        "feature_flags": sorted(server_config.feature_flags),
    }


def _get_template_profile(store: UserStore, user: AuthUser) -> ComplaintTemplateProfile | None:
    server_code = user.server_code or store.get_server_code(user.username)
    server_config = get_server_config(server_code)
    return server_config.complaint_template_profile


def _get_nested_value(data: ComplaintInput, path: str) -> str:
    current = data
    for segment in str(path or "").split("."):
        if not segment:
            continue
        current = getattr(current, segment, "")
    return str(current or "").strip()


def _validate_profile_required_requisites(profile: ComplaintTemplateProfile, complaint: ComplaintInput) -> list[str]:
    missing: list[str] = []
    for path, label in profile.required_requisites:
        if not _get_nested_value(complaint, path):
            missing.append(f"Обязательный реквизит не заполнен: {label}.")
    return missing


def _validate_profile_required_evidence(profile: ComplaintTemplateProfile, complaint: ComplaintInput) -> list[str]:
    titles = {title for title, _ in complaint.evidence_items if str(title).strip()}
    missing: list[str] = []
    for required_title in profile.required_evidence_titles:
        if required_title not in titles:
            missing.append(f"Обязательное доказательство отсутствует: {required_title}.")
    return missing


def _build_template_data(complaint: ComplaintInput, profile: ComplaintTemplateProfile) -> dict[str, str]:
    legal_insertions = [item.strip() for item in profile.legal_insertions if str(item).strip()]
    return {
        "addressee": escape_bbcode_text(profile.addressee),
        "legal_insertions_block": "\n".join(f"[*]{escape_bbcode_text(item)}" for item in legal_insertions) or "[*]-",
        "org_name": escape_bbcode_text(profile.authority_name_format.format(org=complaint.org.strip())),
        "appeal_no": escape_bbcode_text(complaint.appeal_no),
        "subject_names": escape_bbcode_text(complaint.subject_names),
        "situation_description": escape_bbcode_text(complaint.situation_description),
        "violation_short": escape_bbcode_text(complaint.violation_short),
        "event_dt": escape_bbcode_text(complaint.event_dt),
        "today_date": escape_bbcode_text(complaint.today_date),
        "evidence_line": build_evidence_line(complaint.evidence_items),
        "representative_name": escape_bbcode_text(complaint.representative.name),
        "representative_passport": escape_bbcode_text(complaint.representative.passport),
        "representative_address": escape_bbcode_text(complaint.representative.address),
        "representative_phone": escape_bbcode_text(format_phone_for_bbcode(complaint.representative.phone)),
        "representative_email": escape_bbcode_text(normalize_discord_to_email(complaint.representative.discord)),
        "representative_scan_url": sanitize_url(complaint.representative.passport_scan_url),
        "victim_name": escape_bbcode_text(complaint.victim.name),
        "victim_passport": escape_bbcode_text(complaint.victim.passport),
        "victim_address": escape_bbcode_text(complaint.victim.address),
        "victim_phone": escape_bbcode_text(format_phone_for_bbcode(complaint.victim.phone)),
        "victim_email": escape_bbcode_text(normalize_discord_to_email(complaint.victim.discord)),
        "victim_scan_url": sanitize_url(complaint.victim.passport_scan_url),
    }

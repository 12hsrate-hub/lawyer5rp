from __future__ import annotations

from dataclasses import fields
from typing import Any, List

from pydantic import BaseModel, Field, create_model, field_validator

from shared.ogp_core import DEFAULT_SITUATION_PLACEHOLDER, DEFAULT_VIOLATION_PLACEHOLDER
from shared.ogp_models import Representative, Victim


def _normalize_passport(value: str) -> str:
    raw = str(value or "").strip()
    if len(raw) > 32:
        raise ValueError("Паспорт не должен содержать более 32 символов.")
    return raw


def _normalize_phone(value: str) -> str:
    raw = str(value or "").strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    if raw and (len(digits) < 7 or len(digits) > 15):
        raise ValueError("Телефон должен содержать от 7 до 15 цифр.")
    return digits


def _build_payload_base(model_cls: type[Representative] | type[Victim], model_name: str) -> type[BaseModel]:
    payload_fields = {
        field.name: (str, field.default)
        for field in fields(model_cls)
    }
    return create_model(model_name, __base__=BaseModel, **payload_fields)


RepresentativePayloadBase = _build_payload_base(Representative, "RepresentativePayloadBase")
VictimPayloadBase = _build_payload_base(Victim, "VictimPayloadBase")


class RepresentativePayload(RepresentativePayloadBase):
    @field_validator("passport")
    @classmethod
    def validate_passport(cls, value: str) -> str:
        return _normalize_passport(value)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        return _normalize_phone(value)


class VictimPayload(VictimPayloadBase):
    @field_validator("passport")
    @classmethod
    def validate_passport(cls, value: str) -> str:
        return _normalize_passport(value)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        return _normalize_phone(value)


class ComplaintPayload(BaseModel):
    appeal_no: str = ""
    org: str = ""
    subject_names: str = ""
    situation_description: str = DEFAULT_SITUATION_PLACEHOLDER
    violation_short: str = DEFAULT_VIOLATION_PLACEHOLDER
    event_dt: str = ""
    today_date: str = ""
    representative: RepresentativePayload | None = None
    victim: VictimPayload
    contract_url: str = ""
    bar_request_url: str = ""
    official_answer_url: str = ""
    mail_notice_url: str = ""
    arrest_record_url: str = ""
    personnel_file_url: str = ""
    video_fix_urls: List[str] = Field(default_factory=list)
    provided_video_urls: List[str] = Field(default_factory=list)


class GenerateResponse(BaseModel):
    bbcode: str
    generated_document_id: int | None = None


class ComplaintDraftPayload(BaseModel):
    draft: dict = Field(default_factory=dict)
    document_type: str = "complaint"
    bundle_version: str = ""
    schema_hash: str = ""
    status: str = "draft"
    allowed_actions: List[str] = Field(default_factory=list)


class ComplaintDraftResponse(BaseModel):
    draft: dict = Field(default_factory=dict)
    updated_at: str = ""
    bundle_version: str = ""
    schema_hash: str = ""
    status: str = "draft"
    allowed_actions: List[str] = Field(default_factory=list)
    document_type: str = "complaint"
    server_id: str = ""
    message: str = ""


class GeneratedDocumentHistoryItem(BaseModel):
    id: int
    server_code: str = ""
    document_kind: str = ""
    created_at: str = ""


class GeneratedDocumentHistoryResponse(BaseModel):
    items: List[GeneratedDocumentHistoryItem] = Field(default_factory=list)


class GeneratedDocumentSnapshotResponse(BaseModel):
    id: int
    server_code: str = ""
    document_kind: str = ""
    created_at: str = ""
    context_snapshot: dict[str, Any] = Field(default_factory=dict)


class RehabPayload(BaseModel):
    principal_name: str = ""
    principal_passport: str = ""
    principal_passport_scan_url: str = ""
    served_seven_days: bool = False
    contract_url: str = ""
    today_date: str = ""

    @field_validator("principal_passport")
    @classmethod
    def validate_principal_passport(cls, value: str) -> str:
        return _normalize_passport(value)


class SuggestPayload(BaseModel):
    victim_name: str = ""
    org: str = ""
    subject: str = ""
    event_dt: str = ""
    raw_desc: str = ""
    complaint_basis: str = ""
    main_focus: str = ""
    law_version_id: int | None = None
    template_version_id: int | None = None

    @field_validator("complaint_basis")
    @classmethod
    def validate_complaint_basis(cls, value: str) -> str:
        return str(value or "").strip()


class SuggestResponse(BaseModel):
    text: str
    generation_id: str = ""
    guard_status: str = ""
    contract_version: str = ""
    warnings: List[str] = Field(default_factory=list)


class LawQaPayload(BaseModel):
    server_code: str = ""
    model: str = ""
    question: str = ""
    max_answer_chars: int = 2200
    law_version_id: int | None = None

    @field_validator("server_code")
    @classmethod
    def validate_server_code(cls, value: str) -> str:
        return str(value or "").strip().lower()

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        return str(value or "").strip()

    @field_validator("max_answer_chars")
    @classmethod
    def validate_max_answer_chars(cls, value: int) -> int:
        normalized = int(value or 0)
        if normalized < 600:
            return 600
        if normalized > 5000:
            return 5000
        return normalized


class CitationRecord(BaseModel):
    id: int
    retrieval_run_id: int
    citation_type: str = ""
    source_type: str = ""
    source_id: int
    source_version_id: int
    canonical_ref: str = ""
    quoted_text: str = ""
    usage_type: str = ""
    created_at: str = ""


class DocumentVersionCitationsResponse(BaseModel):
    items: List[CitationRecord] = Field(default_factory=list)


class LawQaRunCitationsResponse(BaseModel):
    items: List[CitationRecord] = Field(default_factory=list)


class LawQaResponse(BaseModel):
    text: str
    generation_id: str = ""
    used_sources: List[str] = Field(default_factory=list)
    indexed_documents: int = 0
    retrieval_confidence: str = ""
    retrieval_profile: str = ""
    guard_status: str = ""
    contract_version: str = ""
    bundle_status: str = ""
    bundle_generated_at: str = ""
    bundle_fingerprint: str = ""
    law_version_id: int | None = None
    warnings: List[str] = Field(default_factory=list)
    shadow: dict[str, Any] = Field(default_factory=dict)
    selected_norms: List[dict[str, Any]] = Field(default_factory=list)
    retrieval_run_id: int | None = None
    law_qa_run_id: int | None = None
    citations: List[CitationRecord] = Field(default_factory=list)


class AiFeedbackPayload(BaseModel):
    generation_id: str = ""
    flow: str = ""
    issues: List[str] = Field(default_factory=list)
    note: str = ""
    expected_reference: str = ""
    helpful: bool | None = None

    @field_validator("generation_id")
    @classmethod
    def validate_generation_id(cls, value: str) -> str:
        return str(value or "").strip()

    @field_validator("flow")
    @classmethod
    def validate_flow(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        return normalized


class AiFeedbackResponse(BaseModel):
    feedback_id: str
    generation_id: str
    flow: str
    normalized_issues: List[str] = Field(default_factory=list)
    message: str = ""


class PrincipalScanPayload(BaseModel):
    image_data_url: str = ""


class PrincipalScanResult(BaseModel):
    principal_name: str = ""
    principal_passport: str = ""
    principal_phone: str = ""
    principal_address: str = ""
    principal_discord: str = ""
    source_summary: str = ""
    confidence: str = ""
    missing_fields: List[str] = Field(default_factory=list)

    @field_validator("principal_passport")
    @classmethod
    def validate_principal_passport(cls, value: str) -> str:
        return _normalize_passport(value)

    @field_validator("principal_phone")
    @classmethod
    def validate_principal_phone(cls, value: str) -> str:
        return _normalize_phone(value)


class DocumentBuilderBundleResponse(BaseModel):
    bundle_version: str = ""
    server: str = ""
    document_type: str = ""
    sections: List[dict[str, Any]] = Field(default_factory=list)
    fields: dict[str, dict[str, Any]] = Field(default_factory=dict)
    choice_sets: dict[str, Any] = Field(default_factory=dict)
    validators: dict[str, Any] = Field(default_factory=dict)
    template: dict[str, Any] = Field(default_factory=dict)
    ai_profile: dict[str, Any] = Field(default_factory=dict)
    features: dict[str, Any] = Field(default_factory=dict)
    status: dict[str, Any] = Field(default_factory=dict)
    allowed_actions: List[str] = Field(default_factory=list)


class AuthPayload(BaseModel):
    username: str = ""
    email: str = ""
    password: str = ""


class AuthResponse(BaseModel):
    username: str
    message: str
    server_code: str = ""
    requires_email_verification: bool = False
    verification_url: str | None = None


class EmailPayload(BaseModel):
    email: str = ""


class PasswordResetPayload(BaseModel):
    token: str = ""
    password: str = ""


class PasswordChangePayload(BaseModel):
    current_password: str = ""
    new_password: str = ""


class AdminBlockPayload(BaseModel):
    reason: str = ""


class AdminEmailUpdatePayload(BaseModel):
    email: str = ""


class AdminPasswordResetPayload(BaseModel):
    password: str = ""


class AdminDeactivatePayload(BaseModel):
    reason: str = ""


class AdminQuotaPayload(BaseModel):
    daily_limit: int = Field(default=0, ge=0, le=1_000_000)


class AdminBulkActionPayload(BaseModel):
    usernames: List[str] = Field(default_factory=list)
    action: str = ""
    reason: str = ""
    daily_limit: int | None = Field(default=None, ge=0, le=1_000_000)
    run_async: bool = True


class AdminExamScoreResetPayload(BaseModel):
    full_name: str = ""
    discord_tag: str = ""
    passport: str = ""

    @field_validator("full_name", "discord_tag", "passport")
    @classmethod
    def validate_trimmed(cls, value: str) -> str:
        return str(value or "").strip()


class ProfileResponse(BaseModel):
    representative: RepresentativePayload
    server_code: str = ""
    message: str = ""


class SelectedServerPayload(BaseModel):
    server_code: str = ""

    @field_validator("server_code")
    @classmethod
    def validate_server_code(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if not normalized:
            raise ValueError("Укажите код сервера.")
        return normalized


class DraftSwitchAction(BaseModel):
    semantic_key: str = ""
    action: str = ""
    detail: str = ""


class SelectedServerResponse(BaseModel):
    server_code: str = ""
    message: str = ""
    switch_actions: List[DraftSwitchAction] = Field(default_factory=list)


class ExamImportEntry(BaseModel):
    source_row: int
    submitted_at: str = ""
    full_name: str = ""
    discord_tag: str = ""
    passport: str = ""
    exam_format: str = ""
    answer_count: int = 0
    average_score: float | None = None
    average_score_answer_count: int = 0
    imported_at: str = ""


class ExamAnswerScore(BaseModel):
    column: str
    header: str
    user_answer: str = ""
    correct_answer: str = ""
    score: int | None = None
    rationale: str = ""


class ExamImportDetail(ExamImportEntry):
    updated_at: str = ""
    average_score_scored_at: str = ""
    payload: dict[str, str] = Field(default_factory=dict)
    question_g_header: str = ""
    question_g_answer: str = ""
    question_g_score: int | None = None
    question_g_rationale: str = ""
    exam_scores: List[ExamAnswerScore] = Field(default_factory=list)


class ExamImportResponse(BaseModel):
    sheet_url: str
    total_rows: int = 0
    imported_count: int = 0
    inserted_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    scored_count: int = 0
    latest_entries: List[ExamImportEntry] = Field(default_factory=list)


class ExamImportTaskStatus(BaseModel):
    task_id: str
    task_type: str
    source_row: int | None = None
    status: str
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    error: str = ""
    progress: dict[str, Any] | None = None
    result: dict[str, Any] | None = None


class AdminCatalogItemPayload(BaseModel):
    title: str = ""
    key: str = ""
    description: str = ""
    status: str = "draft"
    server_code: str = ""
    base_url: str = ""
    timeout_sec: int | None = None
    law_code: str = ""
    source: str = ""
    effective_from: str = ""
    template_type: str = ""
    document_kind: str = ""
    output_format: str = ""
    feature_flag: str = ""
    rollout_percent: int | None = None
    audience: str = ""
    rule_type: str = ""
    priority: int | None = None
    applies_to: str = ""
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title", "description")
    @classmethod
    def validate_trimmed_text(cls, value: str) -> str:
        return str(value or "").strip()

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        normalized = str(value or "").strip().lower().replace(" ", "_")
        if normalized and not all(ch.isalnum() or ch in {"_", "-", "."} for ch in normalized):
            raise ValueError("key_must_contain_only_alnum_dash_underscore_dot")
        return normalized

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        normalized = str(value or "draft").strip().lower() or "draft"
        allowed = {"draft", "review", "published", "active", "disabled", "archived"}
        if normalized not in allowed:
            raise ValueError("unsupported_status")
        return normalized

    @field_validator("rollout_percent")
    @classmethod
    def validate_rollout_percent(cls, value: int | None) -> int | None:
        if value is None:
            return None
        normalized = int(value)
        if normalized < 0 or normalized > 100:
            raise ValueError("rollout_percent_must_be_between_0_and_100")
        return normalized

    @field_validator("timeout_sec", "priority")
    @classmethod
    def validate_non_negative_int(cls, value: int | None) -> int | None:
        if value is None:
            return None
        normalized = int(value)
        if normalized < 0:
            raise ValueError("value_must_be_non_negative")
        return normalized

    @field_validator("config")
    @classmethod
    def validate_config(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("config_must_be_object")
        return value


class AdminRuntimeServerPayload(BaseModel):
    code: str = ""
    title: str = ""

    @field_validator("code")
    @classmethod
    def validate_server_code(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if not normalized:
            raise ValueError("server_code_required")
        if not all(ch.isalnum() or ch in {"_", "-", "."} for ch in normalized):
            raise ValueError("server_code_invalid")
        return normalized

    @field_validator("title")
    @classmethod
    def validate_server_title(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("server_title_required")
        return normalized

class AdminCatalogWorkflowPayload(BaseModel):
    action: str = ""
    change_request_id: int = 0


class AdminCatalogRollbackPayload(BaseModel):
    version: int = 0


class AdminLawSourcesPayload(BaseModel):
    server_code: str = ""
    source_urls: list[str] = Field(default_factory=list)
    persist_sources: bool = True

    @field_validator("server_code")
    @classmethod
    def validate_server_code(cls, value: str) -> str:
        return str(value or "").strip().lower()


class AdminLawSourceRegistryPayload(BaseModel):
    name: str = ""
    kind: str = "url"
    url: str = ""
    is_active: bool = True

    @field_validator("name", "url")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("value_required")
        return normalized

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, value: str) -> str:
        normalized = str(value or "").strip().lower() or "url"
        if normalized not in {"url", "registry", "api"}:
            raise ValueError("law_source_kind_invalid")
        return normalized


class AdminLawSetItemPayload(BaseModel):
    law_code: str = ""
    effective_from: str = ""
    priority: int = 100
    source_id: int | None = None

    @field_validator("law_code")
    @classmethod
    def validate_law_code(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("law_code_required")
        return normalized


class AdminLawSetPayload(BaseModel):
    name: str = ""
    is_active: bool = True
    items: list[AdminLawSetItemPayload] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("law_set_name_required")
        return normalized


class AdminLawSetRebuildPayload(BaseModel):
    dry_run: bool = False


class AdminLawSetRollbackPayload(BaseModel):
    law_version_id: int | None = None


class AdminServerLawBindingPayload(BaseModel):
    law_code: str = ""
    source_id: int
    effective_from: str = ""
    priority: int = 100
    law_set_id: int | None = None

    @field_validator("law_code")
    @classmethod
    def validate_law_code(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("law_code_required")
        return normalized

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Iterable, Sequence

import yaml


MODE_LEGAL_GROUNDED = "legal_grounded"
MODE_FACTUAL_FALLBACK_EXPANDED = "factual_fallback_expanded"

_ROOT_DIR = Path(__file__).resolve().parents[3]
_CONFIG_DIR = _ROOT_DIR / "config"

_DATE_PATTERN = re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{2,4}(?:\s+\d{1,2}:\d{2})?\b")
_NUMBER_PATTERN = re.compile(r"\b\d{1,4}(?:\.\d+)?\b")
_ARTICLE_REF_PATTERN = re.compile(
    r"\b(?:ст\.?|стат(?:ья|ье|ьи|ью))\s*\d+(?:\.\d+)?(?:\s*(?:ч\.?|част[ьи])\s*\d+)?(?:\s*(?:п\.?|пункт)\s*[\"«]?[a-zа-яё0-9-]+[\"»]?)?",
    flags=re.IGNORECASE,
)
_MULTIWORD_ENTITY_PATTERN = re.compile(r"\b[А-ЯЁA-Z][а-яёa-z]+(?:\s+[А-ЯЁA-Z][а-яёa-z]+)+\b")
_ALLCAPS_ENTITY_PATTERN = re.compile(r"\b[А-ЯЁA-Z]{3,}(?:\s+[А-ЯЁA-Z]{2,})*\b")
_STOPWORDS = {
    "и",
    "в",
    "во",
    "на",
    "по",
    "к",
    "из",
    "от",
    "для",
    "при",
    "что",
    "это",
    "как",
    "или",
    "the",
    "and",
    "for",
    "with",
}

_INPUT_STATEMENT_MARKERS = (
    "по словам",
    "со слов",
    "как утверждает",
    "как указал",
    "заявил",
    "заявила",
    "заявили",
    "утверждает",
    "утверждают",
)
_INPUT_ASSUMPTION_MARKERS = (
    "возможно",
    "предположительно",
    "вероятно",
    "скорее всего",
    "может быть",
    "полагаю",
    "думаю",
    "мне кажется",
)
_INPUT_ACTION_TERMS = (
    "задерж",
    "арест",
    "достав",
    "обыск",
    "досмотр",
    "процессуальн",
    "запрос",
    "допрос",
    "штраф",
    "тикет",
    "наручник",
)
_INPUT_EVIDENCE_TERMS = (
    "договор",
    "запрос",
    "ответ",
    "видео",
    "видеозап",
    "запись",
    "материал",
    "доказатель",
    "ссылка",
    "скрин",
    "рапорт",
    "протокол",
)
_MASK_TRIGGER_TERMS = ("маск", "маскиров", "визор", "капюшон")
_ENTERTAINMENT_LOCATION_TERMS = (
    "maze bank arena",
    "арена",
    "развлекатель",
    "увеселит",
    "казино",
    "клуб",
    "бар",
)
_VIDEO_TERMS = ("видео", "видеозап", "видеофиксац", "запись", "bodycam", "бодикам")
_VIDEO_ABSENCE_MARKERS = ("отсутств", "не предостав", "не поступ", "нет", "не было")
_VIDEO_PRESENCE_MARKERS = ("предостав", "прилож", "имеется", "есть", "ссылка", "bodycam", "бодикам")
_GENERIC_ACTOR_MARKERS = ("человек", "лицо", "гражданин", "он", "она", "они")
_STATE_SERVICE_TERMS = (
    "государственной службы",
    "государственный служащий",
    "госслужащ",
    "госслужб",
    "прокурор",
    "офиса генерального прокурора",
    "начальств",
    "руководств",
    "бейдж",
    "удостоверен",
)
_SEARCH_ACTION_TERMS = ("обыск", "досмотр", "личный обыск", "изъят", "изъятие", "изъяли")
_PERSONAL_CONFLICT_TERMS = ("личный конфликт", "личная неприязнь", "конфликт", "неприязн")
_CODE_OR_LAW_MARKERS = ("кодекс", "закон")
_PROTECTED_TERM_GROUPS: dict[str, tuple[str, ...]] = {
    "detention": ("задержан", "задержание", "задержали"),
    "arrest": ("арест", "арестован", "арестовали"),
    "delivery": ("доставлен", "доставление", "доставили"),
    "search": ("обыск", "обыскали"),
    "inspection": ("досмотр", "досматрив"),
    "advocate_request": ("адвокатский запрос",),
    "video_recording": ("видеозапись", "видеофиксация", "видео", "запись"),
    "procedural_actions": ("процессуальные действия", "процессуального порядка"),
}


@dataclass(frozen=True)
class NormQualifier:
    kind: str
    text: str
    related_refs: tuple[str, ...] = ()

    def as_contract(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "text": self.text,
            "related_refs": list(self.related_refs),
        }


@dataclass(frozen=True)
class SelectedNorm:
    source_url: str
    document_title: str
    article_label: str
    excerpt: str
    score: int = 0
    qualifiers: tuple[NormQualifier, ...] = ()
    cross_refs: tuple[str, ...] = ()

    def as_contract(self) -> dict[str, object]:
        return {
            "source_url": self.source_url,
            "document_title": self.document_title,
            "article_label": self.article_label,
            "excerpt": self.excerpt,
            "score": self.score,
            "qualifiers": [item.as_contract() for item in self.qualifiers],
            "cross_refs": list(self.cross_refs),
        }

    @property
    def search_text(self) -> str:
        return " ".join(
            part
            for part in (
                self.document_title,
                self.article_label,
                self.excerpt,
                *(item.text for item in self.qualifiers),
                *self.cross_refs,
            )
            if part
        )


@dataclass(frozen=True)
class NormalizedSuggestInput:
    part_id: str
    complainant: str
    organization: str
    target_person: str
    event_datetime: str
    draft_text: str
    retrieval_status: str
    applicability_notes: str
    retrieved_law_context: str
    retrieval_confidence: str = "low"
    selected_norms: tuple[SelectedNorm, ...] = ()

    def as_contract(self) -> dict[str, object]:
        return {
            "part_id": self.part_id,
            "complainant": self.complainant,
            "organization": self.organization,
            "target_person": self.target_person,
            "event_datetime": self.event_datetime,
            "draft_text": self.draft_text,
            "retrieval_status": self.retrieval_status,
            "applicability_notes": self.applicability_notes,
            "retrieved_law_context": self.retrieved_law_context,
        }


@dataclass(frozen=True)
class ExtractedFact:
    id: str
    text: str
    source: str
    confidence: float
    risk: str
    allow_in_final: bool

    def as_contract(self) -> dict[str, object]:
        return {
            "id": self.id,
            "text": self.text,
            "source": self.source,
            "confidence": round(self.confidence, 2),
            "risk": self.risk,
            "allow_in_final": self.allow_in_final,
        }


@dataclass(frozen=True)
class NormTrigger:
    fact_id: str
    norm_ref: str
    matched_in_input: bool
    matched_in_retrieval: bool
    is_valid: bool
    trigger_confidence: float = 0.0
    source_url: str = ""
    document_title: str = ""
    excerpt: str = ""
    qualifiers: tuple[NormQualifier, ...] = ()
    cross_refs: tuple[str, ...] = ()

    def as_contract(self) -> dict[str, object]:
        return {
            "fact_id": self.fact_id,
            "norm_ref": self.norm_ref,
            "matched_in_input": self.matched_in_input,
            "matched_in_retrieval": self.matched_in_retrieval,
            "is_valid": self.is_valid,
            "trigger_confidence": round(self.trigger_confidence, 2),
            "qualifier_kinds": [item.kind for item in self.qualifiers],
            "cross_refs": list(self.cross_refs),
        }


@dataclass(frozen=True)
class PolicyDecision:
    mode: str
    reason: str
    valid_triggers_count: int
    avg_confidence: float

    def as_contract(self) -> dict[str, object]:
        return {
            "policy_decision": {
                "mode": self.mode,
                "reason": self.reason,
                "valid_triggers_count": self.valid_triggers_count,
                "avg_confidence": round(self.avg_confidence, 2),
            }
        }


@dataclass(frozen=True)
class InputAuditIssue:
    code: str
    message: str

    def as_contract(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True)
class InputAuditResult:
    warnings: tuple[InputAuditIssue, ...]
    protected_terms: tuple[str, ...]

    @property
    def warning_codes(self) -> tuple[str, ...]:
        return tuple(item.code for item in self.warnings)

    def as_contract(self) -> dict[str, object]:
        return {
            "warnings": [item.as_contract() for item in self.warnings],
            "protected_terms": list(self.protected_terms),
        }


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    severity: str
    message: str
    start: int = -1
    end: int = -1
    span_text: str = ""


@dataclass(frozen=True)
class SuggestValidationResult:
    status: str
    blockers: tuple[ValidationIssue, ...]
    warnings: tuple[ValidationIssue, ...]
    infos: tuple[ValidationIssue, ...]
    sentence_count: int

    @property
    def blocker_codes(self) -> tuple[str, ...]:
        return tuple(issue.code for issue in self.blockers)

    @property
    def warning_codes(self) -> tuple[str, ...]:
        return tuple(issue.code for issue in self.warnings)

    @property
    def info_codes(self) -> tuple[str, ...]:
        return tuple(issue.code for issue in self.infos)


@dataclass(frozen=True)
class RemediationOutcome:
    text: str
    validation: SuggestValidationResult
    retries_used: int
    safe_fallback_used: bool


@dataclass(frozen=True)
class Point3PipelineContext:
    normalized_input: NormalizedSuggestInput
    input_audit: InputAuditResult
    facts: tuple[ExtractedFact, ...]
    triggers: tuple[NormTrigger, ...]
    policy_decision: PolicyDecision
    risk_level: str

    def prompt_context_json(self) -> str:
        normalized_payload = dict(self.normalized_input.as_contract())
        normalized_payload["draft_text"] = _truncate_prompt_field(normalized_payload.get("draft_text", ""), max_chars=900)
        normalized_payload["retrieved_law_context"] = _truncate_prompt_field(
            normalized_payload.get("retrieved_law_context", ""),
            max_chars=700,
        )
        payload = {
            "normalized_input": normalized_payload,
            "input_audit": self.input_audit.as_contract(),
            "facts": [item.as_contract() for item in self.facts],
            "triggers": [item.as_contract() for item in self.triggers],
            **self.policy_decision.as_contract(),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)


def build_point3_pipeline_context(
    *,
    complainant: str,
    organization: str,
    target_person: str,
    event_datetime: str,
    draft_text: str,
    complaint_basis: str = "",
    main_focus: str = "",
    retrieval_status: str = "no_context",
    retrieval_confidence: str = "low",
    retrieved_law_context: str = "",
    selected_norms: Sequence[dict[str, object]] = (),
) -> Point3PipelineContext:
    normalized_input = normalize_suggest_input(
        complainant=complainant,
        organization=organization,
        target_person=target_person,
        event_datetime=event_datetime,
        draft_text=draft_text,
        complaint_basis=complaint_basis,
        main_focus=main_focus,
        retrieval_status=retrieval_status,
        retrieval_confidence=retrieval_confidence,
        retrieved_law_context=retrieved_law_context,
        selected_norms=selected_norms,
    )
    input_audit = audit_input(normalized_input)
    facts = extract_atomic_facts(normalized_input)
    triggers = match_norm_triggers(normalized_input=normalized_input, facts=facts)
    avg_confidence, risk_level = score_policy_risk(normalized_input=normalized_input, triggers=triggers)
    decision = route_policy(
        normalized_input=normalized_input,
        triggers=triggers,
        avg_confidence=avg_confidence,
    )
    return Point3PipelineContext(
        normalized_input=normalized_input,
        input_audit=input_audit,
        facts=facts,
        triggers=triggers,
        policy_decision=decision,
        risk_level=risk_level,
    )


def normalize_suggest_input(
    *,
    complainant: str,
    organization: str,
    target_person: str,
    event_datetime: str,
    draft_text: str,
    complaint_basis: str = "",
    main_focus: str = "",
    retrieval_status: str = "no_context",
    retrieval_confidence: str = "low",
    retrieved_law_context: str = "",
    selected_norms: Sequence[dict[str, object]] = (),
) -> NormalizedSuggestInput:
    applicability_notes = "; ".join(
        value for value in (_normalize_inline(complaint_basis), _normalize_inline(main_focus)) if value
    )
    normalized_norms = tuple(
        SelectedNorm(
            source_url=_normalize_inline(item.get("source_url", "")),
            document_title=_normalize_inline(item.get("document_title", "")),
            article_label=_normalize_inline(item.get("article_label", "")),
            excerpt=_normalize_inline(item.get("excerpt", "")),
            score=int(item.get("score", 0) or 0),
            qualifiers=tuple(
                NormQualifier(
                    kind=_normalize_inline(qualifier.get("kind", "")),
                    text=_normalize_inline(qualifier.get("text", "")),
                    related_refs=tuple(
                        _normalize_inline(ref)
                        for ref in (qualifier.get("related_refs", ()) or ())
                        if _normalize_inline(ref)
                    ),
                )
                for qualifier in (item.get("qualifiers", ()) or ())
                if isinstance(qualifier, dict)
                and (
                    _normalize_inline(qualifier.get("kind", ""))
                    or _normalize_inline(qualifier.get("text", ""))
                )
            ),
            cross_refs=tuple(
                _normalize_inline(ref)
                for ref in (item.get("cross_refs", ()) or ())
                if _normalize_inline(ref)
            ),
        )
        for item in selected_norms
    )
    return NormalizedSuggestInput(
        part_id="3",
        complainant=_normalize_inline(complainant),
        organization=_normalize_inline(organization),
        target_person=_normalize_inline(target_person),
        event_datetime=_normalize_inline(event_datetime),
        draft_text=_normalize_multiline(draft_text),
        retrieval_status=_normalize_inline(retrieval_status) or "no_context",
        applicability_notes=applicability_notes,
        retrieved_law_context=_normalize_multiline(retrieved_law_context),
        retrieval_confidence=_normalize_inline(retrieval_confidence) or "low",
        selected_norms=normalized_norms,
    )


def audit_input(normalized_input: NormalizedSuggestInput) -> InputAuditResult:
    warnings: list[InputAuditIssue] = []
    draft_text = normalized_input.draft_text
    lowered_draft = draft_text.lower()
    event_dt = normalized_input.event_datetime.strip()

    if event_dt and not _DATE_PATTERN.search(event_dt):
        warnings.append(
            InputAuditIssue(
                code="input_partial_datetime",
                message="Event date/time looks incomplete or non-standard.",
            )
        )
    if not _contains_any_substring(lowered_draft, _INPUT_ACTION_TERMS):
        warnings.append(
            InputAuditIssue(
                code="input_missing_action_reference",
                message="The draft may be missing a clear reference to the underlying procedural action.",
            )
        )
    if not _contains_any_substring(lowered_draft, _INPUT_EVIDENCE_TERMS):
        warnings.append(
            InputAuditIssue(
                code="input_missing_evidence_reference",
                message="The draft may be missing an explicit evidence or document reference.",
            )
        )
    if _contains_any_substring(lowered_draft, _INPUT_STATEMENT_MARKERS):
        warnings.append(
            InputAuditIssue(
                code="input_reported_speech_detected",
                message="The draft contains reported speech markers and should preserve that uncertainty.",
            )
        )
    if _contains_any_substring(lowered_draft, _INPUT_ASSUMPTION_MARKERS):
        warnings.append(
            InputAuditIssue(
                code="input_assumption_language_detected",
                message="The draft contains assumption markers and should remain cautious.",
            )
        )
    if _has_conflicting_date_mentions(normalized_input):
        warnings.append(
            InputAuditIssue(
                code="input_conflicting_dates",
                message="The draft may contain conflicting date or time references.",
            )
        )
    if _has_video_status_conflict(lowered_draft):
        warnings.append(
            InputAuditIssue(
                code="input_conflicting_video_status",
                message="The draft may simultaneously imply both missing and available video evidence.",
            )
        )
    if _has_role_ambiguity(lowered_draft, normalized_input.target_person):
        warnings.append(
            InputAuditIssue(
                code="input_ambiguous_actor_reference",
                message="The acting person may be ambiguous in the draft.",
            )
        )
    if _has_protected_term_collision(lowered_draft, "detention", "arrest"):
        warnings.append(
            InputAuditIssue(
                code="input_term_collision_detention_arrest",
                message="The draft uses both detention and arrest terminology and may need manual review.",
            )
        )
    if _has_protected_term_collision(lowered_draft, "search", "inspection"):
        warnings.append(
            InputAuditIssue(
                code="input_term_collision_search_inspection",
                message="The draft uses both search and inspection terminology and may need manual review.",
            )
        )

    return InputAuditResult(
        warnings=tuple(_dedupe_input_issues(warnings)),
        protected_terms=tuple(_extract_protected_terms(lowered_draft)),
    )


def extract_atomic_facts(normalized_input: NormalizedSuggestInput) -> tuple[ExtractedFact, ...]:
    raw_text = normalized_input.draft_text
    if not raw_text:
        return ()

    chunks = []
    for fragment in re.split(r"(?:\n+|(?<=[.!?;])\s+)", raw_text):
        cleaned = re.sub(r"^[\-*#]+\s*", "", str(fragment or "").strip())
        cleaned = cleaned.strip(" ,;")
        if len(cleaned) < 8:
            continue
        if cleaned not in chunks:
            chunks.append(cleaned)
    if not chunks:
        chunks = [raw_text]

    facts: list[ExtractedFact] = []
    for index, chunk in enumerate(chunks, start=1):
        confidence = 0.92 if len(chunk) >= 40 else 0.82
        risk = "medium" if re.search(r"\b(?:возможно|предположительно|вероятно)\b", chunk, flags=re.IGNORECASE) else "low"
        facts.append(
            ExtractedFact(
                id=f"F{index}",
                text=chunk,
                source="draft",
                confidence=confidence,
                risk=risk,
                allow_in_final=True,
            )
        )
    return tuple(facts)


def match_norm_triggers(
    *,
    normalized_input: NormalizedSuggestInput,
    facts: Sequence[ExtractedFact],
) -> tuple[NormTrigger, ...]:
    thresholds = load_policy_thresholds()
    min_valid = float(thresholds["thresholds"]["min_valid_trigger_confidence"])
    draft_text = normalized_input.draft_text
    triggers: list[NormTrigger] = []

    if not normalized_input.selected_norms:
        if facts:
            return (
                NormTrigger(
                    fact_id=facts[0].id,
                    norm_ref="N/A",
                    matched_in_input=False,
                    matched_in_retrieval=False,
                    is_valid=False,
                ),
            )
        return ()

    for norm in normalized_input.selected_norms:
        best_fact = facts[0] if facts else ExtractedFact("F1", "", "draft", 0.0, "low", True)
        best_overlap = -1
        norm_text = norm.search_text
        norm_roots = _token_roots(norm_text)
        for fact in facts:
            overlap = len(set(_token_roots(fact.text)) & set(norm_roots))
            if overlap > best_overlap:
                best_fact = fact
                best_overlap = overlap
        matched_in_input = _norm_ref_mentioned_in_text(norm.article_label, draft_text)
        matched_in_retrieval = bool(norm.article_label or norm.document_title or norm.excerpt or norm.qualifiers or norm.cross_refs)
        direct_fact_trigger = _has_direct_fact_trigger(
            normalized_input=normalized_input,
            fact_text=best_fact.text,
            norm=norm,
            overlap=max(best_overlap, 0),
        )
        confidence = _score_trigger_confidence(
            retrieval_confidence=normalized_input.retrieval_confidence,
            norm_score=norm.score,
            overlap=max(best_overlap, 0),
            matched_in_input=matched_in_input,
            document_title=norm.document_title,
            direct_fact_trigger=direct_fact_trigger,
        )
        triggers.append(
            NormTrigger(
                fact_id=best_fact.id,
                norm_ref=norm.article_label or norm.document_title or "N/A",
                matched_in_input=matched_in_input,
                matched_in_retrieval=matched_in_retrieval,
                is_valid=bool(matched_in_retrieval and direct_fact_trigger and confidence >= min_valid),
                trigger_confidence=confidence,
                source_url=norm.source_url,
                document_title=norm.document_title,
                excerpt=norm.excerpt,
                qualifiers=norm.qualifiers,
                cross_refs=norm.cross_refs,
            )
        )
    return tuple(triggers)


def score_policy_risk(
    *,
    normalized_input: NormalizedSuggestInput,
    triggers: Sequence[NormTrigger],
) -> tuple[float, str]:
    confidence_values = [item.trigger_confidence for item in triggers if item.matched_in_retrieval]
    avg_confidence = round(sum(confidence_values) / len(confidence_values), 2) if confidence_values else 0.0
    risk_level = "low"
    if normalized_input.retrieval_status in {"low_confidence_context", "no_context"}:
        risk_level = "high" if avg_confidence < 0.7 else "medium"
    elif avg_confidence < 0.7:
        risk_level = "medium"
    return avg_confidence, risk_level


def route_policy(
    *,
    normalized_input: NormalizedSuggestInput,
    triggers: Sequence[NormTrigger],
    avg_confidence: float,
) -> PolicyDecision:
    thresholds = load_policy_thresholds()
    min_valid = float(thresholds["thresholds"]["min_valid_trigger_confidence"])
    borderline_min = float(thresholds["thresholds"]["borderline_trigger_confidence_min"])
    borderline_max = float(thresholds["thresholds"]["borderline_trigger_confidence_max"])

    valid_triggers = [item for item in triggers if item.is_valid]
    trigger_confidences = [item.trigger_confidence for item in triggers if item.matched_in_retrieval]
    borderline_low_confidence = (
        normalized_input.retrieval_status == "low_confidence_context"
        and any(borderline_min <= value < borderline_max for value in trigger_confidences)
    )
    personal_conflict_fallback = _should_force_factual_fallback_for_personal_conflict(
        normalized_input=normalized_input,
        valid_triggers=valid_triggers,
    )

    if (
        valid_triggers
        and min(item.trigger_confidence for item in valid_triggers) >= min_valid
        and not borderline_low_confidence
        and not personal_conflict_fallback
    ):
        return PolicyDecision(
            mode=MODE_LEGAL_GROUNDED,
            reason="valid_trigger_confirmed",
            valid_triggers_count=len(valid_triggers),
            avg_confidence=avg_confidence,
        )
    if personal_conflict_fallback:
        reason = "personal_conflict_requires_factual_fallback"
    elif borderline_low_confidence:
        reason = "low_confidence_context_borderline_triggers"
    else:
        reason = "no_valid_triggers_or_low_confidence"
    return PolicyDecision(
        mode=MODE_FACTUAL_FALLBACK_EXPANDED,
        reason=reason,
        valid_triggers_count=len(valid_triggers),
        avg_confidence=avg_confidence,
    )


def validate_generated_paragraph(text: str, context: Point3PipelineContext) -> SuggestValidationResult:
    normalized_text = normalize_generated_paragraph(text)
    rules = load_validator_rules()
    blockers: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    infos: list[ValidationIssue] = []

    sentence_count = count_sentences(normalized_text)
    policy_mode = context.policy_decision.mode
    valid_triggers = [item for item in context.triggers if item.is_valid]

    for match in re.finditer(r"https?://[^\s)\]]+", normalized_text, flags=re.IGNORECASE):
        blockers.append(
            ValidationIssue(
                code="new_url",
                severity="blocker",
                message="The generated paragraph must not contain URLs.",
                start=match.start(),
                end=match.end(),
                span_text=match.group(0),
            )
        )

    allowed_dates = {context.normalized_input.event_datetime} if context.normalized_input.event_datetime else set()
    for match in _DATE_PATTERN.finditer(normalized_text):
        if match.group(0) not in allowed_dates:
            blockers.append(
                ValidationIssue(
                    code="new_date",
                    severity="blocker",
                    message="The generated paragraph introduced a new date or time.",
                    start=match.start(),
                    end=match.end(),
                    span_text=match.group(0),
                )
            )

    allowed_article_refs = {
        _normalize_inline(item.norm_ref).lower()
        for item in valid_triggers
        if _normalize_inline(item.norm_ref)
    }
    allowed_article_numbers = {
        _primary_article_number(item.norm_ref)
        for item in valid_triggers
        if _primary_article_number(item.norm_ref)
    }
    for match in _ARTICLE_REF_PATTERN.finditer(normalized_text):
        ref_text = _normalize_inline(match.group(0)).lower()
        ref_number = _primary_article_number(ref_text)
        if (
            policy_mode != MODE_LEGAL_GROUNDED
            or (ref_text not in allowed_article_refs and ref_number not in allowed_article_numbers)
        ):
            blockers.append(
                ValidationIssue(
                    code="article_without_valid_trigger",
                    severity="blocker",
                    message="Article references are allowed only in legal_grounded with valid triggers.",
                    start=match.start(),
                    end=match.end(),
                    span_text=match.group(0),
                )
            )
        elif not _article_reference_has_document_title(
            normalized_text,
            match_start=match.start(),
            match_end=match.end(),
        ):
            warnings.append(
                ValidationIssue(
                    code="article_missing_document_title",
                    severity="warning",
                    message="Article references should include the code or law name in the same sentence.",
                    start=match.start(),
                    end=match.end(),
                    span_text=match.group(0),
                )
            )

    sanitized_text = _ARTICLE_REF_PATTERN.sub("", normalized_text)
    allowed_numbers = _extract_allowed_numbers(context)
    for match in _NUMBER_PATTERN.finditer(sanitized_text):
        if match.group(0) not in allowed_numbers:
            blockers.append(
                ValidationIssue(
                    code="new_number",
                    severity="blocker",
                    message="The generated paragraph introduced a new number.",
                    start=match.start(),
                    end=match.end(),
                    span_text=match.group(0),
                )
            )

    allowed_entities = _extract_allowed_entities(context)
    for candidate, start, end in _extract_entity_candidates(normalized_text):
        if candidate.lower() not in allowed_entities:
            blockers.append(
                ValidationIssue(
                    code="new_entity",
                    severity="blocker",
                    message="The generated paragraph introduced a new named entity.",
                    start=start,
                    end=end,
                    span_text=candidate,
                )
            )

    draft_lower = context.normalized_input.draft_text.lower()
    for keyword in rules.get("document_keywords", []):
        normalized_keyword = str(keyword or "").strip().lower()
        if normalized_keyword and normalized_keyword in normalized_text.lower() and normalized_keyword not in draft_lower:
            start = normalized_text.lower().find(normalized_keyword)
            blockers.append(
                ValidationIssue(
                    code="new_document",
                    severity="blocker",
                    message="The generated paragraph introduced a new document reference.",
                    start=start,
                    end=start + len(normalized_keyword),
                    span_text=normalized_text[start : start + len(normalized_keyword)],
                )
            )

    for phrase in rules.get("strong_qualification_phrases", []):
        for match in re.finditer(re.escape(str(phrase or "").strip()), normalized_text, flags=re.IGNORECASE):
            blockers.append(
                ValidationIssue(
                    code="strong_unconfirmed_qualification",
                    severity="blocker",
                    message="The generated paragraph contains an unconfirmed strong legal qualification.",
                    start=match.start(),
                    end=match.end(),
                    span_text=match.group(0),
                )
            )

    if policy_mode == MODE_FACTUAL_FALLBACK_EXPANDED:
        min_sentences = int(rules.get("warnings", {}).get("min_fallback_sentences", 4) or 4)
        if sentence_count < min_sentences:
            warnings.append(
                ValidationIssue(
                    code="fallback_too_short",
                    severity="warning",
                    message="Fallback mode requires at least four sentences.",
                )
            )
        if not _contains_assessment_phrase(normalized_text, rules.get("employee_assessment_phrases", [])):
            warnings.append(
                ValidationIssue(
                    code="missing_employee_assessment",
                    severity="warning",
                    message="Fallback mode requires a restrained procedural assessment of the employee's actions.",
                )
            )

    if sentence_count > int(rules.get("warnings", {}).get("max_sentences", 7) or 7):
        warnings.append(
            ValidationIssue(
                code="too_many_sentences",
                severity="warning",
                message="The paragraph is longer than the configured sentence range.",
            )
        )

    for marker in rules.get("conversational_markers", []):
        if str(marker or "").strip() and re.search(re.escape(str(marker or "").strip()), normalized_text, flags=re.IGNORECASE):
            warnings.append(
                ValidationIssue(
                    code="conversational_style",
                    severity="warning",
                    message="The paragraph sounds too conversational.",
                )
            )
            break

    if _is_mask_exception_case(context.normalized_input.draft_text):
        if not (
            _contains_any_substring(normalized_text, _MASK_TRIGGER_TERMS)
            and _contains_any_substring(normalized_text, _ENTERTAINMENT_LOCATION_TERMS)
        ):
            warnings.append(
                ValidationIssue(
                    code="missing_mask_exception_anchor",
                    severity="warning",
                    message="The output lost the key mask exception anchor from the draft facts.",
                )
            )
        if not _contains_any_substring(normalized_text, ("допуска", "разреш")):
            warnings.append(
                ValidationIssue(
                    code="missing_mask_exception_rule",
                    severity="warning",
                    message="The output should state the decisive exception rule for the mask case.",
                )
            )

    if context.normalized_input.retrieval_status == "low_confidence_context":
        infos.append(
            ValidationIssue(
                code="low_confidence_context",
                severity="info",
                message="Low-confidence retrieval context was detected.",
            )
        )
    if policy_mode == MODE_FACTUAL_FALLBACK_EXPANDED and context.policy_decision.reason != "valid_trigger_confirmed":
        infos.append(
            ValidationIssue(
                code="fallback_selected_correctly",
                severity="info",
                message="Fallback mode was selected conservatively.",
            )
        )

    blockers = _dedupe_issues(blockers)
    warnings = _dedupe_issues(warnings)
    infos = _dedupe_issues(infos)
    status = "fail" if blockers else "warn" if warnings else "pass"
    return SuggestValidationResult(
        status=status,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        infos=tuple(infos),
        sentence_count=sentence_count,
    )


def apply_validation_remediation(text: str, context: Point3PipelineContext) -> RemediationOutcome:
    retry_policy = load_retry_policy()
    max_retries = int(retry_policy.get("retry_policy", {}).get("max_retries", 0) or 0)
    candidate = _apply_grounded_output_repairs(normalize_generated_paragraph(text), context)
    validation = validate_generated_paragraph(candidate, context)
    retries_used = 0

    while validation.blockers and retries_used < max_retries:
        candidate = remediate_generated_paragraph(candidate, validation)
        candidate = _apply_grounded_output_repairs(candidate, context)
        retries_used += 1
        validation = validate_generated_paragraph(candidate, context)

    if validation.warning_codes:
        repaired_candidate = _apply_grounded_output_repairs(candidate, context)
        if repaired_candidate != candidate:
            candidate = repaired_candidate
            validation = validate_generated_paragraph(candidate, context)

    safe_fallback_used = False
    if validation.blockers:
        candidate = build_safe_fallback_paragraph(context)
        candidate = _apply_grounded_output_repairs(candidate, context)
        validation = validate_generated_paragraph(candidate, context)
        safe_fallback_used = True

    return RemediationOutcome(
        text=candidate,
        validation=validation,
        retries_used=retries_used,
        safe_fallback_used=safe_fallback_used,
    )


def remediate_generated_paragraph(text: str, validation: SuggestValidationResult) -> str:
    replacements = {str(key).lower(): str(value) for key, value in load_danger_phrases().get("replacements", {}).items()}
    remediated = text
    blockers = sorted(validation.blockers, key=lambda item: (item.start, item.end), reverse=True)
    for issue in blockers:
        replacement = _replacement_for_issue(issue, replacements)
        if issue.start >= 0 and issue.end >= issue.start:
            remediated = remediated[: issue.start] + replacement + remediated[issue.end :]
        elif issue.span_text:
            remediated = remediated.replace(issue.span_text, replacement, 1)
    return _normalize_after_rewrite(remediated)


def build_safe_fallback_paragraph(context: Point3PipelineContext) -> str:
    facts = [item.text.rstrip(".; ") for item in context.facts if item.allow_in_final]
    first_fact = _lower_first(facts[0]) if facts else "в черновике изложены обстоятельства, требующие проверки"
    second_fact = _lower_first(facts[1]) if len(facts) > 1 else "в представленных сведениях отражены дополнительные спорные обстоятельства"
    employee_ref = context.normalized_input.target_person or "сотрудника"
    sentences = [
        f"Из изложенных в черновике обстоятельств следует, что {first_fact}.",
        f"Также указывается, что {second_fact}.",
        f"При таких данных действия {employee_ref} требуют проверки на предмет соблюдения процессуального порядка и достаточности оснований.",
        "Из имеющихся сведений усматривается наличие спорности в оценке фактических обстоятельств, что требует правовой оценки по представленным материалам.",
    ]
    return normalize_generated_paragraph(" ".join(sentences))


def normalize_generated_paragraph(text: str) -> str:
    normalized = str(text or "").replace("\r\n", "\n")
    normalized = re.sub(r"\s+", " ", normalized.replace("\n", " ")).strip()
    normalized = re.sub(r"\s+([,.;:!?])", r"\1", normalized)
    normalized = re.sub(r"([,.;:!?]){2,}", r"\1", normalized)
    return normalized.strip()


def count_sentences(text: str) -> int:
    parts = [item.strip() for item in re.split(r"(?<=[.!?])\s+", str(text or "").strip()) if item.strip()]
    return len(parts)


@lru_cache(maxsize=1)
def load_policy_thresholds() -> dict[str, object]:
    return _load_yaml("policy_thresholds.yaml")


@lru_cache(maxsize=1)
def load_validator_rules() -> dict[str, object]:
    return _load_yaml("validator_rules.yaml")


@lru_cache(maxsize=1)
def load_danger_phrases() -> dict[str, object]:
    return _load_yaml("danger_phrases.yaml")


@lru_cache(maxsize=1)
def load_retry_policy() -> dict[str, object]:
    return _load_yaml("retry_policy.yaml")


def _load_yaml(name: str) -> dict[str, object]:
    path = _CONFIG_DIR / name
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _normalize_inline(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _normalize_multiline(value: object) -> str:
    return re.sub(r"[ \t]+", " ", str(value or "").replace("\r\n", "\n").strip())


def _tokenize(text: str) -> list[str]:
    normalized = re.sub(r"[^0-9a-zа-яё]+", " ", str(text or "").lower())
    return [token for token in normalized.split() if len(token) >= 3 and token not in _STOPWORDS]


def _token_roots(text: str) -> set[str]:
    roots: set[str] = set()
    for token in _tokenize(text):
        normalized = token.lower()
        if len(normalized) >= 8:
            roots.add(normalized[:7])
        elif len(normalized) >= 6:
            roots.add(normalized[:6])
        else:
            roots.add(normalized)
    return roots


def _score_trigger_confidence(
    *,
    retrieval_confidence: str,
    norm_score: int,
    overlap: int,
    matched_in_input: bool,
    document_title: str,
    direct_fact_trigger: bool,
) -> float:
    base = {
        "high": 0.68,
        "medium": 0.56,
        "low": 0.42,
    }.get(str(retrieval_confidence or "").strip().lower(), 0.42)
    score_component = max(0.0, min(float(norm_score or 0), 100.0)) / 320.0
    overlap_component = min(0.18, max(0, int(overlap or 0)) * 0.06)
    input_bonus = 0.08 if matched_in_input else 0.0
    priority_component = _document_priority_weight(document_title) / 1000.0
    confidence = min(0.99, base + score_component + overlap_component + input_bonus + priority_component)
    if not direct_fact_trigger:
        confidence = min(confidence, 0.59)
    return round(confidence, 2)


def _norm_ref_mentioned_in_text(norm_ref: str, draft_text: str) -> bool:
    normalized_ref = _normalize_inline(norm_ref)
    if not normalized_ref:
        return False
    article_numbers = _NUMBER_PATTERN.findall(normalized_ref)
    if not article_numbers:
        return normalized_ref.lower() in str(draft_text or "").lower()
    return any(re.search(rf"\b{re.escape(number)}\b", str(draft_text or "")) for number in article_numbers)


def _primary_article_number(norm_ref: str) -> str:
    numbers = _NUMBER_PATTERN.findall(_normalize_inline(norm_ref))
    return numbers[0] if numbers else ""


def _has_direct_fact_trigger(
    *,
    normalized_input: NormalizedSuggestInput,
    fact_text: str,
    norm: SelectedNorm,
    overlap: int,
) -> bool:
    if _is_mask_exception_trigger(normalized_input=normalized_input, fact_text=fact_text, norm=norm):
        return True

    thresholds = load_policy_thresholds()
    min_root_overlap = int(thresholds["thresholds"].get("min_root_overlap_for_trigger", 1) or 1)
    if overlap < min_root_overlap:
        return False

    group_key = _document_group_key(norm.document_title)
    if group_key == "judicial_system_law":
        combined_text = " ".join(
            (
                normalized_input.draft_text,
                normalized_input.applicability_notes,
                fact_text,
            )
        )
        court_terms = thresholds.get("document_priority", {}).get("court_proceedings_terms", ())
        return _contains_any_substring(combined_text, court_terms)

    if "прецедент" in _normalize_inline(norm.document_title).lower():
        combined_text = " ".join(
            (
                normalized_input.draft_text,
                normalized_input.applicability_notes,
                fact_text,
            )
        )
        court_terms = thresholds.get("document_priority", {}).get("court_proceedings_terms", ())
        return _contains_any_substring(combined_text, court_terms)

    primary_article_number = _primary_article_number(norm.article_label)
    if group_key == "processual_code" and primary_article_number == "19":
        combined_text = " ".join((normalized_input.draft_text, normalized_input.applicability_notes, fact_text))
        return _contains_any_substring(combined_text, _STATE_SERVICE_TERMS)

    if group_key == "processual_code" and primary_article_number == "29":
        combined_text = " ".join((normalized_input.draft_text, normalized_input.applicability_notes, fact_text))
        return _contains_any_substring(combined_text, _SEARCH_ACTION_TERMS)

    if group_key == "advocate_law":
        combined_text = " ".join((normalized_input.draft_text, normalized_input.applicability_notes, fact_text))
        return _contains_any_substring(combined_text, ("адвокат", "запрос", "защит", "юридическ"))

    return True


def _is_mask_exception_trigger(
    *,
    normalized_input: NormalizedSuggestInput,
    fact_text: str,
    norm: SelectedNorm,
) -> bool:
    group_key = _document_group_key(norm.document_title)
    if group_key != "administrative_code":
        return False

    case_text = " ".join((normalized_input.draft_text, fact_text, normalized_input.applicability_notes))
    if not _contains_any_substring(case_text, _MASK_TRIGGER_TERMS):
        return False
    if not _contains_any_substring(case_text, _ENTERTAINMENT_LOCATION_TERMS):
        return False

    norm_text = norm.search_text
    if _primary_article_number(norm_text) != "18":
        return False
    return _contains_any_substring(norm_text, _MASK_TRIGGER_TERMS)


def _document_priority_weight(document_title: str) -> int:
    thresholds = load_policy_thresholds()
    priority_config = thresholds.get("document_priority", {})
    default_weight = int(priority_config.get("default_weight", 0) or 0)
    normalized_title = _normalize_inline(document_title).lower()
    for group in priority_config.get("groups", []):
        patterns = tuple(str(item or "").strip().lower() for item in group.get("patterns", ()) if str(item or "").strip())
        if normalized_title and any(pattern in normalized_title for pattern in patterns):
            return int(group.get("weight", default_weight) or default_weight)
    return default_weight


def _document_group_key(document_title: str) -> str:
    thresholds = load_policy_thresholds()
    normalized_title = _normalize_inline(document_title).lower()
    for group in thresholds.get("document_priority", {}).get("groups", []):
        patterns = tuple(str(item or "").strip().lower() for item in group.get("patterns", ()) if str(item or "").strip())
        if normalized_title and any(pattern in normalized_title for pattern in patterns):
            return str(group.get("key", "") or "").strip()
    return ""


def _contains_any_substring(text: str, values: Iterable[str]) -> bool:
    normalized_text = _normalize_inline(text).lower()
    if not normalized_text:
        return False
    return any(str(value or "").strip().lower() in normalized_text for value in values if str(value or "").strip())


def _has_conflicting_date_mentions(normalized_input: NormalizedSuggestInput) -> bool:
    draft_dates = {item for item in _DATE_PATTERN.findall(normalized_input.draft_text) if item}
    event_dt = normalized_input.event_datetime.strip()
    if not draft_dates or not event_dt:
        return len(draft_dates) > 1
    return len(draft_dates) > 1 or any(item != event_dt for item in draft_dates)


def _has_video_status_conflict(lowered_draft: str) -> bool:
    if not _contains_any_substring(lowered_draft, _VIDEO_TERMS):
        return False
    return _contains_any_substring(lowered_draft, _VIDEO_ABSENCE_MARKERS) and _contains_any_substring(
        lowered_draft,
        _VIDEO_PRESENCE_MARKERS,
    )


def _has_role_ambiguity(lowered_draft: str, target_person: str) -> bool:
    normalized_target = _normalize_inline(target_person).lower()
    if normalized_target and normalized_target in lowered_draft:
        return False
    has_generic_actor = any(
        re.search(rf"\b{re.escape(marker)}\b", lowered_draft, flags=re.IGNORECASE)
        for marker in _GENERIC_ACTOR_MARKERS
    )
    return has_generic_actor and _contains_any_substring(lowered_draft, _INPUT_ACTION_TERMS)


def _has_protected_term_collision(lowered_draft: str, left_group: str, right_group: str) -> bool:
    left_terms = _PROTECTED_TERM_GROUPS.get(left_group, ())
    right_terms = _PROTECTED_TERM_GROUPS.get(right_group, ())
    return _contains_any_substring(lowered_draft, left_terms) and _contains_any_substring(lowered_draft, right_terms)


def _is_personal_conflict_case(draft_text: str) -> bool:
    normalized = _normalize_inline(draft_text).lower()
    return _contains_any_substring(normalized, _PERSONAL_CONFLICT_TERMS) and _contains_any_substring(
        normalized,
        _PROTECTED_TERM_GROUPS.get("detention", ()) + _PROTECTED_TERM_GROUPS.get("arrest", ()),
    )


def _is_generic_processual_trigger(trigger: NormTrigger) -> bool:
    group_key = _document_group_key(trigger.document_title)
    if group_key != "processual_code":
        return False
    return _primary_article_number(trigger.norm_ref) in {"17", "19", "29", "59"}


def _should_force_factual_fallback_for_personal_conflict(
    *,
    normalized_input: NormalizedSuggestInput,
    valid_triggers: Sequence[NormTrigger],
) -> bool:
    if not valid_triggers or not _is_personal_conflict_case(normalized_input.draft_text):
        return False
    return all(_is_generic_processual_trigger(item) and not item.matched_in_input for item in valid_triggers)


def _extract_protected_terms(lowered_draft: str) -> list[str]:
    protected_terms: list[str] = []
    for canonical_name, variants in _PROTECTED_TERM_GROUPS.items():
        if _contains_any_substring(lowered_draft, variants):
            protected_terms.append(canonical_name)
    return protected_terms


def _dedupe_input_issues(issues: Sequence[InputAuditIssue]) -> list[InputAuditIssue]:
    deduped: list[InputAuditIssue] = []
    seen: set[str] = set()
    for issue in issues:
        if issue.code in seen:
            continue
        seen.add(issue.code)
        deduped.append(issue)
    return deduped


def _is_mask_exception_case(text: str) -> bool:
    return _contains_any_substring(text, _MASK_TRIGGER_TERMS) and _contains_any_substring(
        text,
        _ENTERTAINMENT_LOCATION_TERMS,
    )


def _extract_allowed_numbers(context: Point3PipelineContext) -> set[str]:
    allowed: set[str] = set()
    for value in (
        context.normalized_input.complainant,
        context.normalized_input.organization,
        context.normalized_input.target_person,
        context.normalized_input.event_datetime,
        context.normalized_input.draft_text,
    ):
        allowed.update(_NUMBER_PATTERN.findall(str(value or "")))
    if context.policy_decision.mode == MODE_LEGAL_GROUNDED:
        for item in context.triggers:
            if item.is_valid:
                allowed.update(_NUMBER_PATTERN.findall(item.norm_ref))
    return {item for item in allowed if item}


def _extract_allowed_entities(context: Point3PipelineContext) -> set[str]:
    allowed = {
        value.lower()
        for value in (
            context.normalized_input.complainant,
            context.normalized_input.organization,
            context.normalized_input.target_person,
        )
        if value
    }
    for fact in context.facts:
        for candidate, _, _ in _extract_entity_candidates(fact.text):
            allowed.add(candidate.lower())
    if context.policy_decision.mode == MODE_LEGAL_GROUNDED:
        for item in context.triggers:
            if item.is_valid and item.document_title:
                allowed.add(item.document_title.lower())
    return allowed


def _extract_entity_candidates(text: str) -> list[tuple[str, int, int]]:
    results: list[tuple[str, int, int]] = []
    for pattern in (_MULTIWORD_ENTITY_PATTERN, _ALLCAPS_ENTITY_PATTERN):
        for match in pattern.finditer(str(text or "")):
            candidate = _normalize_inline(match.group(0))
            if len(candidate) < 3:
                continue
            results.append((candidate, match.start(), match.end()))
    return results


def _contains_assessment_phrase(text: str, phrases: Iterable[str]) -> bool:
    return any(
        str(phrase or "").strip() and re.search(re.escape(str(phrase or "").strip()), text, flags=re.IGNORECASE)
        for phrase in phrases
    )


def _article_reference_has_document_title(text: str, *, match_start: int, match_end: int) -> bool:
    sentence_start = max(text.rfind(".", 0, match_start), text.rfind("!", 0, match_start), text.rfind("?", 0, match_start))
    sentence_end_candidates = [index for index in (text.find(".", match_end), text.find("!", match_end), text.find("?", match_end)) if index >= 0]
    sentence_end = min(sentence_end_candidates) if sentence_end_candidates else len(text)
    sentence_text = text[sentence_start + 1 : sentence_end].lower()
    return any(marker in sentence_text for marker in _CODE_OR_LAW_MARKERS)


def _clean_document_title_for_reference(document_title: str) -> str:
    cleaned = _normalize_inline(document_title)
    cleaned = re.sub(r"^\s*Важно\s*-\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*\((?:редакция|version)[^)]+\)\s*$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip(" ,;")


def _build_article_reference_title_map(context: Point3PipelineContext) -> tuple[dict[str, str], dict[str, str]]:
    exact_map: dict[str, str] = {}
    number_to_title_candidates: dict[str, set[str]] = {}
    for trigger in context.triggers:
        if not trigger.is_valid:
            continue
        cleaned_title = _clean_document_title_for_reference(trigger.document_title)
        normalized_ref = _normalize_inline(trigger.norm_ref).lower()
        if cleaned_title and normalized_ref:
            exact_map[normalized_ref] = cleaned_title
        for number in _NUMBER_PATTERN.findall(trigger.norm_ref):
            if cleaned_title:
                number_to_title_candidates.setdefault(number, set()).add(cleaned_title)
    number_map = {
        number: next(iter(titles))
        for number, titles in number_to_title_candidates.items()
        if len(titles) == 1
    }
    return exact_map, number_map


def _apply_article_reference_titles(text: str, context: Point3PipelineContext) -> str:
    if context.policy_decision.mode != MODE_LEGAL_GROUNDED:
        return text

    exact_map, number_map = _build_article_reference_title_map(context)

    def replace(match: re.Match[str]) -> str:
        if _article_reference_has_document_title(text, match_start=match.start(), match_end=match.end()):
            return match.group(0)
        ref_text = _normalize_inline(match.group(0))
        normalized_ref = ref_text.lower()
        title = exact_map.get(normalized_ref)
        if not title:
            numbers = _NUMBER_PATTERN.findall(ref_text)
            if numbers:
                title = number_map.get(numbers[0], "")
        if not title:
            return match.group(0)
        return f"{match.group(0)} ({title})"

    return _ARTICLE_REF_PATTERN.sub(replace, text)


def _mask_case_location_phrase(draft_text: str) -> str:
    normalized = _normalize_inline(draft_text)
    if "Maze Bank Arena".lower() in normalized.lower():
        return "на территории Maze Bank Arena"
    return "в соответствующем развлекательном учреждении"


def _apply_mask_exception_rule(text: str, context: Point3PipelineContext) -> str:
    if not _is_mask_exception_case(context.normalized_input.draft_text):
        return text
    if _contains_any_substring(text, ("допуска", "разреш")):
        return text

    article_18_trigger = next(
        (
            item
            for item in context.triggers
            if item.is_valid and _primary_article_number(item.norm_ref) == "18"
        ),
        None,
    )
    if article_18_trigger is None:
        return text

    document_title = _clean_document_title_for_reference(article_18_trigger.document_title)
    location_phrase = _mask_case_location_phrase(context.normalized_input.draft_text)
    sentence = (
        f"При этом статья 18 ({document_title}) предусматривает исключение, при котором ношение маски "
        f"{location_phrase} допускается и требует отдельной проверки достаточности основания задержания."
    ).strip()
    if sentence.lower() in text.lower():
        return text

    parts = [item.strip() for item in re.split(r"(?<=[.!?])\s+", text) if item.strip()]
    if len(parts) >= 2:
        parts.insert(2, sentence)
        return normalize_generated_paragraph(" ".join(parts))
    return normalize_generated_paragraph(f"{text} {sentence}")


def _apply_grounded_output_repairs(text: str, context: Point3PipelineContext) -> str:
    repaired = normalize_generated_paragraph(text)
    repaired = _apply_article_reference_titles(repaired, context)
    repaired = _apply_mask_exception_rule(repaired, context)
    return _normalize_after_rewrite(repaired)


def _dedupe_issues(issues: Sequence[ValidationIssue]) -> list[ValidationIssue]:
    deduped: list[ValidationIssue] = []
    seen: set[tuple[object, ...]] = set()
    for issue in issues:
        key = (issue.code, issue.start, issue.end, issue.span_text.lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(issue)
    return deduped


def _replacement_for_issue(issue: ValidationIssue, replacements: dict[str, str]) -> str:
    span_lower = issue.span_text.lower()
    if issue.code == "strong_unconfirmed_qualification":
        for phrase, replacement in replacements.items():
            if phrase in span_lower:
                return replacement
        return "требует правовой оценки"
    if issue.code == "article_without_valid_trigger":
        return "соответствующих процессуальных требований"
    if issue.code == "new_entity":
        return "сотрудника"
    if issue.code == "new_document":
        return "материалов"
    if issue.code in {"new_url", "new_date", "new_number"}:
        return ""
    return ""


def _normalize_after_rewrite(text: str) -> str:
    normalized = normalize_generated_paragraph(text)
    normalized = re.sub(r"\s+,", ",", normalized)
    normalized = re.sub(r"\(\s*\)", "", normalized)
    normalized = re.sub(r"\s{2,}", " ", normalized)
    normalized = re.sub(r"\.\s*,", ".", normalized)
    normalized = re.sub(r",\s*\.", ".", normalized)
    normalized = re.sub(r"\b(сотрудника|сотрудник)\s+\1\b", r"\1", normalized, flags=re.IGNORECASE)
    normalized = normalized.replace("материалова", "материалов")
    normalized = normalized.replace("оценкисть", "оценки")
    return normalized.strip(" ,;")


def _lower_first(text: str) -> str:
    normalized = _normalize_inline(text)
    if not normalized:
        return normalized
    return normalized[:1].lower() + normalized[1:]


def _truncate_prompt_field(value: object, *, max_chars: int) -> str:
    normalized = _normalize_multiline(value)
    if max_chars <= 0 or len(normalized) <= max_chars:
        return normalized
    truncated = normalized[: max_chars + 1]
    split_index = truncated.rfind(" ")
    if split_index < max(0, int(max_chars * 0.6)):
        split_index = max_chars
    return truncated[:split_index].rstrip(" ,;:-") + "..."

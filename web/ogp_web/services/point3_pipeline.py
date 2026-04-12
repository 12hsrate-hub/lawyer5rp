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
    r"\b(?:ст\.?|статья)\s*\d+(?:\.\d+)?(?:\s*(?:ч\.?|част[ьи])\s*\d+)?(?:\s*(?:п\.?|пункт)\s*[\"«]?[a-zа-яё0-9-]+[\"»]?)?",
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


@dataclass(frozen=True)
class SelectedNorm:
    source_url: str
    document_title: str
    article_label: str
    excerpt: str
    score: int = 0

    def as_contract(self) -> dict[str, object]:
        return {
            "source_url": self.source_url,
            "document_title": self.document_title,
            "article_label": self.article_label,
            "excerpt": self.excerpt,
            "score": self.score,
        }


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

    def as_contract(self) -> dict[str, object]:
        return {
            "fact_id": self.fact_id,
            "norm_ref": self.norm_ref,
            "matched_in_input": self.matched_in_input,
            "matched_in_retrieval": self.matched_in_retrieval,
            "is_valid": self.is_valid,
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
        norm_tokens = _tokenize(" ".join((norm.document_title, norm.article_label, norm.excerpt)))
        for fact in facts:
            overlap = len(set(_tokenize(fact.text)) & set(norm_tokens))
            if overlap > best_overlap:
                best_fact = fact
                best_overlap = overlap
        matched_in_input = _norm_ref_mentioned_in_text(norm.article_label, draft_text)
        matched_in_retrieval = bool(norm.article_label or norm.document_title or norm.excerpt)
        confidence = _score_trigger_confidence(
            retrieval_confidence=normalized_input.retrieval_confidence,
            norm_score=norm.score,
            overlap=max(best_overlap, 0),
            matched_in_input=matched_in_input,
        )
        triggers.append(
            NormTrigger(
                fact_id=best_fact.id,
                norm_ref=norm.article_label or norm.document_title or "N/A",
                matched_in_input=matched_in_input,
                matched_in_retrieval=matched_in_retrieval,
                is_valid=bool(matched_in_retrieval and confidence >= min_valid),
                trigger_confidence=confidence,
                source_url=norm.source_url,
                document_title=norm.document_title,
                excerpt=norm.excerpt,
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

    if valid_triggers and min(item.trigger_confidence for item in valid_triggers) >= min_valid and not borderline_low_confidence:
        return PolicyDecision(
            mode=MODE_LEGAL_GROUNDED,
            reason="valid_trigger_confirmed",
            valid_triggers_count=len(valid_triggers),
            avg_confidence=avg_confidence,
        )
    if borderline_low_confidence:
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
    for match in _ARTICLE_REF_PATTERN.finditer(normalized_text):
        ref_text = _normalize_inline(match.group(0)).lower()
        if policy_mode != MODE_LEGAL_GROUNDED or ref_text not in allowed_article_refs:
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
    candidate = normalize_generated_paragraph(text)
    validation = validate_generated_paragraph(candidate, context)
    retries_used = 0

    while validation.blockers and retries_used < max_retries:
        candidate = remediate_generated_paragraph(candidate, validation)
        retries_used += 1
        validation = validate_generated_paragraph(candidate, context)

    safe_fallback_used = False
    if validation.blockers:
        candidate = build_safe_fallback_paragraph(context)
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


def _score_trigger_confidence(
    *,
    retrieval_confidence: str,
    norm_score: int,
    overlap: int,
    matched_in_input: bool,
) -> float:
    base = {
        "high": 0.68,
        "medium": 0.56,
        "low": 0.42,
    }.get(str(retrieval_confidence or "").strip().lower(), 0.42)
    score_component = max(0.0, min(float(norm_score or 0), 100.0)) / 320.0
    overlap_component = min(0.18, max(0, int(overlap or 0)) * 0.06)
    input_bonus = 0.08 if matched_in_input else 0.0
    return round(min(0.99, base + score_component + overlap_component + input_bonus), 2)


def _norm_ref_mentioned_in_text(norm_ref: str, draft_text: str) -> bool:
    normalized_ref = _normalize_inline(norm_ref)
    if not normalized_ref:
        return False
    article_numbers = _NUMBER_PATTERN.findall(normalized_ref)
    if not article_numbers:
        return normalized_ref.lower() in str(draft_text or "").lower()
    return any(re.search(rf"\b{re.escape(number)}\b", str(draft_text or "")) for number in article_numbers)


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

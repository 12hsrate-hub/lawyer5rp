from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class Clock(Protocol):
    def __call__(self) -> float: ...


class RetryableGenerator(Protocol):
    def __call__(self, *, prompt_text: str, attempt_index: int) -> Any: ...


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int


@dataclass(frozen=True)
class RetryAttemptMeta:
    attempt_index: int
    compaction_level: int
    prompt_text: str


@dataclass(frozen=True)
class TelemetryBudgetMeta:
    telemetry: dict[str, object]
    budget_status: str
    budget_warnings: list[str]
    budget_policy: dict[str, object]


@dataclass(frozen=True)
class LawQaAnswerResult:
    text: str
    generation_id: str
    used_sources: list[str]
    indexed_documents: int
    retrieval_confidence: str
    retrieval_profile: str
    guard_status: str
    contract_version: str
    bundle_status: str
    bundle_generated_at: str
    bundle_fingerprint: str
    warnings: list[str]
    shadow: dict[str, object]
    selected_norms: list[dict[str, object]]
    telemetry: dict[str, object]
    budget_status: str
    budget_warnings: list[str]
    budget_policy: dict[str, object]


@dataclass(frozen=True)
class SuggestTextResult:
    text: str
    generation_id: str
    guard_status: str
    contract_version: str
    warnings: list[str]
    shadow: dict[str, object]
    telemetry: dict[str, object]
    budget_status: str
    budget_warnings: list[str]
    budget_policy: dict[str, object]
    retrieval_ms: int
    openai_ms: int
    total_suggest_ms: int
    prompt_mode: str
    retrieval_confidence: str
    retrieval_context_mode: str
    retrieval_profile: str
    bundle_status: str
    bundle_generated_at: str
    bundle_fingerprint: str
    selected_norms_count: int
    policy_mode: str = ""
    policy_reason: str = ""
    valid_triggers_count: int = 0
    avg_trigger_confidence: float = 0.0
    remediation_retries: int = 0
    safe_fallback_used: bool = False
    input_warning_codes: tuple[str, ...] = ()
    protected_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class SuggestContextBuildResult:
    context_text: str
    retrieval_confidence: str
    retrieval_context_mode: str
    retrieval_profile: str
    bundle_status: str
    bundle_generated_at: str
    bundle_fingerprint: str
    selected_norms_count: int
    selected_norms: tuple[dict[str, object], ...] = ()

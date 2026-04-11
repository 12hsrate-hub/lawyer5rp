from __future__ import annotations

from dataclasses import asdict, dataclass
import os
import re

from shared.ogp_ai import AiUsageSummary


@dataclass(frozen=True)
class ModelPricing:
    input_per_million_usd: float
    output_per_million_usd: float
    source: str = "official_default"


@dataclass(frozen=True)
class AiTelemetry:
    model: str
    input_chars: int
    output_chars: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: int
    usage_source: str
    cache_hit: bool
    estimated_cost_usd: float | None
    pricing_source: str


@dataclass(frozen=True)
class AiBudgetPolicy:
    flow: str
    prompt_warn_tokens: int
    output_warn_tokens: int
    total_warn_tokens: int
    cost_warn_usd: float | None = None
    preferred_models: tuple[str, ...] = ()


@dataclass(frozen=True)
class AiBudgetAssessment:
    status: str
    warnings: tuple[str, ...]
    policy: AiBudgetPolicy


_MODEL_PRICING_DEFAULTS: dict[str, tuple[float, float]] = {
    # Official OpenAI pricing as of 2026-04-11.
    "gpt-5.4": (2.50, 15.00),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5-mini": (0.75, 4.50),
    "gpt-4.1-mini": (0.80, 3.20),
}


_BUDGET_POLICY_DEFAULTS: dict[str, AiBudgetPolicy] = {
    "law_qa": AiBudgetPolicy(
        flow="law_qa",
        prompt_warn_tokens=14000,
        output_warn_tokens=1400,
        total_warn_tokens=15000,
        cost_warn_usd=0.06,
        preferred_models=("gpt-5-mini", "gpt-4.1-mini", "gpt-5.4-mini", "gpt-5.4"),
    ),
    "suggest": AiBudgetPolicy(
        flow="suggest",
        prompt_warn_tokens=9000,
        output_warn_tokens=1100,
        total_warn_tokens=10000,
        cost_warn_usd=0.035,
        preferred_models=("gpt-5-mini", "gpt-4.1-mini", "gpt-5.4-mini", "gpt-5.4"),
    ),
}


def _model_env_key(model_name: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", str(model_name or "").strip().upper()).strip("_")


def _env_float(name: str, default: float | None = None) -> float | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def estimate_text_tokens(text: str) -> int:
    normalized = str(text or "")
    if not normalized.strip():
        return 0
    # Simple heuristic for GPT-family text prompts: ~4 chars per token on average.
    return max(1, int(round(len(normalized) / 4)))


def resolve_model_pricing(model_name: str) -> ModelPricing | None:
    normalized = str(model_name or "").strip().lower()
    if not normalized:
        return None
    env_key = _model_env_key(normalized)
    env_input = _env_float(f"OGP_AI_PRICE_{env_key}_INPUT_USD_PER_1M")
    env_output = _env_float(f"OGP_AI_PRICE_{env_key}_OUTPUT_USD_PER_1M")
    if env_input is not None and env_output is not None:
        return ModelPricing(
            input_per_million_usd=max(0.0, env_input),
            output_per_million_usd=max(0.0, env_output),
            source="env_override",
        )
    default = _MODEL_PRICING_DEFAULTS.get(normalized)
    if default is None:
        return None
    return ModelPricing(
        input_per_million_usd=default[0],
        output_per_million_usd=default[1],
        source="official_default",
    )


def build_ai_telemetry(
    *,
    model_name: str,
    prompt_text: str,
    output_text: str,
    usage: AiUsageSummary | None = None,
    latency_ms: int = 0,
    cache_hit: bool = False,
) -> AiTelemetry:
    input_chars = len(str(prompt_text or ""))
    output_chars = len(str(output_text or ""))
    actual_input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    actual_output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    actual_total_tokens = int(getattr(usage, "total_tokens", 0) or 0)

    input_tokens = actual_input_tokens or estimate_text_tokens(prompt_text)
    output_tokens = actual_output_tokens or estimate_text_tokens(output_text)
    total_tokens = actual_total_tokens or (input_tokens + output_tokens)

    if actual_input_tokens and actual_output_tokens:
        usage_source = "actual"
    elif actual_input_tokens or actual_output_tokens or actual_total_tokens:
        usage_source = "mixed"
    else:
        usage_source = "estimated"

    pricing = resolve_model_pricing(model_name)
    if cache_hit:
        estimated_cost_usd = 0.0
        pricing_source = "local_cache"
    elif pricing is None:
        estimated_cost_usd = None
        pricing_source = "unconfigured"
    else:
        estimated_cost_usd = round(
            (input_tokens * pricing.input_per_million_usd + output_tokens * pricing.output_per_million_usd) / 1_000_000,
            6,
        )
        pricing_source = pricing.source

    return AiTelemetry(
        model=str(model_name or "").strip(),
        input_chars=input_chars,
        output_chars=output_chars,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        latency_ms=max(0, int(latency_ms or 0)),
        usage_source=usage_source,
        cache_hit=bool(cache_hit),
        estimated_cost_usd=estimated_cost_usd,
        pricing_source=pricing_source,
    )


def get_budget_policy(flow: str) -> AiBudgetPolicy:
    normalized_flow = str(flow or "").strip().lower()
    base = _BUDGET_POLICY_DEFAULTS.get(normalized_flow) or _BUDGET_POLICY_DEFAULTS["suggest"]
    prefix = f"OGP_AI_BUDGET_{normalized_flow.upper()}"
    prompt_warn = int(_env_float(f"{prefix}_PROMPT_WARN_TOKENS", float(base.prompt_warn_tokens)) or base.prompt_warn_tokens)
    output_warn = int(_env_float(f"{prefix}_OUTPUT_WARN_TOKENS", float(base.output_warn_tokens)) or base.output_warn_tokens)
    total_warn = int(_env_float(f"{prefix}_TOTAL_WARN_TOKENS", float(base.total_warn_tokens)) or base.total_warn_tokens)
    cost_warn = _env_float(f"{prefix}_COST_WARN_USD", base.cost_warn_usd)
    return AiBudgetPolicy(
        flow=normalized_flow or base.flow,
        prompt_warn_tokens=max(1, prompt_warn),
        output_warn_tokens=max(1, output_warn),
        total_warn_tokens=max(1, total_warn),
        cost_warn_usd=cost_warn,
        preferred_models=base.preferred_models,
    )


def evaluate_budget(*, flow: str, telemetry: AiTelemetry) -> AiBudgetAssessment:
    policy = get_budget_policy(flow)
    warnings: list[str] = []
    if telemetry.input_tokens >= policy.prompt_warn_tokens:
        warnings.append("budget_prompt_warn")
    if telemetry.output_tokens >= policy.output_warn_tokens:
        warnings.append("budget_output_warn")
    if telemetry.total_tokens >= policy.total_warn_tokens:
        warnings.append("budget_total_warn")
    if policy.cost_warn_usd is not None and telemetry.estimated_cost_usd is not None:
        if telemetry.estimated_cost_usd >= policy.cost_warn_usd:
            warnings.append("budget_cost_warn")
    if telemetry.pricing_source == "unconfigured":
        warnings.append("budget_pricing_unconfigured")
    status = "warn" if warnings else "ok"
    return AiBudgetAssessment(status=status, warnings=tuple(warnings), policy=policy)


def telemetry_to_meta(telemetry: AiTelemetry) -> dict[str, object]:
    return asdict(telemetry)


def policy_to_meta(policy: AiBudgetPolicy) -> dict[str, object]:
    return asdict(policy)

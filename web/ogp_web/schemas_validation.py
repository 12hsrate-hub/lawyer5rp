from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ValidationIssueResponse(BaseModel):
    id: int
    validation_run_id: int
    issue_code: str
    severity: str
    message: str
    field_ref: str = ""
    details_json: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""


class ValidationRunResponse(BaseModel):
    id: int
    target_type: str
    target_id: int
    server_id: str
    status: str
    risk_score: float
    coverage_score: float
    readiness_status: str
    summary_json: dict[str, Any] = Field(default_factory=dict)
    score_breakdown_json: dict[str, Any] = Field(default_factory=dict)
    gate_decisions_json: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str = ""
    issues: list[ValidationIssueResponse] = Field(default_factory=list)

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from ogp_web.storage.validation_repository import ValidationRepository


@dataclass(frozen=True)
class ValidationResult:
    run: dict[str, Any]
    issues: list[dict[str, Any]]
    gates_blocking: list[dict[str, Any]]


class ValidationService:
    def __init__(self, repository: ValidationRepository):
        self.repository = repository

    @staticmethod
    def _normalize_json(value: Any, default: Any):
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(str(value or ""))
        except Exception:  # noqa: BLE001
            return default

    @staticmethod
    def _legacy_enforcement_enabled() -> bool:
        return str(os.getenv("OGP_VALIDATION_LEGACY_ENFORCEMENT", "0") or "").strip() in {"1", "true", "yes", "on"}

    def _resolve_target(self, *, target_type: str, target_id: int) -> tuple[str, str, dict[str, Any]]:
        if target_type == "document_version":
            row = self.repository.get_document_version_target(version_id=target_id)
            if not row:
                raise ValueError("Document version not found.")
            payload = self._normalize_json(row.get("content_json"), {})
            subtype = str(row.get("document_type") or "").strip()
            return str(row["server_id"]), subtype, {"bbcode": str(payload.get("bbcode") or ""), "content_json": payload}
        if target_type == "law_qa_run":
            row = self.repository.get_law_qa_run_target(run_id=target_id)
            if not row:
                raise ValueError("Law QA run not found.")
            used_sources = self._normalize_json(row.get("used_sources_json"), [])
            selected_norms = self._normalize_json(row.get("selected_norms_json"), [])
            return str(row["server_id"]), "law_qa", {
                "question": str(row.get("question") or ""),
                "answer_text": str(row.get("answer_text") or ""),
                "used_sources": used_sources if isinstance(used_sources, list) else [],
                "selected_norms": selected_norms if isinstance(selected_norms, list) else [],
            }
        raise ValueError("Unsupported target type.")

    def run_validation(self, *, target_type: str, target_id: int) -> ValidationResult:
        server_id, target_subtype, target_payload = self._resolve_target(target_type=target_type, target_id=target_id)
        requirements = self.repository.get_applicable_requirements(
            target_type=target_type,
            target_subtype=target_subtype,
            server_id=server_id,
        )
        gates = self.repository.get_applicable_readiness_gates(
            target_type=target_type,
            target_subtype=target_subtype,
            server_id=server_id,
        )

        issues: list[dict[str, Any]] = []
        required_total = 0
        required_ok = 0

        for row in requirements:
            field_key = str(row.get("field_key") or "").strip()
            if not field_key:
                continue
            required = bool(row.get("is_required"))
            expected_type = str(self._normalize_json(row.get("rule_json"), {}).get("expected_type") or "").strip()
            value = target_payload.get(field_key)
            present = value is not None and str(value).strip() != ""
            if required:
                required_total += 1
            valid = present
            if expected_type == "list" and present:
                valid = isinstance(value, list) and len(value) > 0
            elif expected_type == "dict" and present:
                valid = isinstance(value, dict) and len(value) > 0
            if required and valid:
                required_ok += 1
            if required and not valid:
                issues.append(
                    {
                        "issue_code": "required_field_missing",
                        "severity": "error",
                        "message": f"Missing required field: {field_key}",
                        "field_ref": field_key,
                        "details_json": {"field_key": field_key, "target_type": target_type},
                    }
                )

        if target_type == "document_version":
            bbcode = str(target_payload.get("bbcode") or "")
            if "[quote" not in bbcode and "http" not in bbcode:
                issues.append(
                    {
                        "issue_code": "citation_missing",
                        "severity": "warning",
                        "message": "Document has no explicit citation markers.",
                        "field_ref": "bbcode",
                        "details_json": {},
                    }
                )
        if target_type == "law_qa_run":
            if not target_payload.get("used_sources"):
                issues.append(
                    {
                        "issue_code": "source_coverage_missing",
                        "severity": "error",
                        "message": "Law QA answer has no used sources.",
                        "field_ref": "used_sources",
                        "details_json": {},
                    }
                )

        errors = sum(1 for item in issues if item["severity"] == "error")
        warnings = sum(1 for item in issues if item["severity"] == "warning")
        coverage_score = 100.0 if required_total == 0 else round((required_ok / required_total) * 100.0, 2)
        risk_score = min(100.0, round(errors * 35.0 + warnings * 10.0, 2))

        gate_decisions: list[dict[str, Any]] = []
        gates_blocking: list[dict[str, Any]] = []
        for gate in gates:
            thresholds = self._normalize_json(gate.get("threshold_json"), {})
            min_coverage = float(thresholds.get("min_coverage_score", 0) or 0)
            max_risk = float(thresholds.get("max_risk_score", 100) or 100)
            mode = str(gate.get("enforcement_mode") or "off").strip().lower()
            violated = coverage_score < min_coverage or risk_score > max_risk
            decision = {
                "gate_code": str(gate.get("gate_code") or ""),
                "enforcement_mode": mode,
                "violated": violated,
                "thresholds": {"min_coverage_score": min_coverage, "max_risk_score": max_risk},
            }
            gate_decisions.append(decision)
            if violated and mode == "hard_block":
                gates_blocking.append(decision)

        if gates_blocking or errors > 0:
            readiness_status = "blocked"
            status = "fail"
        elif warnings > 0:
            readiness_status = "needs_review"
            status = "warn"
        else:
            readiness_status = "ready"
            status = "pass"

        score_breakdown_json = {
            "errors": errors,
            "warnings": warnings,
            "required_total": required_total,
            "required_ok": required_ok,
            "legacy_enforcement_enabled": self._legacy_enforcement_enabled(),
        }
        summary_json = {
            "target_type": target_type,
            "target_id": target_id,
            "issues_count": len(issues),
            "blocking_gates": [item["gate_code"] for item in gates_blocking],
        }

        run = self.repository.create_validation_run(
            target_type=target_type,
            target_id=target_id,
            server_id=server_id,
            status=status,
            risk_score=risk_score,
            coverage_score=coverage_score,
            readiness_status=readiness_status,
            summary_json=summary_json,
            score_breakdown_json=score_breakdown_json,
            gate_decisions_json=gate_decisions,
        )
        created_issues = self.repository.create_validation_issues(validation_run_id=int(run["id"]), issues=issues)
        return ValidationResult(run=dict(run), issues=[dict(item) for item in created_issues], gates_blocking=gates_blocking)

    def get_validation_run_details(self, *, run_id: int) -> dict[str, Any] | None:
        run = self.repository.get_validation_run(run_id=run_id)
        if not run:
            return None
        issues = self.repository.list_validation_issues(validation_run_id=int(run["id"]))
        payload = dict(run)
        payload["summary_json"] = self._normalize_json(payload.get("summary_json"), {})
        payload["score_breakdown_json"] = self._normalize_json(payload.get("score_breakdown_json"), {})
        payload["gate_decisions_json"] = self._normalize_json(payload.get("gate_decisions_json"), [])
        payload["issues"] = [{**dict(item), "details_json": self._normalize_json(item.get("details_json"), {})} for item in issues]
        return payload

    def get_latest_target_validation(self, *, target_type: str, target_id: int) -> dict[str, Any] | None:
        latest = self.repository.get_latest_validation_run(target_type=target_type, target_id=target_id)
        if not latest:
            return None
        return self.get_validation_run_details(run_id=int(latest["id"]))

    def assert_action_allowed(
        self,
        *,
        target_type: str,
        target_id: int,
        action: str,
        legacy_mode: bool = False,
    ) -> tuple[bool, list[str]]:
        latest = self.get_latest_target_validation(target_type=target_type, target_id=target_id)
        if not latest:
            return False, [f"missing_validation_for_{action}"]
        messages: list[str] = []
        blocked = False
        for item in latest.get("gate_decisions_json", []):
            if not item.get("violated"):
                continue
            mode = str(item.get("enforcement_mode") or "off").strip().lower()
            code = str(item.get("gate_code") or "gate")
            if mode == "warn":
                messages.append(f"{action}:{code}:warn")
            elif mode == "hard_block":
                if legacy_mode and not self._legacy_enforcement_enabled():
                    messages.append(f"{action}:{code}:legacy_soft_fail")
                else:
                    blocked = True
                    messages.append(f"{action}:{code}:blocked")
        return (not blocked), messages

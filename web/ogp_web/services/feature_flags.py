from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ogp_web.services.auth_service import is_admin_user


class RolloutMode(str, Enum):
    OFF = "off"
    INTERNAL = "internal"
    BETA = "beta"
    ALL = "all"


class EnforcementMode(str, Enum):
    OFF = "off"
    WARN = "warn"
    HARD = "hard"


class Cohort(str, Enum):
    DEFAULT = "default"
    INTERNAL = "internal"
    BETA = "beta"


FEATURE_FLAGS = (
    "cases_v1",
    "documents_v2",
    "citations_required",
    "validation_gate_v1",
    "async_jobs_v1",
    "pilot_runtime_adapter_v1",
    "pilot_shadow_compare_v1",
)


@dataclass(frozen=True)
class FlagDecision:
    flag: str
    mode: RolloutMode
    cohort: Cohort
    use_new_flow: bool
    enforcement: EnforcementMode


@dataclass(frozen=True)
class RolloutContext:
    username: str
    server_id: str


class FeatureFlagService:
    """Server-side rollout decision service for staged feature flags."""

    def __init__(self) -> None:
        self._json_config = self._load_json()

    @staticmethod
    def _split_env_list(value: str) -> set[str]:
        return {item.strip().lower() for item in str(value or "").split(",") if item.strip()}

    def _load_json(self) -> dict[str, Any]:
        raw = str(os.getenv("OGP_FEATURE_FLAGS_JSON", "") or "").strip()
        if not raw:
            return {}
        try:
            payload = json.loads(raw)
            return payload if isinstance(payload, dict) else {}
        except Exception:  # noqa: BLE001
            return {}

    def _flag_config(self, flag: str) -> dict[str, Any]:
        flag_json = self._json_config.get(flag)
        if isinstance(flag_json, dict):
            return flag_json
        return {}

    def _mode(self, flag: str) -> RolloutMode:
        from_env = str(os.getenv(f"OGP_FEATURE_FLAG_{flag.upper()}_MODE", "") or "").strip().lower()
        if from_env in {item.value for item in RolloutMode}:
            return RolloutMode(from_env)
        from_json = str(self._flag_config(flag).get("mode") or "").strip().lower()
        if from_json in {item.value for item in RolloutMode}:
            return RolloutMode(from_json)
        return RolloutMode.OFF

    def _enforcement(self, flag: str) -> EnforcementMode:
        from_env = str(os.getenv(f"OGP_FEATURE_FLAG_{flag.upper()}_ENFORCEMENT", "") or "").strip().lower()
        if from_env in {item.value for item in EnforcementMode}:
            return EnforcementMode(from_env)
        from_json = str(self._flag_config(flag).get("enforcement") or "").strip().lower()
        if from_json in {item.value for item in EnforcementMode}:
            return EnforcementMode(from_json)
        if flag in {"citations_required", "validation_gate_v1"}:
            return EnforcementMode.WARN
        return EnforcementMode.OFF

    def _internal_usernames(self, flag: str) -> set[str]:
        global_items = self._split_env_list(os.getenv("OGP_INTERNAL_USERNAMES", ""))
        flag_items = self._split_env_list(os.getenv(f"OGP_FEATURE_FLAG_{flag.upper()}_INTERNAL_USERS", ""))
        json_items = {
            str(item).strip().lower()
            for item in (self._flag_config(flag).get("internal_users") or [])
            if str(item).strip()
        }
        return global_items | flag_items | json_items

    def _beta_usernames(self, flag: str) -> set[str]:
        global_items = self._split_env_list(os.getenv("OGP_BETA_USERNAMES", ""))
        flag_items = self._split_env_list(os.getenv(f"OGP_FEATURE_FLAG_{flag.upper()}_BETA_USERS", ""))
        json_items = {
            str(item).strip().lower()
            for item in (self._flag_config(flag).get("beta_users") or [])
            if str(item).strip()
        }
        return global_items | flag_items | json_items

    def _internal_servers(self, flag: str) -> set[str]:
        global_items = self._split_env_list(os.getenv("OGP_INTERNAL_SERVER_IDS", ""))
        flag_items = self._split_env_list(os.getenv(f"OGP_FEATURE_FLAG_{flag.upper()}_INTERNAL_SERVERS", ""))
        json_items = {
            str(item).strip().lower()
            for item in (self._flag_config(flag).get("internal_servers") or [])
            if str(item).strip()
        }
        return global_items | flag_items | json_items

    def _beta_servers(self, flag: str) -> set[str]:
        global_items = self._split_env_list(os.getenv("OGP_BETA_SERVER_IDS", ""))
        flag_items = self._split_env_list(os.getenv(f"OGP_FEATURE_FLAG_{flag.upper()}_BETA_SERVERS", ""))
        json_items = {
            str(item).strip().lower()
            for item in (self._flag_config(flag).get("beta_servers") or [])
            if str(item).strip()
        }
        return global_items | flag_items | json_items

    def _resolve_cohort(self, *, flag: str, username: str, server_id: str) -> Cohort:
        normalized_username = str(username or "").strip().lower()
        normalized_server_id = str(server_id or "").strip().lower()

        if (
            is_admin_user(normalized_username)
            or normalized_username in self._internal_usernames(flag)
            or normalized_server_id in self._internal_servers(flag)
        ):
            return Cohort.INTERNAL
        if normalized_username in self._beta_usernames(flag) or normalized_server_id in self._beta_servers(flag):
            return Cohort.BETA
        return Cohort.DEFAULT

    def evaluate(self, *, flag: str, context: RolloutContext) -> FlagDecision:
        if flag not in FEATURE_FLAGS:
            raise ValueError(f"Unknown feature flag: {flag}")
        mode = self._mode(flag)
        cohort = self._resolve_cohort(flag=flag, username=context.username, server_id=context.server_id)

        use_new_flow = False
        if mode == RolloutMode.ALL:
            use_new_flow = True
        elif mode == RolloutMode.INTERNAL:
            use_new_flow = cohort == Cohort.INTERNAL
        elif mode == RolloutMode.BETA:
            use_new_flow = cohort in {Cohort.INTERNAL, Cohort.BETA}

        return FlagDecision(
            flag=flag,
            mode=mode,
            cohort=cohort,
            use_new_flow=use_new_flow,
            enforcement=self._enforcement(flag),
        )

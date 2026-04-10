from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from shared.ogp_models import Representative, Victim


@dataclass
class ComplaintInput:
    appeal_no: str
    org: str
    subject_names: str
    situation_description: str
    violation_short: str
    event_dt: str
    today_date: str
    representative: Representative
    victim: Victim
    evidence_items: List[Tuple[str, str]]


@dataclass
class RehabInput:
    representative: Representative
    principal_name: str
    principal_passport: str
    principal_passport_scan_url: str
    served_seven_days: bool
    contract_url: str
    today_date: str

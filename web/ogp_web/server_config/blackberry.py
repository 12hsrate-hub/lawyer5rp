from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ogp_web.services.complaint_draft_schema import (
    DEFAULT_VALUE_TRANSFORM_RULES,
    LEGACY_FIELD_ALIASES,
    SEMANTIC_KEY_SPECS,
)
from ogp_web.services.exam_sheet_service import EXAM_SHEET_URL

from shared.ogp_core import BASE_EVIDENCE_FIELDS

from .types import ComplaintBasisConfig, EvidenceFieldConfig, NavItemConfig, ServerConfig


BLACKBERRY_TEST_COMPLAINT_PRESET = {
    "representative": {
        "name": "Test Advocate",
        "passport": "778899",
        "address": "Los Santos, Integrity Way, 10",
        "phone": "5550200",
        "discord": "testadvocate",
        "passport_scan_url": "https://example.com/representative-passport",
    },
    "appeal_no": "T001",
    "org": "LSPD",
    "subject_names": "Officer John Doe, badge #4412",
    "event_dt": "2026-04-08T14:30",
    "victim_name": "Test Victim",
    "victim_passport": "123456",
    "victim_address": "Los Santos, Vespucci Blvd, 1",
    "victim_phone": "5550100",
    "victim_discord": "testvictim",
    "victim_scan": "https://example.com/victim-passport",
    "situation_description": "Тестовое описание ситуации: адвокат прибыл на место задержания, запросил материалы и доступ к процессуальным документам, однако получил отказ без объяснения причин. Дополнительно сотрудник отказался сообщить процессуальную статью обвинения и затруднил коммуникацию.",
    "violation_short": "Непредоставление материалов, процессуальной статьи обвинения и препятствие работе адвоката.",
    "contract_url": "https://example.com/contract",
    "bar_request_url": "https://example.com/bar-request",
    "official_answer_url": "https://example.com/official-answer",
    "mail_notice_url": "https://example.com/mail-notice",
    "arrest_record_url": "https://example.com/arrest-record",
    "personnel_file_url": "https://example.com/personnel-file",
    "video_fix_urls": (
        "https://example.com/video-fix-1",
        "https://example.com/video-fix-2",
    ),
    "provided_video_urls": (
        "https://example.com/provided-video-1",
    ),
}


def _bootstrap_pack_path() -> Path:
    return Path(__file__).resolve().parent / "packs" / "blackberry.bootstrap.json"


def load_blackberry_bootstrap_pack_metadata() -> dict[str, Any]:
    try:
        payload = json.loads(_bootstrap_pack_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    metadata = payload.get("metadata")
    return dict(metadata) if isinstance(metadata, dict) else {}


def build_server_config_from_pack(*, metadata: dict[str, Any], code: str = "blackberry", name: str = "BlackBerry") -> ServerConfig:
    complaint_bases_raw = metadata.get("complaint_bases") if isinstance(metadata, dict) else None
    complaint_bases: list[ComplaintBasisConfig] = []
    if isinstance(complaint_bases_raw, list):
        for item in complaint_bases_raw:
            if not isinstance(item, dict):
                continue
            basis_code = str(item.get("code") or "").strip()
            if not basis_code:
                continue
            complaint_bases.append(
                ComplaintBasisConfig(
                    code=basis_code,
                    label=str(item.get("label") or basis_code),
                    description=str(item.get("description") or ""),
                )
            )

    organizations_raw = metadata.get("organizations") if isinstance(metadata, dict) else []
    procedure_types_raw = metadata.get("procedure_types") if isinstance(metadata, dict) else []

    return ServerConfig(
        code=code,
        name=name,
        app_title="OGP Builder Web",
        organizations=tuple(str(item).strip() for item in organizations_raw if str(item).strip()),
        complaint_bases=tuple(complaint_bases),
        procedure_types=tuple(str(item).strip() for item in procedure_types_raw if str(item).strip()),
        evidence_fields=tuple(
            EvidenceFieldConfig(
                field_name=field_name,
                label=field_label,
                required=field_name == "contract_url",
            )
            for field_name, field_label in BASE_EVIDENCE_FIELDS
        ),
        form_schema=dict(metadata.get("form_schema") or {}),
        validation_profiles=dict(metadata.get("validation_profiles") or {}),
        template_bindings=dict(metadata.get("template_bindings") or {}),
        terminology={
            str(key): str(value)
            for key, value in dict(metadata.get("terminology") or {}).items()
        },
        page_nav_items=(
            NavItemConfig(key="complaint", label="Жалоба", href="/complaint"),
            NavItemConfig(key="rehab", label="Реабилитация", href="/rehab"),
            NavItemConfig(
                key="court_claim_test",
                label="Судебный иск",
                href="/court-claim-test",
                permission="court_claims",
            ),
            NavItemConfig(
                key="law_qa_test",
                label="Тест законов",
                href="/law-qa-test",
                permission="court_claims",
            ),
            NavItemConfig(
                key="exam_import",
                label="Проверка тестов",
                href="/exam-import-test",
                permission="exam_import",
            ),
            NavItemConfig(key="admin", label="Админ", href="/admin", permission="manage_servers"),
        ),
        complaint_nav_items=(
            NavItemConfig(key="complaint", label="Жалоба", href="/complaint"),
            NavItemConfig(key="rehab", label="Реабилитация", href="/rehab"),
            NavItemConfig(
                key="court_claim_test",
                label="Исковые заявления",
                href="/court-claim-test",
                permission="court_claims",
            ),
            NavItemConfig(
                key="law_qa_test",
                label="Q&A по законам",
                href="/law-qa-test",
                permission="court_claims",
            ),
            NavItemConfig(
                key="exam_import",
                label="Проверка тестов",
                href="/exam-import-test",
                permission="exam_import",
            ),
        ),
        enabled_pages=frozenset(
            {
                "complaint",
                "rehab",
                "profile",
                "court_claim_test",
                "law_qa_test",
                "complaint_test",
                "exam_import",
                "admin",
            }
        ),
        feature_flags=frozenset(
            {
                "complaint_generation",
                "rehab_generation",
                "court_claims",
                "exam_import",
                "admin_panel",
                "legal_bundle_freshness",
                "legal_feedback_loop",
                "legal_guard_validation",
                "legal_pipeline_contract",
            }
        ),
        law_qa_sources=(
            "https://forum.gta5rp.com/threads/processualnyi-kodeks-shtata-san-andreas-redakcija-ot-29-marta-2026-goda.826899/",
            "https://forum.gta5rp.com/threads/sudebnye-precedenty.1291064/",
            "https://forum.gta5rp.com/threads/dorozhnyi-kodeks-shtata-san-andreas-redakcija-ot-29-marta-2025-goda.826974/",
            "https://forum.gta5rp.com/threads/administrativnyi-kodeks-shtata-san-andreas-redakcija-ot-29-marta-2025-goda.827016/",
            "https://forum.gta5rp.com/threads/ugolovnyi-kodeks-shtata-san-andreas-redakcija-ot-29-marta-2026-goda.826988/",
            "https://forum.gta5rp.com/threads/grazhdanskii-kodeks-shtata-san-andreas-redakcija-ot-05-marta-2026-goda.932736/",
            "https://forum.gta5rp.com/threads/ehticheskii-kodeks-shtata-san-andreas-redakcija-ot-19-oktjabrja-2024-goda.826971/",
            "https://forum.gta5rp.com/threads/konstitucija-shtata-san-andreas-redakcija-ot-29-marta-2026-goda.826866/",
            "https://forum.gta5rp.com/threads/zakon-ob-advokature-i-advokatskoi-dejatelnosti-v-shtate-san-andreas-redakcija-ot-05-marta-2026-goda.827351/",
            "https://forum.gta5rp.com/threads/zakon-o-sudebnoi-sisteme-i-sudoproizvodstve-redakcija-ot-29-marta-2025.3284901/",
            "https://forum.gta5rp.com/threads/zakon-o-dejatelnosti-regionalnyx-pravooxranitelnyx-organov-redakcija-ot-29-marta-2026-goda.3284897/",
            "https://forum.gta5rp.com/threads/zakon-o-federalnom-rassledovatelskom-bjuro-redakcija-ot-29-marta-2026-goda.827363/",
            "https://forum.gta5rp.com/threads/kodeks-o-dejatelnosti-pravitelstva-shtata-san-andreas-redakcija-ot-29-marta-2026-goda.3253844/",
            "https://forum.gta5rp.com/threads/kodeks-o-zakonodatelnoi-vlasti-i-politicheskix-partijax-shtata-san-andreas-redakcija-ot-26-ijulja-2025-goda.3253847/",
            "https://forum.gta5rp.com/threads/trudovoi-kodeks-shtata-san-andreas-redakcija-ot-29-marta-2026-goda.827090/",
            "https://forum.gta5rp.com/threads/zakon-o-predprinimatelskoi-dejatelnosti-i-nalogooblozhenii-redakcija-ot-26-ijulja-2025-goda.827261/",
            "https://forum.gta5rp.com/threads/zakon-o-gosudarstvennoi-taine-v-shtate-san-andreas-redakcija-ot-27-ijunja-2025-goda.827290/",
        ),
        law_qa_bundle_path="law_bundles/blackberry.json",
        law_qa_bundle_max_age_hours=168,
        suggest_prompt_mode="data_driven",
        suggest_low_confidence_policy="controlled_fallback",
        exam_sheet_url=EXAM_SHEET_URL,
        complaint_forum_url="https://forum.gta5rp.com/forums/zhaloby-v-prokuraturu.748/",
        complaint_test_preset=BLACKBERRY_TEST_COMPLAINT_PRESET,
        complaint_supported_keys=tuple(SEMANTIC_KEY_SPECS.keys()),
        complaint_legacy_key_map=dict(LEGACY_FIELD_ALIASES),
        complaint_value_transforms=dict(DEFAULT_VALUE_TRANSFORM_RULES),
    )


BLACKBERRY_BOOTSTRAP_SERVER_PACK = {
    "version": 1,
    "status": "published",
    "server_code": "blackberry",
    "metadata": load_blackberry_bootstrap_pack_metadata(),
}


BLACKBERRY_SERVER_CONFIG = build_server_config_from_pack(
    metadata=BLACKBERRY_BOOTSTRAP_SERVER_PACK["metadata"],
    code="blackberry",
    name="BlackBerry",
)

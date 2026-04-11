from __future__ import annotations

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


BLACKBERRY_SERVER_CONFIG = ServerConfig(
    code="blackberry",
    name="BlackBerry",
    app_title="OGP Builder Web",
    organizations=(
        "LSPD",
        "GOV",
        "FIB",
        "LSSD",
        "ARMY",
        "SANG",
        "EMS",
        "WN",
    ),
    complaint_bases=(
        ComplaintBasisConfig(
            code="wrongful_article",
            label="Неверная квалификация",
            description="Спор по применённой статье или правовой квалификации.",
        ),
        ComplaintBasisConfig(
            code="no_materials_by_request",
            label="Не выдали материалы",
            description="Материалы не предоставлены по запросу адвоката.",
        ),
        ComplaintBasisConfig(
            code="no_video_or_no_evidence",
            label="Нет видео или доказательств",
            description="Отсутствуют видеоматериалы или надлежащая доказательная база.",
        ),
    ),
    evidence_fields=tuple(
        EvidenceFieldConfig(
            field_name=field_name,
            label=field_label,
            required=field_name == "contract_url",
        )
        for field_name, field_label in BASE_EVIDENCE_FIELDS
    ),
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
        NavItemConfig(key="admin", label="Админ", href="/admin", permission="admin"),
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
        }
    ),
    exam_sheet_url=EXAM_SHEET_URL,
    complaint_forum_url="https://forum.gta5rp.com/forums/zhaloby-v-prokuraturu.748/",
    complaint_test_preset=BLACKBERRY_TEST_COMPLAINT_PRESET,
)

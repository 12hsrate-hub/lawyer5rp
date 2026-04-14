from __future__ import annotations

from ogp_web.services.exam_sheet_service import EXAM_SHEET_URL

from shared.ogp_core import BASE_EVIDENCE_FIELDS

from .types import ComplaintBasisConfig, ComplaintTemplateProfile, EvidenceFieldConfig, NavItemConfig, ServerConfig


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
    complaint_template_profile=ComplaintTemplateProfile(
        addressee="Attorney General's office, San-Andreas, Burton, Eastbourne Way. Dear Attorney General Konstantin Belonozhkin.",
        legal_insertions=(
            "Прошу рассмотреть обращение в соответствии с действующим законодательством штата Сан-Андреас.",
        ),
        authority_name_format="{org}",
        required_requisites=(
            ("appeal_no", "Номер обращения"),
            ("org", "Организация"),
            ("subject_names", "Объект заявления"),
            ("event_dt", "Дата и время события"),
            ("victim.name", "ФИО потерпевшего"),
            ("victim.passport", "Паспорт потерпевшего"),
            ("victim.phone", "Телефон потерпевшего"),
            ("victim.discord", "Discord потерпевшего"),
            ("victim.passport_scan_url", "Скан паспорта потерпевшего (URL)"),
            ("representative.name", "Профиль: ФИО представителя"),
            ("representative.passport", "Профиль: паспорт"),
            ("representative.address", "Профиль: адрес"),
            ("representative.phone", "Профиль: телефон"),
            ("representative.discord", "Профиль: Discord"),
            ("representative.passport_scan_url", "Профиль: скан паспорта (URL)"),
        ),
        required_evidence_titles=("Договор на оказание юридических услуг",),
        bundle_template="""[RIGHT][I]To: {addressee}[/I][/RIGHT]

[CENTER]
[SIZE=5]Обращение №{appeal_no}[/SIZE]
Я, гражданин штата Сан-Андреас {representative_name}, являясь законным представителем гражданина {victim_name} и в его интересах, обращаюсь к Вам с просьбой рассмотреть следующую ситуацию и принять необходимые меры в соответствии с законом:
[/CENTER]

[B]Суть обращения:[/B]
[LIST=1]
[*]Организация, в которой состоит объект заявления: {org_name}
[*]Объект заявления (имя и фамилия, удостоверение, бейджик, нашивка, жетон): {subject_names}
[*]Подробное описание ситуации: {situation_description}
[*]Формулировка сути нарушения: {violation_short}
[*]Дата и время описываемых событий: {event_dt}
[*]Доказательства: {evidence_line}
[/LIST]

[B]Правовые вставки:[/B]
[LIST]
{legal_insertions_block}
[/LIST]

[B]Информация о представителе:[/B]
[LIST=1]
[*]Имя, фамилия: {representative_name}
[*]Номер паспорта: {representative_passport}
[*]Адрес проживания: {representative_address}
[*]Номер телефона: {representative_phone}
[*]Адрес электронной почты (( discord )): [EMAIL]{representative_email}[/EMAIL]
[*]Ксерокопия паспорта (( imgur.com )): [URL='{representative_scan_url}']Паспорт[/URL]
[/LIST]

[B]Информация о потерпевшем:[/B]
[LIST=1]
[*]Имя, фамилия: {victim_name}
[*]Номер паспорта: {victim_passport}
[*]Адрес проживания: {victim_address}
[*]Номер телефона: {victim_phone}
[*]Адрес электронной почты (( discord )): [EMAIL]{victim_email}[/EMAIL]
[*]Ксерокопия паспорта (( imgur.com )): [URL='{victim_scan_url}']Паспорт[/URL]
[/LIST]

[B][FONT=trebuchet ms]Дата: [/FONT][/B][FONT=trebuchet ms][U]{today_date} г.[/U][/FONT]
[B][FONT=trebuchet ms]Подпись: {representative_name}[/FONT][/B]
""",
    ),
)

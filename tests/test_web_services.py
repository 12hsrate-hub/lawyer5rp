from __future__ import annotations

import gc
import os
import shutil
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

os.environ.setdefault("OGP_DB_BACKEND", "sqlite")
os.environ.setdefault("OGP_WEB_SECRET", "test-secret")

import httpx
from fastapi import HTTPException

from ogp_web.db.backends.sqlite import SQLiteBackend
from ogp_web.schemas import ComplaintPayload, LawQaPayload, PrincipalScanPayload, RehabPayload, SuggestPayload, VictimPayload
from ogp_web.services import ai_service, auth_service, complaint_service, email_service, exam_import_service, exam_sheet_service
from ogp_web.services.auth_service import AuthUser
from ogp_web.storage.user_repository import UserRepository
from ogp_web.storage.user_store import UserStore
from tests.temp_helpers import make_temp_dir


class WebServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = make_temp_dir()
        root = Path(self.tmpdir)
        self.store = UserStore(
            root / "app.db",
            root / "users.json",
            repository=UserRepository(SQLiteBackend(root / "app.db")),
        )
        self.user, token = self.store.register("tester", "tester@example.com", "Password123!")
        self.store.confirm_email(token)

    def tearDown(self):
        del self.store
        gc.collect()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_auth_service_session_token_roundtrip(self):
        token = auth_service.create_session_token("tester")
        user = auth_service.parse_session_token(token)
        self.assertIsNotNone(user)
        self.assertEqual(user.username, "tester")

    def test_auth_service_rejects_tampered_session_token(self):
        token = auth_service.create_session_token("tester")
        tampered = token[:-2] + "ab"
        self.assertIsNone(auth_service.parse_session_token(tampered))

    def test_email_service_prefers_configured_public_base_url(self):
        previous = os.environ.get("OGP_WEB_BASE_URL")
        os.environ["OGP_WEB_BASE_URL"] = "https://www.lawyer5rp.online/"
        try:
            value = email_service.build_public_base_url("http://127.0.0.1:8000/")
        finally:
            if previous is None:
                os.environ.pop("OGP_WEB_BASE_URL", None)
            else:
                os.environ["OGP_WEB_BASE_URL"] = previous
        self.assertEqual(value, "https://www.lawyer5rp.online")

    def test_email_service_returns_not_sent_without_smtp_host(self):
        previous_host = os.environ.get("SMTP_HOST")
        os.environ.pop("SMTP_HOST", None)
        try:
            result = email_service.send_verification_email(
                recipient="tester@example.com",
                username="tester",
                verification_url="https://example.com/verify",
            )
        finally:
            if previous_host is not None:
                os.environ["SMTP_HOST"] = previous_host
        self.assertFalse(result.sent)

    def test_complaint_service_to_domain_model_uses_profile_and_defaults(self):
        self.store.save_representative_profile(
            "tester",
            {
                "name": "Rep",
                "passport": "AA",
                "address": "Addr",
                "phone": "1234567",
                "discord": "disc",
                "passport_scan_url": "https://example.com/rep",
            },
        )
        payload = ComplaintPayload(
            appeal_no="123",
            org="LSPD",
            subject_names="Officer",
            situation_description="",
            violation_short="",
            event_dt="08.04.2026 14:30",
            victim=VictimPayload(
                name="Victim",
                passport="BB",
                address="Addr",
                phone="7654321",
                discord="victim",
                passport_scan_url="https://example.com/victim",
            ),
            contract_url="https://example.com/contract",
        )

        complaint = complaint_service.to_domain_model(self.store, payload, AuthUser(username="tester"))
        self.assertEqual(complaint.representative.name, "Rep")
        self.assertTrue(complaint.situation_description)
        self.assertTrue(complaint.violation_short)
        self.assertEqual(len(complaint.evidence_items), 1)

    def test_complaint_service_generate_rehab_bbcode_text(self):
        self.store.save_representative_profile(
            "tester",
            {
                "name": "Rep",
                "passport": "AA",
                "address": "Addr",
                "phone": "1234567",
                "discord": "disc",
                "passport_scan_url": "https://example.com/rep",
            },
        )
        payload = RehabPayload(
            principal_name="Victim",
            principal_passport="BB",
            principal_passport_scan_url="https://example.com/principal",
            served_seven_days=True,
            contract_url="https://example.com/contract",
            today_date="08.04.2026",
        )
        text = complaint_service.generate_rehab_bbcode_text(self.store, payload, AuthUser(username="tester"))
        self.assertIn("Rep", text)
        self.assertIn("Victim", text)

    def test_exam_sheet_service_parse_and_build_score_items(self):
        csv_text = (
            "submitted,full_name,discord,passport,format,QF,QG\n"
            "2026-04-08,Student,disc,123456,Очнo,Answer F,Answer G\n"
            "\n"
        )
        rows = exam_sheet_service.parse_exam_sheet_csv(csv_text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_row"], 2)

        items = exam_sheet_service.build_exam_score_items(rows[0]["payload"])
        columns = {item["column"] for item in items}
        self.assertIn("F", columns)
        self.assertIn("G", columns)
        first_item = next(item for item in items if item["column"] == "F")
        self.assertEqual(first_item["question"], "QF")
        self.assertEqual(first_item["key_points"], exam_sheet_service.EXAM_KEY_POINTS["F"])

    def test_exam_sheet_service_build_score_items_includes_ad_when_answer_key_exists(self):
        payload = {
            "submitted": "2026-04-08",
            "full_name": "Student",
            "discord": "disc",
            "passport": "123456",
            "format": "OCHNO",
        }
        for suffix in (
            "F",
            "G",
            "H",
            "I",
            "J",
            "K",
            "L",
            "M",
            "N",
            "O",
            "P",
            "Q",
            "R",
            "S",
            "T",
            "U",
            "V",
            "W",
            "X",
            "Y",
            "Z",
            "AA",
            "AB",
            "AC",
            "AD",
        ):
            payload[f"Q{suffix}"] = f"Answer {suffix}"

        items = exam_sheet_service.build_exam_score_items(payload)

        columns = {item["column"] for item in items}
        self.assertIn("AD", columns)
        n_item = next(item for item in items if item["column"] == "N")
        self.assertTrue(n_item["key_points"])

    def test_exam_sheet_service_anchors_question_columns_after_exam_format(self):
        payload = {
            "submitted": "2026-04-08",
            "full_name": "Student",
            "discord": "disc",
            "passport": "123456",
            "exam_type_extra": "Государственный адвокат",
            "format": "Государственный адвокат",
            "Составной вопрос": "Answer F",
            "Последний вопрос": "Answer AD",
        }

        items = exam_sheet_service.build_exam_score_items(payload)

        self.assertGreaterEqual(len(items), 2)
        self.assertEqual(items[0]["column"], "F")
        self.assertEqual(items[0]["question"], "Составной вопрос")
        self.assertEqual(items[1]["column"], "G")

    def test_exam_sheet_service_uses_row_payload_as_correct_answers(self):
        payload = {
            "submitted": "2026-04-08",
            "full_name": "Student",
            "discord": "disc",
            "passport": "123456",
            "exam_type_extra": "Государственный адвокат",
            "format": "Государственный адвокат",
            "QF": "candidate F",
        }
        row4_payload = {
            "submitted": "",
            "full_name": "эталонные ответы",
            "discord": "",
            "passport": "",
            "exam_type_extra": "эталонные ответы",
            "format": "эталонные ответы",
            "QF": "row4 F",
        }

        dynamic_answers = exam_sheet_service.build_exam_correct_answers_from_payload(row4_payload)
        items = exam_sheet_service.build_exam_score_items(payload, correct_answers=dynamic_answers)

        self.assertEqual(items[0]["column"], "F")
        self.assertEqual(items[0]["correct_answer"], "row4 F")

    def test_exam_sheet_service_build_exam_correct_answers_from_payload_is_stable_for_unordered_jsonb(self):
        payload = {
            "column_31": "",
            "Р¤РѕСЂРјР°С‚ СЌРєР·Р°РјРµРЅР°": "РџРѕР»СѓС‡РµРЅРёРµ Р»РёС†РµРЅР·РёРё Р°РґРІРѕРєР°С‚Р°",
            "Р’Р°С€Рµ РРјСЏ/Р¤Р°РјРёР»РёСЏ? (РїСЂРёРјРµСЂ Pavel Clayton)": "Р­С‚Р°Р»РѕРЅРЅС‹Р№ РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ",
            "РЎРёС‚СѓР°С‚РёРІРЅС‹Р№ РІРѕРїСЂРѕСЃ. Р’Р°С€ РїРѕРґР·Р°С‰РёС‚РЅС‹Р№ Р±С‹Р» Р·Р°РґРµСЂР¶Р°РЅ Р·Р° СЃС‚. 18 РђРљ РЅР° РїР°СЂРєРѕРІРєРµ РєР°Р·РёРЅРѕ Diamond Р·Р° РЅРѕС€РµРЅРёРµ РјР°СЃРєРё РёР»Рё РёРЅРѕРіРѕ СЃСЂРµРґСЃС‚РІР° РјР°СЃРєРёСЂРѕРІРєРё Р»РёС‡РЅРѕСЃС‚Рё. РџСЂР°РІРѕРјРµСЂРЅРѕ Р»Рё Р·Р°РґРµСЂР¶Р°РЅРёРµ РёР»Рё РЅРµС‚? РћС‚РІРµС‚ РїРѕСЏСЃРЅРёС‚СЊ.": "РћС‚РІРµС‚ РїРѕ AC",
            "РЎРѕСЃС‚Р°РІРЅРѕР№ РІРѕРїСЂРѕСЃ. РЎС‚Р°С‚СЊСЏ 14 РђРљ СЃРѕРѕР±С‰Р°РµС‚ РЅР°Рј Рѕ РІС‹РїСѓСЃРєРµ РіСЂР°Р¶РґР°РЅ РїРѕРґ Р·Р°Р»РѕРі.  (1) Р“СЂР°Р¶РґР°РЅ, РѕСЃСѓР¶РґРµРЅРЅС‹С… РїРѕ РєР°РєРёРј Р·Р°РєРѕРЅР°Рј Рё РєРѕРґРµРєСЃР°Рј Р°РґРІРѕРєР°С‚С‹ РІРїСЂР°РІРµ РІС‹РїСѓСЃРєР°С‚СЊ Р°СЂРµСЃС‚РѕРІР°РЅРЅС‹С… РїРѕРґ Р·Р°Р»РѕРі? (2) РљР°Рє РЅР°Р·РЅР°С‡Р°РµС‚СЃСЏ СЃС‚РѕРёРјРѕСЃС‚СЊ Р·Р°Р»РѕРіР°?": "РћС‚РІРµС‚ РїРѕ F",
            "РћР±С‰РёР№ РІРѕРїСЂРѕСЃ. РџРѕС‡РµРјСѓ Р·Р°СЏРІР»РµРЅРёРµ: вЂњСЏ РЅРµ Р·РЅР°Р», С‡С‚Рѕ С‚Р°Рє РґРµР»Р°С‚СЊ РЅРµР»СЊР·СЏвЂќ РЅРµ СЂР°Р±РѕС‚Р°РµС‚? РЎРѕС€Р»РёС‚РµСЃСЊ РЅР° РЅРѕСЂРјСѓ Р·Р°РєРѕРЅР°.": "РћС‚РІРµС‚ РїРѕ AD",
            "Р’Р°С€ DiscordTag РґР»СЏ СЃРІСЏР·Рё? (РїСЂРёРјРµСЂ: musiksash)": "tag#0001",
            "Р’Р°С€ РЅРѕРјРµСЂ РїР°СЃРїРѕСЂС‚Р°?": "654321",
        }

        answers = exam_sheet_service.build_exam_correct_answers_from_payload(payload)

        self.assertEqual(answers["F"], "РћС‚РІРµС‚ РїРѕ F")
        self.assertEqual(answers["AC"], "РћС‚РІРµС‚ РїРѕ AC")
        self.assertEqual(answers["AD"], "РћС‚РІРµС‚ РїРѕ AD")

    def test_exam_sheet_service_skips_personal_columns_from_scoring(self):
        payload = {
            "submitted": "2026-04-08",
            "full_name": "Student",
            "discord": "disc",
            "passport": "123456",
            "format": "Государственный адвокат",
            "Ваше Имя/Фамилия?": "Имя Фамилия",
            "Ваш DiscordTag для связи?": "tag#0001",
            "Ваш номер паспорта?": "654321",
            "QF": "answer F",
        }

        items = exam_sheet_service.build_exam_score_items(payload)
        columns = {item["column"] for item in items}

        self.assertIn("F", columns)
        self.assertNotIn("G", columns)

    def test_exam_sheet_service_is_stable_for_unordered_payload_from_jsonb(self):
        payload = {
            "column_31": "",
            "Формат экзамена": "Получение лицензии адвоката",
            "Ваше Имя/Фамилия? (пример Pavel Clayton)": "Nikitos Reground",
            "Ситуативный вопрос. Ваш подзащитный был задержан за ст. 18 АК на парковке казино Diamond за ношение маски или иного средства маскировки личности. Правомерно ли задержание или нет? Ответ пояснить.": "Ответ по AC",
            "Составной вопрос. Статья 14 АК сообщает нам о выпуске граждан под залог.  (1) Граждан, осужденных по каким законам и кодексам адвокаты вправе выпускать арестованных под залог? (2) Как назначается стоимость залога?": "Ответ по F",
            "Общий вопрос. Почему заявление: “я не знал, что так делать нельзя” не работает? Сошлитесь на норму закона.": "Ответ по AD",
            "Ваш DiscordTag для связи? (пример: musiksash)": "tag#0001",
            "Ваш номер паспорта?": "654321",
        }

        items = exam_sheet_service.build_exam_score_items(payload)
        by_column = {item["column"]: item for item in items}

        self.assertEqual(by_column["F"]["user_answer"], "Ответ по F")
        self.assertEqual(by_column["AC"]["user_answer"], "Ответ по AC")
        self.assertEqual(by_column["AD"]["user_answer"], "Ответ по AD")

    def test_exam_sheet_service_load_exam_correct_answers_skips_empty_values(self):
        original_content = exam_sheet_service.EXAM_ANSWER_KEY_PATH.read_text(encoding="utf-8")
        exam_sheet_service.load_exam_correct_answers.cache_clear()
        try:
            exam_sheet_service.EXAM_ANSWER_KEY_PATH.write_text(
                '{"F": "Valid answer", "G": "", "H": null, "I": "  "}',
                encoding="utf-8",
            )
            answers = exam_sheet_service.load_exam_correct_answers()
        finally:
            exam_sheet_service.EXAM_ANSWER_KEY_PATH.write_text(original_content, encoding="utf-8")
            exam_sheet_service.load_exam_correct_answers.cache_clear()

        self.assertEqual(answers, {"F": "Valid answer"})

    def test_exam_sheet_service_normalizes_exam_type(self):
        self.assertEqual(
            exam_sheet_service.normalize_exam_type("Государственный адвокат"),
            exam_sheet_service.EXAM_STATE_TYPE,
        )
        self.assertEqual(
            exam_sheet_service.normalize_exam_type("Получение лицензии адвоката"),
            exam_sheet_service.EXAM_LICENSE_TYPE,
        )

    def test_exam_sheet_service_fetch_wraps_http_errors(self):
        original_get = exam_sheet_service.httpx.get

        def fake_get(*args, **kwargs):
            raise httpx.ConnectError("boom")

        exam_sheet_service.httpx.get = fake_get
        try:
            with self.assertRaises(HTTPException) as ctx:
                exam_sheet_service.fetch_exam_sheet_rows()
        finally:
            exam_sheet_service.httpx.get = original_get

        self.assertEqual(ctx.exception.status_code, 502)

    def test_ai_service_suggest_text_validates_required_fields(self):
        with self.assertRaises(HTTPException) as ctx:
            ai_service.suggest_text(SuggestPayload(victim_name="", org="", subject="", event_dt="", raw_desc=""))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_ai_service_suggest_text_wraps_provider_errors(self):
        original = ai_service.suggest_description_with_proxy_fallback_result
        ai_service.suggest_description_with_proxy_fallback_result = (
            lambda **kwargs: (_ for _ in ()).throw(RuntimeError("timeout"))
        )
        try:
            with self.assertRaises(HTTPException) as ctx:
                ai_service.suggest_text(
                    SuggestPayload(
                        victim_name="Victim",
                        org="LSPD",
                        subject="Officer",
                        event_dt="08.04.2026 14:30",
                        raw_desc="Draft",
                    )
                )
        finally:
            ai_service.suggest_description_with_proxy_fallback_result = original
        self.assertEqual(ctx.exception.status_code, 500)

    def test_ai_service_suggest_text_passes_optional_focus_fields(self):
        captured: dict[str, str] = {}
        original = ai_service.suggest_description_with_proxy_fallback_result
        original_build_context = ai_service._build_suggest_law_context

        def fake_suggest(**kwargs):
            captured.update(kwargs)
            return ai_service.TextGenerationResult(
                text="ok",
                usage=ai_service.AiUsageSummary(input_tokens=10, output_tokens=5, total_tokens=15),
                cache_hit=False,
                attempt_path="direct",
                attempt_duration_ms=321,
                route_policy="direct_first",
            )

        ai_service.suggest_description_with_proxy_fallback_result = fake_suggest
        ai_service._build_suggest_law_context = lambda **kwargs: "Источник: https://laws.example\nНорма: Статья 20"
        try:
            result = ai_service.suggest_text_details(
                SuggestPayload(
                    victim_name="Victim",
                    org="LSPD",
                    subject="Officer",
                    event_dt="08.04.2026 14:30",
                    raw_desc="Draft",
                    complaint_basis="wrongful_article",
                    main_focus="Спорная квалификация",
                ),
                server_code="blackberry",
            )
        finally:
            ai_service.suggest_description_with_proxy_fallback_result = original
            ai_service._build_suggest_law_context = original_build_context

        self.assertEqual(result.text, "ok")
        self.assertEqual(captured["complaint_basis"], "wrongful_article")
        self.assertEqual(captured["main_focus"], "Спорная квалификация")
        self.assertEqual(captured["law_context"], "Источник: https://laws.example\nНорма: Статья 20")
        self.assertEqual(result.telemetry["attempt_path"], "direct")
        self.assertEqual(result.telemetry["attempt_duration_ms"], 321)
        self.assertEqual(result.telemetry["route_policy"], "direct_first")
        self.assertEqual(result.telemetry["usage_source"], "actual")

    def test_suggest_text_details_records_stage_timings_in_metrics_meta(self):
        original_suggest = ai_service.suggest_description_with_proxy_fallback_result
        original_build_context = ai_service._build_suggest_law_context
        original_monotonic = ai_service.monotonic
        ticks = iter((100.0, 100.125, 100.250, 100.500, 100.750, 101.000))

        ai_service._build_suggest_law_context = lambda **kwargs: "Источник: https://laws.example\nНорма: Статья 20"
        ai_service.suggest_description_with_proxy_fallback_result = lambda **kwargs: ai_service.TextGenerationResult(
            text="Описание фактов по жалобе.\n\nУказан ключевой эпизод задержания.",
            usage=ai_service.AiUsageSummary(),
            cache_hit=False,
            attempt_path="proxy",
            attempt_duration_ms=250,
            route_policy="proxy_first",
        )
        ai_service.monotonic = lambda: next(ticks)
        payload = SuggestPayload(
            victim_name="Victim",
            org="LSPD",
            subject="Officer",
            event_dt="08.04.2026 14:30",
            raw_desc="Draft",
            complaint_basis="wrongful_article",
            main_focus="Нарушение процедуры",
        )
        try:
            result = ai_service.suggest_text_details(payload, server_code="blackberry")
        finally:
            ai_service.suggest_description_with_proxy_fallback_result = original_suggest
            ai_service._build_suggest_law_context = original_build_context
            ai_service.monotonic = original_monotonic

        meta = ai_service.build_suggest_metrics_meta(payload=payload, result=result, server_code="blackberry")
        self.assertEqual(result.retrieval_ms, 125)
        self.assertEqual(result.openai_ms, 250)
        self.assertEqual(result.total_suggest_ms, 1000)
        self.assertEqual(meta["retrieval_ms"], 125)
        self.assertEqual(meta["openai_ms"], 250)
        self.assertEqual(meta["total_suggest_ms"], 1000)
        self.assertEqual(meta["prompt_mode"], "data_driven")
        self.assertEqual(meta["retrieval_context_mode"], "normal_context")
        self.assertEqual(meta["selected_norms_count"], 0)

    def test_build_suggest_retrieval_query_light_formats_fields_in_expected_order(self):
        payload = SuggestPayload(
            victim_name="Victim",
            org="  LSPD  ",
            subject="  Officer North  ",
            event_dt="08.04.2026 14:30",
            raw_desc="  First fact.\nSecond fact.  ",
            complaint_basis="  wrongful_article  ",
            main_focus="  procedural_violation  ",
        )

        query = ai_service.build_suggest_retrieval_query_light(payload)

        self.assertEqual(
            query,
            "wrongful_article procedural_violation LSPD Officer North First fact. Second fact.",
        )

    def test_build_suggest_retrieval_query_light_truncates_only_raw_desc_fragment(self):
        payload = SuggestPayload(
            victim_name="Victim",
            org="LSPD",
            subject="Officer",
            event_dt="08.04.2026 14:30",
            raw_desc=" ".join(f"token{i}" for i in range(80)),
            complaint_basis="wrongful_article",
            main_focus="procedural_violation",
        )

        query = ai_service.build_suggest_retrieval_query_light(payload, raw_desc_limit=48)

        self.assertTrue(query.startswith("wrongful_article procedural_violation LSPD Officer "))
        self.assertIn("token0", query)
        self.assertNotIn("token20", query)
        self.assertTrue(query.endswith("…"))

    def test_build_suggest_retrieval_query_light_expands_mask_exception_case(self):
        payload = SuggestPayload(
            victim_name="Victim",
            org="LSPD",
            subject="Officer",
            event_dt="08.04.2026 14:30",
            raw_desc=(
                "Человека задержали на территории Maze Bank Arena из-за ношения маски, "
                "после отказа снять её оформили задержание."
            ),
            complaint_basis="procedural_violation",
            main_focus="Спорность оснований задержания",
        )

        query = ai_service.build_suggest_retrieval_query_light(payload)

        self.assertIn("статья 18 административный кодекс", query.lower())
        self.assertIn("допустимость ношения маски", query.lower())
        self.assertIn("maze bank arena", query.lower())

    def test_ai_service_suggest_text_uses_lightweight_query_only_for_retrieval(self):
        captured: dict[str, str] = {}
        original = ai_service.suggest_description_with_proxy_fallback_result
        original_build_context = ai_service._build_suggest_law_context

        def fake_suggest(**kwargs):
            captured["provider_raw_desc"] = kwargs["raw_desc"]
            captured["provider_law_context"] = kwargs["law_context"]
            return ai_service.TextGenerationResult(
                text="Описание фактов по жалобе.\n\nУказан ключевой эпизод задержания.",
                usage=ai_service.AiUsageSummary(),
                cache_hit=False,
                attempt_path="proxy",
                attempt_duration_ms=180,
                route_policy="proxy_first",
            )

        def fake_context(**kwargs):
            captured["retrieval_query"] = kwargs["question"]
            return "Источник: https://laws.example\nНорма: Статья 20"

        raw_desc = " ".join(f"fact{i}" for i in range(120))
        ai_service.suggest_description_with_proxy_fallback_result = fake_suggest
        ai_service._build_suggest_law_context = fake_context
        try:
            text = ai_service.suggest_text(
                SuggestPayload(
                    victim_name="Victim",
                    org="LSPD",
                    subject="Officer",
                    event_dt="08.04.2026 14:30",
                    raw_desc=raw_desc,
                    complaint_basis="wrongful_article",
                    main_focus="procedural_violation",
                ),
                server_code="blackberry",
            )
        finally:
            ai_service.suggest_description_with_proxy_fallback_result = original
            ai_service._build_suggest_law_context = original_build_context

        self.assertTrue(text.startswith("Описание фактов"))
        self.assertEqual(captured["provider_raw_desc"], raw_desc)
        self.assertEqual(captured["provider_law_context"], "Источник: https://laws.example\nНорма: Статья 20")
        self.assertIn("wrongful_article procedural_violation LSPD Officer", captured["retrieval_query"])
        self.assertNotIn("fact100", captured["retrieval_query"])

    def test_suggest_text_details_filters_prompt_law_context_to_valid_mask_exception_trigger(self):
        captured: dict[str, str] = {}
        original = ai_service.suggest_description_with_proxy_fallback_result
        original_build_context = ai_service._build_suggest_law_context

        def fake_suggest(**kwargs):
            captured["provider_law_context"] = kwargs["law_context"]
            return ai_service.TextGenerationResult(
                text=(
                    "Человека задержали на территории Maze Bank Arena из-за ношения маски. "
                    "Эти обстоятельства требуют проверки. "
                    "Действия сотрудника вызывают сомнения. "
                    "Необходима правовая оценка по представленным материалам."
                ),
                usage=ai_service.AiUsageSummary(),
                cache_hit=False,
                attempt_path="proxy",
                attempt_duration_ms=180,
                route_policy="proxy_first",
            )

        ai_service.suggest_description_with_proxy_fallback_result = fake_suggest
        ai_service._build_suggest_law_context = lambda **kwargs: ai_service.SuggestContextBuildResult(
            context_text=(
                "Источник: https://laws.example/admin\n"
                "Документ: Административный кодекс\n"
                "Норма: Статья 18\n"
                "Фрагмент: Использование маски допустимо в Maze Bank Arena.\n\n"
                "Источник: https://laws.example/processual\n"
                "Документ: Процессуальный кодекс\n"
                "Норма: Статья 23.1 Порядок наложения штрафа (тикета)\n"
                "Фрагмент: Сотрудник обязан подготовить тикет и указать сумму штрафа."
            ),
            retrieval_confidence="high",
            retrieval_context_mode="normal_context",
            retrieval_profile="suggest",
            bundle_status="ready",
            bundle_generated_at="2026-04-12T00:00:00Z",
            bundle_fingerprint="bundle-mask-test",
            selected_norms_count=2,
            selected_norms=(
                {
                    "source_url": "https://laws.example/admin",
                    "document_title": "Административный кодекс",
                    "article_label": "Статья 18",
                    "excerpt": "Использование маски допускается на территории Maze Bank Arena.",
                    "score": 92,
                },
                {
                    "source_url": "https://laws.example/processual",
                    "document_title": "Процессуальный кодекс",
                    "article_label": "Статья 23.1 Порядок наложения штрафа (тикета)",
                    "excerpt": "Сотрудник обязан подготовить тикет и указать сумму штрафа.",
                    "score": 35,
                },
            ),
        )
        try:
            result = ai_service.suggest_text_details(
                SuggestPayload(
                    victim_name="Victim",
                    org="LSPD",
                    subject="Officer",
                    event_dt="08.04.2026 14:30",
                    raw_desc=(
                        "Человека задержали на территории Maze Bank Arena из-за ношения маски, "
                        "потребовали снять её без внятного основания, а после отказа оформили задержание."
                    ),
                    complaint_basis="procedural_violation",
                    main_focus="Спорность оснований задержания",
                ),
                server_code="blackberry",
            )
        finally:
            ai_service.suggest_description_with_proxy_fallback_result = original
            ai_service._build_suggest_law_context = original_build_context

        self.assertEqual(result.policy_mode, "legal_grounded")
        self.assertIn("Статья 18", captured["provider_law_context"])
        self.assertNotIn("23.1", captured["provider_law_context"])
        self.assertNotIn("тикет", captured["provider_law_context"].lower())
        self.assertNotIn("штраф", captured["provider_law_context"].lower())

    def test_build_suggest_law_context_extracts_qualifiers_and_cross_refs(self):
        original_get_server_config = ai_service.get_server_config
        original_load_bundle = ai_service.load_law_bundle_chunks
        original_select_chunks = ai_service._select_law_qa_chunks

        class DummyServerConfig:
            code = "blackberry"
            name = "BlackBerry"
            law_qa_sources = ()
            law_qa_bundle_path = "bundle.json"

        chunk = ai_service._LawChunk(
            url="https://laws.example/admin",
            document_title="Административный кодекс",
            article_label="Статья 22 ч. 2",
            text=(
                "Статья 22 ч. 2. Основное правило. "
                "Исключение: допускается иной порядок при наличии отдельного основания. "
                "Примечание: оценка производится с учетом фактических обстоятельств. "
                "Комментарий II. Дополнительно применяется подход, описанный в статье 33 Процессуального кодекса."
            ),
        )

        ai_service.get_server_config = lambda server_code: DummyServerConfig()
        ai_service.load_law_bundle_chunks = lambda server_code, bundle_path: [chunk]
        ai_service._select_law_qa_chunks = lambda chunks, question, profile="suggest": (list(chunks), "high")
        try:
            context = ai_service._build_suggest_law_context(
                server_code="blackberry",
                question="разъяснения по статье 22 части 2",
            )
        finally:
            ai_service.get_server_config = original_get_server_config
            ai_service.load_law_bundle_chunks = original_load_bundle
            ai_service._select_law_qa_chunks = original_select_chunks

        qualifiers = context.selected_norms[0]["qualifiers"]
        qualifier_kinds = {item["kind"] for item in qualifiers}
        self.assertTrue({"exception", "note", "comment"}.issubset(qualifier_kinds))
        self.assertTrue(any("33" in ref for ref in context.selected_norms[0]["cross_refs"]))

    def test_build_suggest_law_context_forces_article_18_for_mask_exception_case(self):
        original_get_server_config = ai_service.get_server_config
        original_load_bundle = ai_service.load_law_bundle_chunks
        original_retrieve = ai_service._retrieve_law_context

        class DummyServerConfig:
            code = "blackberry"
            name = "BlackBerry"
            law_qa_sources = ()
            law_qa_bundle_path = "bundle.json"

        processual_chunk = ai_service._LawChunk(
            url="https://laws.example/processual",
            document_title="Процессуальный кодекс",
            article_label="Статья 29",
            text="Личный обыск при задержании.",
        )
        forced_chunk = ai_service._LawChunk(
            url="https://laws.example/admin",
            document_title="Административный кодекс",
            article_label="Статья 18",
            text=(
                "Статья 18. Ношение маски. "
                "Исключение: ношение маски допускается на территории Maze Bank Arena и иных развлекательных учреждений."
            ),
        )

        retrieval_result = type(
            "RetrievalResult",
            (),
            {
                "indexed_chunk_count": 2,
                "confidence": "high",
                "profile": "suggest",
                "bundle_health": type(
                    "BundleHealth",
                    (),
                    {"status": "ready", "generated_at": "2026-04-12T00:00:00Z", "fingerprint": "bundle-mask-force"},
                )(),
                "matches": [
                    type(
                        "Match",
                        (),
                        {
                            "score": 370,
                            "excerpt": "Личный обыск при задержании.",
                            "chunk": processual_chunk,
                        },
                    )(),
                ],
            },
        )()

        ai_service.get_server_config = lambda server_code: DummyServerConfig()
        ai_service.load_law_bundle_chunks = lambda server_code, bundle_path: [forced_chunk, processual_chunk]
        ai_service._retrieve_law_context = lambda **kwargs: retrieval_result
        try:
            context = ai_service._build_suggest_law_context(
                server_code="blackberry",
                question="статья 18 маска Maze Bank Arena задержание",
            )
        finally:
            ai_service.get_server_config = original_get_server_config
            ai_service.load_law_bundle_chunks = original_load_bundle
            ai_service._retrieve_law_context = original_retrieve

        self.assertGreaterEqual(context.selected_norms_count, 2)
        self.assertEqual(context.selected_norms[0]["article_label"], "Статья 18")
        self.assertIn("Maze Bank Arena", context.selected_norms[0]["excerpt"])

    def test_filtered_prompt_law_context_limits_grounded_norms_to_two_and_keeps_qualifiers(self):
        selected_norms = (
            {
                "source_url": "https://laws.example/admin",
                "document_title": "Административный кодекс",
                "article_label": "Статья 18",
                "excerpt": "Ношение маски на территории Maze Bank Arena подлежит оценке по статье 18.",
                "score": 96,
                "qualifiers": (
                    {
                        "kind": "exception",
                        "text": "Исключение: ношение маски допускается на территории Maze Bank Arena.",
                        "related_refs": (),
                    },
                ),
                "cross_refs": (),
            },
            {
                "source_url": "https://laws.example/advocate",
                "document_title": "Закон об адвокатуре",
                "article_label": "Статья 5",
                "excerpt": "Адвокатский запрос подлежит рассмотрению в установленном порядке.",
                "score": 88,
                "qualifiers": (
                    {
                        "kind": "note",
                        "text": "Примечание: ответ на адвокатский запрос оценивается вместе с материалами проверки.",
                        "related_refs": ("статье 33",),
                    },
                ),
                "cross_refs": ("статье 33",),
            },
            {
                "source_url": "https://laws.example/processual",
                "document_title": "Процессуальный кодекс",
                "article_label": "Статья 33",
                "excerpt": "Видеозапись процессуальных действий хранится в пределах установленного срока.",
                "score": 12,
                "qualifiers": (
                    {
                        "kind": "comment",
                        "text": "Комментарий: видеозапись относится к материалам процессуальной проверки.",
                        "related_refs": (),
                    },
                ),
                "cross_refs": (),
            },
        )
        point3_context = ai_service.build_point3_pipeline_context(
            complainant="Victim",
            organization="LSPD",
            target_person="Officer",
            event_datetime="08.04.2026 14:30",
            draft_text=(
                "Человека задержали на территории Maze Bank Arena из-за маски, после чего был направлен "
                "адвокатский запрос, а запись процессуальных действий так и не была предоставлена."
            ),
            retrieval_status="normal_context",
            retrieval_confidence="high",
            retrieved_law_context="law context",
            selected_norms=selected_norms,
        )
        prompt_law_context = ai_service._build_filtered_prompt_law_context(
            point3_context=point3_context,
            suggest_context=ai_service.SuggestContextBuildResult(
                context_text="law context",
                retrieval_confidence="high",
                retrieval_context_mode="normal_context",
                retrieval_profile="suggest",
                bundle_status="ready",
                bundle_generated_at="2026-04-12T00:00:00Z",
                bundle_fingerprint="bundle-qualifier-test",
                selected_norms_count=3,
                selected_norms=selected_norms,
            ),
            fallback_law_context="fallback",
        )

        self.assertEqual(prompt_law_context.count("Норма:"), 2)
        self.assertIn("Исключение: ношение маски допускается", prompt_law_context)
        self.assertIn("Примечание: ответ на адвокатский запрос", prompt_law_context)
        self.assertIn("supporting only", prompt_law_context)
        self.assertNotIn("Статья 33\nФрагмент", prompt_law_context)

    def test_filtered_prompt_law_context_prefers_single_primary_norm_when_secondary_is_generic_support(self):
        selected_norms = (
            {
                "source_url": "https://laws.example/admin",
                "document_title": "Административный кодекс штата Сан-Андреас",
                "article_label": "Статья 18",
                "excerpt": "Ношение маски на территории Maze Bank Arena оценивается по статье 18.",
                "score": 96,
                "qualifiers": (
                    {
                        "kind": "exception",
                        "text": "Исключение: ношение маски допускается на территории Maze Bank Arena.",
                        "related_refs": (),
                    },
                ),
                "cross_refs": (),
            },
            {
                "source_url": "https://laws.example/processual",
                "document_title": "Процессуальный кодекс штата Сан-Андреас",
                "article_label": "Статья 59",
                "excerpt": "Задержание как мера процессуального принуждения применяется при подозрении в совершении преступления.",
                "score": 78,
                "qualifiers": (),
                "cross_refs": (),
            },
        )
        point3_context = ai_service.build_point3_pipeline_context(
            complainant="Victim",
            organization="LSPD",
            target_person="Officer",
            event_datetime="08.04.2026 14:30",
            draft_text=(
                "Человека задержали на территории Maze Bank Arena из-за маски и потребовали снять её без внятного основания."
            ),
            retrieval_status="normal_context",
            retrieval_confidence="high",
            retrieved_law_context="law context",
            selected_norms=selected_norms,
        )
        prompt_law_context = ai_service._build_filtered_prompt_law_context(
            point3_context=point3_context,
            suggest_context=ai_service.SuggestContextBuildResult(
                context_text="law context",
                retrieval_confidence="high",
                retrieval_context_mode="normal_context",
                retrieval_profile="suggest",
                bundle_status="ready",
                bundle_generated_at="2026-04-12T00:00:00Z",
                bundle_fingerprint="bundle-primary-norm-test",
                selected_norms_count=2,
                selected_norms=selected_norms,
            ),
            fallback_law_context="fallback",
        )

        self.assertEqual(prompt_law_context.count("Норма:"), 1)
        self.assertIn("Статья 18", prompt_law_context)
        self.assertIn("Исключение: ношение маски допускается", prompt_law_context)
        self.assertNotIn("Статья 59", prompt_law_context)

    def test_suggest_text_retries_with_compacted_context_on_context_window_error(self):
        captured_calls: list[dict[str, object]] = []
        original = ai_service.suggest_description_with_proxy_fallback_result
        original_build_context = ai_service._build_suggest_law_context

        def fake_suggest(**kwargs):
            captured_calls.append(kwargs)
            if len(captured_calls) == 1:
                raise RuntimeError(
                    '{"error":{"message":"Your input exceeds the context window of this model.","code":"context_length_exceeded"}}'
                )
            return ai_service.TextGenerationResult(
                text="Описание фактов по жалобе.",
                usage=ai_service.AiUsageSummary(input_tokens=20, output_tokens=10, total_tokens=30),
                cache_hit=False,
                attempt_path="direct",
                attempt_duration_ms=210,
                route_policy="direct_first",
            )

        ai_service.suggest_description_with_proxy_fallback_result = fake_suggest
        ai_service._build_suggest_law_context = lambda **kwargs: ("Статья 20. " + ("текст " * 1600)).strip()
        try:
            result = ai_service.suggest_text_details(
                SuggestPayload(
                    victim_name="Victim",
                    org="LSPD",
                    subject="Officer",
                    event_dt="08.04.2026 14:30",
                    raw_desc="Draft",
                    complaint_basis="wrongful_article",
                    main_focus="procedural_violation",
                ),
                server_code="blackberry",
            )
        finally:
            ai_service.suggest_description_with_proxy_fallback_result = original
            ai_service._build_suggest_law_context = original_build_context

        self.assertEqual(result.text, "Описание фактов по жалобе.")
        self.assertEqual(len(captured_calls), 2)
        self.assertIn("suggest_context_compacted", result.warnings)
        self.assertTrue(bool(result.telemetry.get("context_compacted")))
        self.assertGreaterEqual(int(result.telemetry.get("context_compaction_level") or 0), 1)
        self.assertLess(
            len(str(captured_calls[1]["law_context"] or "")),
            len(str(captured_calls[0]["law_context"] or "")),
        )

    def test_build_suggest_law_context_marks_low_confidence_mode(self):
        original_get_server_config = ai_service.get_server_config
        original_load_bundle = ai_service.load_law_bundle_chunks
        original_select_chunks = ai_service._select_law_qa_chunks

        class DummyServerConfig:
            code = "blackberry"
            name = "BlackBerry"
            law_qa_sources = ()
            law_qa_bundle_path = "bundle.json"
            law_qa_bundle_path = "bundle.json"
            law_qa_bundle_path = "law_bundles/blackberry.json"

        ai_service.get_server_config = lambda server_code: DummyServerConfig()
        ai_service.load_law_bundle_chunks = lambda server_code, bundle_path="": (
            ai_service._LawChunk(
                url="https://laws.example/one",
                document_title="Процессуальный кодекс",
                article_label="Статья 20",
                text="Освобождение задержанного.",
            ),
        )
        ai_service._select_law_qa_chunks = lambda chunks, question: (list(chunks), "low")
        try:
            context = ai_service._build_suggest_law_context(server_code="blackberry", question="спорный запрос")
        finally:
            ai_service.get_server_config = original_get_server_config
            ai_service.load_law_bundle_chunks = original_load_bundle
            ai_service._select_law_qa_chunks = original_select_chunks

        self.assertEqual(context.retrieval_context_mode, "low_confidence_context")
        self.assertEqual(context.retrieval_confidence, "low")

    def test_retry_invalid_batch_scores_uses_mini_batch_before_single_retry(self):
        original_batch = exam_import_service.score_exam_answers_batch_with_proxy_fallback
        original_single = exam_import_service.score_exam_answer_with_proxy_fallback
        batch_calls: list[dict[str, object]] = []
        single_calls: list[str] = []

        def fake_batch(**kwargs):
            batch_calls.append(kwargs)
            return (
                {
                    "G": {"score": 91, "rationale": "Исправлено мини-батчем."},
                    "H": {"score": 1, "rationale": exam_import_service.DEFAULT_INVALID_BATCH_RATIONALE},
                    "I": {"score": 1, "rationale": exam_import_service.DEFAULT_INVALID_BATCH_RATIONALE},
                },
                {
                    "answer_count": 3,
                    "heuristic_count": 0,
                    "cache_hit_count": 0,
                    "llm_count": 3,
                    "llm_calls": 1,
                },
            )

        def fake_single(**kwargs):
            single_calls.append(str(kwargs["column"]))
            return {"score": 87, "rationale": f"Исправлено одиночной проверкой {kwargs['column']}."}

        score_items = [
            {"column": "G", "header": "QG", "user_answer": "UG", "correct_answer": "CG"},
            {"column": "H", "header": "QH", "user_answer": "UH", "correct_answer": "CH"},
            {"column": "I", "header": "QI", "user_answer": "UI", "correct_answer": "CI"},
        ]
        results = {
            "G": {"score": 1, "rationale": exam_import_service.DEFAULT_INVALID_BATCH_RATIONALE},
            "H": {"score": 1, "rationale": exam_import_service.DEFAULT_INVALID_BATCH_RATIONALE},
            "I": {"score": 1, "rationale": exam_import_service.DEFAULT_INVALID_BATCH_RATIONALE},
        }
        stats = exam_import_service._empty_scoring_stats()

        exam_import_service.score_exam_answers_batch_with_proxy_fallback = fake_batch
        exam_import_service.score_exam_answer_with_proxy_fallback = fake_single
        try:
            with self.assertLogs(exam_import_service.logger, level="WARNING") as logs:
                retried = exam_import_service.retry_invalid_batch_scores(
                    api_key="key",
                    proxy_url="",
                    source_row=42,
                    score_items=score_items,
                    results=results,
                    stats=stats,
                )
        finally:
            exam_import_service.score_exam_answers_batch_with_proxy_fallback = original_batch
            exam_import_service.score_exam_answer_with_proxy_fallback = original_single

        self.assertEqual(len(batch_calls), 1)
        self.assertEqual([item["column"] for item in batch_calls[0]["items"]], ["G", "H", "I"])
        self.assertEqual(batch_calls[0]["chunk_size"], exam_import_service.RETRY_BATCH_CHUNK_SIZE)
        self.assertEqual(batch_calls[0]["return_stats"], True)
        self.assertEqual(single_calls, ["H", "I"])
        self.assertEqual(retried["G"]["score"], 91)
        self.assertEqual(retried["H"]["score"], 87)
        self.assertEqual(retried["I"]["score"], 87)
        self.assertEqual(stats["invalid_batch_item_count"], 3)
        self.assertEqual(stats["retry_batch_items"], 3)
        self.assertEqual(stats["retry_batch_calls"], 1)
        self.assertEqual(stats["retry_single_items"], 2)
        self.assertEqual(stats["retry_single_calls"], 2)
        self.assertEqual(stats["llm_count"], 5)
        self.assertEqual(stats["llm_calls"], 3)
        joined_logs = "\n".join(logs.output)
        self.assertIn("source_row=42 column=G", joined_logs)
        self.assertIn("batch_initial > invalid_batch > retry_batch > retry_batch_resolved", joined_logs)
        self.assertIn("source_row=42 column=H", joined_logs)
        self.assertIn("retry_single > retry_single_resolved", joined_logs)

    def test_retry_invalid_batch_scores_skips_fallback_when_batch_results_are_valid(self):
        original_batch = exam_import_service.score_exam_answers_batch_with_proxy_fallback
        original_single = exam_import_service.score_exam_answer_with_proxy_fallback

        def unexpected_batch(**kwargs):
            raise AssertionError(f"mini-batch retry should not run: {kwargs}")

        def unexpected_single(**kwargs):
            raise AssertionError(f"single retry should not run: {kwargs}")

        score_items = [
            {"column": "G", "header": "QG", "user_answer": "UG", "correct_answer": "CG"},
            {"column": "H", "header": "QH", "user_answer": "UH", "correct_answer": "CH"},
        ]
        results = {
            "G": {"score": 91, "rationale": "ok"},
            "H": {"score": 77, "rationale": "ok"},
        }
        stats = exam_import_service._empty_scoring_stats()

        exam_import_service.score_exam_answers_batch_with_proxy_fallback = unexpected_batch
        exam_import_service.score_exam_answer_with_proxy_fallback = unexpected_single
        try:
            retried = exam_import_service.retry_invalid_batch_scores(
                api_key="key",
                proxy_url="",
                source_row=15,
                score_items=score_items,
                results=results,
                stats=stats,
            )
        finally:
            exam_import_service.score_exam_answers_batch_with_proxy_fallback = original_batch
            exam_import_service.score_exam_answer_with_proxy_fallback = original_single

        self.assertEqual(retried, results)
        self.assertEqual(stats["invalid_batch_item_count"], 0)
        self.assertEqual(stats["retry_batch_items"], 0)
        self.assertEqual(stats["retry_batch_calls"], 0)
        self.assertEqual(stats["retry_single_items"], 0)
        self.assertEqual(stats["retry_single_calls"], 0)
        self.assertEqual(stats["llm_count"], 0)
        self.assertEqual(stats["llm_calls"], 0)

    def test_retry_invalid_batch_scores_uses_single_retry_only_for_one_invalid_item(self):
        original_batch = exam_import_service.score_exam_answers_batch_with_proxy_fallback
        original_single = exam_import_service.score_exam_answer_with_proxy_fallback
        single_calls: list[str] = []

        def unexpected_batch(**kwargs):
            raise AssertionError(f"mini-batch retry should not run for one invalid item: {kwargs}")

        def fake_single(**kwargs):
            single_calls.append(str(kwargs["column"]))
            return {"score": 84, "rationale": "resolved singly"}

        score_items = [
            {"column": "G", "header": "QG", "user_answer": "UG", "correct_answer": "CG"},
        ]
        results = {
            "G": {"score": 1, "rationale": exam_import_service.DEFAULT_INVALID_BATCH_RATIONALE},
        }
        stats = exam_import_service._empty_scoring_stats()

        exam_import_service.score_exam_answers_batch_with_proxy_fallback = unexpected_batch
        exam_import_service.score_exam_answer_with_proxy_fallback = fake_single
        try:
            with self.assertLogs(exam_import_service.logger, level="WARNING") as logs:
                retried = exam_import_service.retry_invalid_batch_scores(
                    api_key="key",
                    proxy_url="",
                    source_row=16,
                    score_items=score_items,
                    results=results,
                    stats=stats,
                )
        finally:
            exam_import_service.score_exam_answers_batch_with_proxy_fallback = original_batch
            exam_import_service.score_exam_answer_with_proxy_fallback = original_single

        self.assertEqual(single_calls, ["G"])
        self.assertEqual(retried["G"]["score"], 84)
        self.assertEqual(stats["invalid_batch_item_count"], 1)
        self.assertEqual(stats["retry_batch_items"], 0)
        self.assertEqual(stats["retry_batch_calls"], 0)
        self.assertEqual(stats["retry_single_items"], 1)
        self.assertEqual(stats["retry_single_calls"], 1)
        self.assertEqual(stats["llm_count"], 1)
        self.assertEqual(stats["llm_calls"], 1)
        joined_logs = "\n".join(logs.output)
        self.assertIn("source_row=16 column=G", joined_logs)
        self.assertIn("batch_initial > invalid_batch > retry_single > retry_single_resolved", joined_logs)
        self.assertNotIn("retry_batch", joined_logs)

    def test_retry_invalid_batch_scores_falls_back_to_single_when_mini_batch_fails(self):
        original_batch = exam_import_service.score_exam_answers_batch_with_proxy_fallback
        original_single = exam_import_service.score_exam_answer_with_proxy_fallback
        batch_calls: list[dict[str, object]] = []
        single_calls: list[str] = []

        def failing_batch(**kwargs):
            batch_calls.append(kwargs)
            raise RuntimeError("mini-batch failed")

        def fake_single(**kwargs):
            single_calls.append(str(kwargs["column"]))
            return {"score": 79, "rationale": f"resolved singly {kwargs['column']}"}

        score_items = [
            {"column": "G", "header": "QG", "user_answer": "UG", "correct_answer": "CG"},
            {"column": "H", "header": "QH", "user_answer": "UH", "correct_answer": "CH"},
        ]
        results = {
            "G": {"score": 1, "rationale": exam_import_service.DEFAULT_INVALID_BATCH_RATIONALE},
            "H": {"score": 1, "rationale": exam_import_service.DEFAULT_INVALID_BATCH_RATIONALE},
        }
        stats = exam_import_service._empty_scoring_stats()

        exam_import_service.score_exam_answers_batch_with_proxy_fallback = failing_batch
        exam_import_service.score_exam_answer_with_proxy_fallback = fake_single
        try:
            with self.assertLogs(exam_import_service.logger, level="WARNING") as logs:
                retried = exam_import_service.retry_invalid_batch_scores(
                    api_key="key",
                    proxy_url="",
                    source_row=17,
                    score_items=score_items,
                    results=results,
                    stats=stats,
                )
        finally:
            exam_import_service.score_exam_answers_batch_with_proxy_fallback = original_batch
            exam_import_service.score_exam_answer_with_proxy_fallback = original_single

        self.assertEqual(len(batch_calls), 1)
        self.assertEqual([item["column"] for item in batch_calls[0]["items"]], ["G", "H"])
        self.assertEqual(single_calls, ["G", "H"])
        self.assertEqual(retried["G"]["score"], 79)
        self.assertEqual(retried["H"]["score"], 79)
        self.assertEqual(stats["invalid_batch_item_count"], 2)
        self.assertEqual(stats["retry_batch_items"], 0)
        self.assertEqual(stats["retry_batch_calls"], 0)
        self.assertEqual(stats["retry_single_items"], 2)
        self.assertEqual(stats["retry_single_calls"], 2)
        self.assertEqual(stats["llm_count"], 2)
        self.assertEqual(stats["llm_calls"], 2)
        joined_logs = "\n".join(logs.output)
        self.assertIn("source_row=17 column=G", joined_logs)
        self.assertIn("retry_batch_failed > retry_single > retry_single_resolved", joined_logs)

    def test_score_exam_answers_if_needed_normalizes_case_mismatched_result_columns(self):
        original_batch = exam_import_service.score_exam_answers_batch_with_proxy_fallback
        original_single = exam_import_service.score_exam_answer_with_proxy_fallback
        captured: list[dict[str, object]] = []

        def fake_batch(**kwargs):
            captured.append(kwargs)
            fake_stats = exam_import_service._empty_scoring_stats()
            fake_stats["llm_count"] = 2
            fake_stats["llm_calls"] = 1
            return (
                {
                    " g ": {"score": 91, "rationale": "Готово через batch"},
                    "h": {"score": 82, "rationale": "Case-variant key"},
                },
                fake_stats,
            )

        class FakeStore:
            def __init__(self):
                self.saved = None

            def save_exam_scores(self, source_row: int, scores: list[dict[str, object]]):
                self.saved = (source_row, list(scores))

            def get_entry(self, source_row: int):
                return entry

        score_items = [
            {
                "column": "G",
                "header": "Вопрос G",
                "user_answer": "Ответ G",
                "correct_answer": "Эталон G",
                "question": "QG",
                "exam_type": "type",
            },
            {
                "column": "H",
                "header": "Вопрос H",
                "user_answer": "Ответ H",
                "correct_answer": "Эталон H",
                "question": "QH",
                "exam_type": "type",
            },
        ]
        entry = {
            "source_row": 777,
            "payload": {"submitted": "2026-04-11", "full_name": "Student"},
            "exam_scores": [],
        }

        exam_import_service.score_exam_answers_batch_with_proxy_fallback = fake_batch
        exam_import_service.score_exam_answer_with_proxy_fallback = lambda **kwargs: {
            "score": 1,
            "rationale": "не должен быть использован",
        }
        store = FakeStore()
        try:
            did_score, stats = exam_import_service.score_exam_answers_if_needed(
                store=store,
                entry=entry,
                build_exam_score_items=lambda payload: score_items,
            )
        finally:
            exam_import_service.score_exam_answers_batch_with_proxy_fallback = original_batch
            exam_import_service.score_exam_answer_with_proxy_fallback = original_single

        self.assertTrue(did_score)
        self.assertEqual(stats["llm_count"], 2)
        self.assertEqual(len(captured), 1)
        self.assertEqual(store.saved[0], 777)
        scored = {item["column"]: item for item in store.saved[1]}
        self.assertEqual(scored["G"]["score"], 91)
        self.assertEqual(scored["H"]["score"], 82)
        self.assertEqual(scored["G"]["rationale"], "Готово через batch")
        self.assertEqual(scored["H"]["rationale"], "Case-variant key")

    def test_score_exam_answers_if_needed_uses_reference_entry_answers(self):
        original_batch = exam_import_service.score_exam_answers_batch_with_proxy_fallback
        original_single = exam_import_service.score_exam_answer_with_proxy_fallback
        captured: list[dict[str, object]] = []

        def fake_batch(**kwargs):
            captured.extend(kwargs["items"])
            return (
                {"F": {"score": 100, "rationale": "ok"}},
                exam_import_service._empty_scoring_stats(),
            )

        class FakeStore:
            def __init__(self):
                self.saved = None

            def get_reference_entry(self):
                return {
                    "source_row": 0,
                    "payload": {
                        "submitted": "",
                        "full_name": "эталонные ответы",
                        "discord": "",
                        "passport": "",
                        "format": "эталонные ответы",
                        "QF": "reference F",
                    },
                }

            def save_exam_scores(self, source_row: int, scores: list[dict[str, object]]):
                self.saved = (source_row, list(scores))

            def get_entry(self, source_row: int):
                return entry

        entry = {
            "source_row": 778,
            "full_name": "Student",
            "exam_format": "remote",
            "payload": {
                "submitted": "2026-04-11",
                "full_name": "Student",
                "discord": "disc",
                "passport": "123456",
                "format": "remote",
                "QF": "candidate F",
            },
            "exam_scores": [],
        }

        exam_import_service.score_exam_answers_batch_with_proxy_fallback = fake_batch
        exam_import_service.score_exam_answer_with_proxy_fallback = lambda **kwargs: {"score": 1, "rationale": "unused"}
        store = FakeStore()
        try:
            did_score, _ = exam_import_service.score_exam_answers_if_needed(
                store=store,
                entry=entry,
                build_exam_score_items=exam_sheet_service.build_exam_score_items,
            )
        finally:
            exam_import_service.score_exam_answers_batch_with_proxy_fallback = original_batch
            exam_import_service.score_exam_answer_with_proxy_fallback = original_single

        self.assertTrue(did_score)
        self.assertEqual(captured[0]["column"], "F")
        self.assertEqual(captured[0]["correct_answer"], "reference F")
        self.assertEqual(store.saved[0], 778)

    def test_score_exam_answers_if_needed_skips_reference_entry(self):
        class FakeStore:
            def save_exam_scores(self, source_row: int, scores: list[dict[str, object]]):
                raise AssertionError("reference entry must not be scored")

            def get_entry(self, source_row: int):
                return None

        entry = {
            "source_row": 0,
            "full_name": "эталонные ответы",
            "exam_format": "эталонные ответы",
            "payload": {
                "submitted": "",
                "full_name": "эталонные ответы",
                "discord": "",
                "passport": "",
                "format": "эталонные ответы",
                "QF": "reference F",
            },
            "exam_scores": [],
        }

        did_score, stats = exam_import_service.score_exam_answers_if_needed(
            store=FakeStore(),
            entry=entry,
            build_exam_score_items=exam_sheet_service.build_exam_score_items,
        )

        self.assertFalse(did_score)
        self.assertEqual(stats["llm_calls"], 0)

    def test_build_row_scoring_result_logs_prompt_version_meta(self):
        original_score_if_needed = exam_import_service.score_exam_answers_if_needed

        class FakeStore:
            def get_entry(self, source_row: int):
                return {
                    "source_row": source_row,
                    "payload": {},
                    "exam_scores": [
                        {
                            "column": "G",
                            "header": "Question G",
                            "user_answer": "Answer",
                            "correct_answer": "Reference",
                            "score": 88,
                            "rationale": "ok",
                        }
                    ],
                }

        class FakeMetricsStore:
            def __init__(self):
                self.events: list[dict[str, object]] = []

            def log_event(self, **kwargs):
                self.events.append(kwargs)

        def fake_score(store, entry, *, build_exam_score_items, force_rescore=False):
            _ = store, entry, build_exam_score_items, force_rescore
            stats = exam_import_service._empty_scoring_stats()
            stats["llm_count"] = 1
            stats["prompt_mode"] = "compact"
            stats["prompt_version"] = "exam_batch_scoring.compact.v8"
            stats["single_prompt_version"] = "exam_scoring.compact.v8"
            return True, stats

        exam_import_service.score_exam_answers_if_needed = fake_score
        try:
            metrics_store = FakeMetricsStore()
            result = exam_import_service.build_row_scoring_result(
                source_row=7,
                user=AuthUser(username="tester"),
                store=FakeStore(),
                metrics_store=metrics_store,
                build_exam_score_items=lambda payload: [],
            )
        finally:
            exam_import_service.score_exam_answers_if_needed = original_score_if_needed

        self.assertEqual(result["source_row"], 7)
        self.assertEqual(len(metrics_store.events), 1)
        meta = metrics_store.events[0]["meta"]
        self.assertEqual(meta["prompt_mode"], "compact")
        self.assertEqual(meta["prompt_version"], "exam_batch_scoring.compact.v8")
        self.assertEqual(meta["single_prompt_version"], "exam_scoring.compact.v8")

    def test_clean_suggest_text_unwraps_code_blocks_and_drops_sources_tail(self):
        raw = """```text
Описание фактов по жалобе.

Указан ключевой эпизод задержания.
```

Источники:
https://laws.example/article
"""
        cleaned = ai_service._clean_suggest_text(raw)
        self.assertIn("Описание фактов по жалобе.", cleaned)
        self.assertIn("Указан ключевой эпизод задержания.", cleaned)
        self.assertNotIn("```", cleaned)
        self.assertNotIn("Источники", cleaned)
        self.assertNotIn("https://laws.example/article", cleaned)

    def test_ai_service_extract_principal_scan_rejects_bad_model_payload(self):
        original = ai_service.extract_principal_fields_with_proxy_fallback
        ai_service.extract_principal_fields_with_proxy_fallback = lambda **kwargs: {"principal_phone": "123"}
        try:
            with self.assertRaises(HTTPException) as ctx:
                ai_service.extract_principal_scan(PrincipalScanPayload(image_data_url="data:image/png;base64,AAAA"))
        finally:
            ai_service.extract_principal_fields_with_proxy_fallback = original
        self.assertEqual(ctx.exception.status_code, 502)

    def test_ai_service_law_qa_rejects_unknown_server(self):
        with self.assertRaises(Exception):
            ai_service.answer_law_question(
                LawQaPayload(
                    server_code="missing-server",
                    question="test question",
                    max_answer_chars=2000,
                )
            )

    def test_ai_service_law_qa_requires_configured_sources(self):
        original = ai_service.get_server_config

        class DummyServerConfig:
            code = "blackberry"
            name = "BlackBerry"
            law_qa_sources = ()

        ai_service.get_server_config = lambda server_code: DummyServerConfig()
        try:
            with self.assertRaises(HTTPException) as ctx:
                ai_service.answer_law_question(
                    LawQaPayload(
                        server_code="blackberry",
                        question="test question",
                        max_answer_chars=2000,
                    )
                )
        finally:
            ai_service.get_server_config = original

        self.assertEqual(ctx.exception.status_code, 400)

    def test_law_html_parser_skips_script_content(self):
        parser = ai_service._LawHtmlParser()
        parser.feed("<html><body><h1>Кодекс</h1><script>XF.ready(() => bad())</script><p>Статья 1 действует.</p></body></html>")
        self.assertIn("Кодекс", parser.text)
        self.assertIn("Статья 1 действует.", parser.text)
        self.assertNotIn("XF.ready", parser.text)

    def test_clean_law_document_text_removes_xenforo_bootstrap_noise(self):
        raw = "Важно - Кодекс XF.ready(() => { XF.extendObject(true, XF.config, { cookie: { path: '/' } }) short_date_x_minutes: '{minutes}m' }) Статья 5. Право на защиту."
        cleaned = ai_service._clean_law_document_text(raw)
        self.assertIn("Важно - Кодекс", cleaned)
        self.assertIn("Статья 5. Право на защиту.", cleaned)
        self.assertNotIn("XF.ready", cleaned)
        self.assertNotIn("short_date_x_minutes", cleaned)

    def test_law_qa_ignores_unsupported_model_and_uses_default(self):
        self.assertEqual(ai_service.resolve_law_qa_model("unsupported-model"), ai_service.get_default_law_qa_model())

    def test_law_qa_uses_default_model(self):
        original_get_server_config = ai_service.get_server_config
        original_build_index = ai_service._build_law_chunk_index_cached
        original_create_client = ai_service.create_openai_client

        class DummyServerConfig:
            code = "blackberry"
            name = "BlackBerry"
            law_qa_sources = ("https://laws.example/base",)

        captured = {}

        class DummyResponses:
            def create(self, **kwargs):
                captured.update(kwargs)
                return type("DummyResponse", (), {"output_text": "Ответ по закону."})()

        class DummyClient:
            responses = DummyResponses()

        ai_service.get_server_config = lambda server_code: DummyServerConfig()
        ai_service._build_law_chunk_index_cached = lambda source_urls: (
            ai_service._LawChunk(
                url="https://laws.example/base",
                document_title="Процессуальный кодекс",
                article_label="Статья 1. Право на защиту",
                text="Статья 1. Право на защиту. Каждый имеет право на защиту.",
            ),
        )
        ai_service.create_openai_client = lambda **kwargs: DummyClient()
        try:
            text, sources, count = ai_service.answer_law_question(
                LawQaPayload(
                    server_code="blackberry",
                    model="gpt-5.4",
                    question="Какая статья дает право на защиту?",
                    max_answer_chars=2000,
                )
            )
        finally:
            ai_service.get_server_config = original_get_server_config
            ai_service._build_law_chunk_index_cached = original_build_index
            ai_service.create_openai_client = original_create_client

        self.assertEqual(text, "Ответ по закону.")
        self.assertEqual(sources, ["https://laws.example/base"])
        self.assertEqual(count, 1)
        self.assertEqual(captured["model"], ai_service.get_default_law_qa_model())
        self.assertIn("Не используй реальные законы", captured["input"])
        self.assertIn("Право на защиту", captured["input"])

    def test_law_qa_details_include_retrieval_debug(self):
        original_get_server_config = ai_service.get_server_config
        original_build_index = ai_service._build_law_chunk_index_cached
        original_create_client = ai_service.create_openai_client

        class DummyServerConfig:
            code = "blackberry"
            name = "BlackBerry"
            law_qa_sources = ("https://laws.example/base",)

        class DummyResponses:
            def create(self, **kwargs):
                return type("DummyResponse", (), {"output_text": "Ответ по закону."})()

        class DummyClient:
            responses = DummyResponses()

        ai_service.get_server_config = lambda server_code: DummyServerConfig()
        ai_service._build_law_chunk_index_cached = lambda source_urls: (
            ai_service._LawChunk(
                url="https://laws.example/base",
                document_title="Процессуальный кодекс",
                article_label="Статья 20",
                text="Статья 20. Основания освобождения задержанного.",
            ),
        )
        ai_service.create_openai_client = lambda **kwargs: DummyClient()
        try:
            result = ai_service.answer_law_question_details(
                LawQaPayload(
                    server_code="blackberry",
                    model="gpt-5.4",
                    question="Когда обязаны освободить задержанного?",
                    max_answer_chars=2000,
                )
            )
        finally:
            ai_service.get_server_config = original_get_server_config
            ai_service._build_law_chunk_index_cached = original_build_index
            ai_service.create_openai_client = original_create_client

        self.assertEqual(result.text, "Ответ по закону.")
        self.assertEqual(result.retrieval_profile, "law_qa")
        self.assertTrue(result.retrieval_confidence)
        self.assertEqual(result.selected_norms[0]["article_label"], "Статья 20")
        self.assertEqual(result.selected_norms[0]["source_url"], "https://laws.example/base")

    def test_law_qa_retries_when_model_returns_empty_text_once(self):
        original_get_server_config = ai_service.get_server_config
        original_build_index = ai_service._build_law_chunk_index_cached
        original_create_client = ai_service.create_openai_client

        class DummyServerConfig:
            code = "blackberry"
            name = "BlackBerry"
            law_qa_sources = ("https://laws.example/base",)

        class DummyResponses:
            def __init__(self):
                self.calls = 0

            def create(self, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    return type(
                        "EmptyResponse",
                        (),
                        {
                            "output_text": "",
                            "status": "completed",
                            "output": [
                                type(
                                    "OutputItem",
                                    (),
                                    {
                                        "type": "message",
                                        "content": [type("ContentItem", (), {"type": "reasoning", "text": ""})()],
                                    },
                                )()
                            ],
                        },
                    )()
                return type("GoodResponse", (), {"output_text": "Найденный ответ"})()

        class DummyClient:
            def __init__(self):
                self.responses = DummyResponses()

        dummy_client = DummyClient()
        ai_service.get_server_config = lambda server_code: DummyServerConfig()
        ai_service._build_law_chunk_index_cached = lambda source_urls: (
            ai_service._LawChunk(
                url="https://laws.example/base",
                document_title="Процессуальный кодекс",
                article_label="Статья 20. Основания освобождения",
                text="Статья 20. Основания освобождения задержанного.",
            ),
        )
        ai_service.create_openai_client = lambda **kwargs: dummy_client
        try:
            text, sources, count = ai_service.answer_law_question(
                LawQaPayload(
                    server_code="blackberry",
                    model="gpt-5-mini",
                    question="Когда задержанного обязаны отпустить?",
                    max_answer_chars=2000,
                )
            )
        finally:
            ai_service.get_server_config = original_get_server_config
            ai_service._build_law_chunk_index_cached = original_build_index
            ai_service.create_openai_client = original_create_client

        self.assertEqual(text, "Найденный ответ")
        self.assertEqual(sources, ["https://laws.example/base"])
        self.assertEqual(count, 1)
        self.assertEqual(dummy_client.responses.calls, 2)

    def test_law_qa_retries_with_compacted_context_on_context_window_error(self):
        original_get_server_config = ai_service.get_server_config
        original_build_index = ai_service._build_law_chunk_index_cached
        original_create_client = ai_service.create_openai_client

        class DummyServerConfig:
            code = "blackberry"
            name = "BlackBerry"
            law_qa_sources = ("https://laws.example/base",)

        class DummyResponses:
            def __init__(self):
                self.calls = 0
                self.prompt_lengths: list[int] = []

            def create(self, **kwargs):
                self.calls += 1
                self.prompt_lengths.append(len(str(kwargs.get("input") or "")))
                if self.calls == 1:
                    raise RuntimeError(
                        '{"error":{"message":"Your input exceeds the context window of this model.","code":"context_length_exceeded"}}'
                    )
                return type("GoodResponse", (), {"output_text": "Ответ после сжатия контекста"})()

        class DummyClient:
            def __init__(self):
                self.responses = DummyResponses()

        dummy_client = DummyClient()
        ai_service.get_server_config = lambda server_code: DummyServerConfig()
        ai_service._build_law_chunk_index_cached = lambda source_urls: (
            ai_service._LawChunk(
                url="https://laws.example/base",
                document_title="Процессуальный кодекс",
                article_label="Статья 20",
                text=("Основания освобождения задержанного. " * 220).strip(),
            ),
        )
        ai_service.create_openai_client = lambda **kwargs: dummy_client
        try:
            result = ai_service.answer_law_question_details(
                LawQaPayload(
                    server_code="blackberry",
                    model="gpt-5-mini",
                    question="Когда обязаны освободить задержанного?",
                    max_answer_chars=2000,
                )
            )
        finally:
            ai_service.get_server_config = original_get_server_config
            ai_service._build_law_chunk_index_cached = original_build_index
            ai_service.create_openai_client = original_create_client

        self.assertEqual(result.text, "Ответ после сжатия контекста")
        self.assertGreaterEqual(dummy_client.responses.calls, 2)
        self.assertIn("law_qa_context_compacted", result.warnings)
        self.assertTrue(bool(result.telemetry.get("context_compacted")))
        self.assertGreaterEqual(int(result.telemetry.get("context_compaction_level") or 0), 1)

    def test_law_qa_prefers_structured_bundle_before_html_fetch(self):
        original_get_server_config = ai_service.get_server_config
        original_load_bundle = ai_service.load_law_bundle_chunks
        original_build_index = ai_service._build_law_chunk_index_cached
        original_create_client = ai_service.create_openai_client

        class DummyServerConfig:
            code = "blackberry"
            name = "BlackBerry"
            law_qa_sources = ("https://laws.example/fallback",)
            law_qa_bundle_path = "law_bundles/blackberry.json"

        class DummyResponses:
            def create(self, **kwargs):
                return type("DummyResponse", (), {"output_text": "Ответ из bundle"})()

        class DummyClient:
            responses = DummyResponses()

        ai_service.get_server_config = lambda server_code: DummyServerConfig()
        ai_service.load_law_bundle_chunks = lambda server_code, bundle_path="": (
            ai_service._LawChunk(
                url="https://laws.example/bundle",
                document_title="Уголовный кодекс",
                article_label="Статья 23. Необходимая оборона",
                text="Статья 23. Необходимая оборона. Текст нормы.",
            ),
        )

        def fail_if_html_fetch(source_urls):
            raise AssertionError(f"html fallback should not be used: {source_urls}")

        ai_service._build_law_chunk_index_cached = fail_if_html_fetch
        ai_service.create_openai_client = lambda **kwargs: DummyClient()
        try:
            text, sources, count = ai_service.answer_law_question(
                LawQaPayload(
                    server_code="blackberry",
                    model="gpt-5.4",
                    question="Какие обстоятельства исключают преступность деяния?",
                    max_answer_chars=2000,
                )
            )
        finally:
            ai_service.get_server_config = original_get_server_config
            ai_service.load_law_bundle_chunks = original_load_bundle
            ai_service._build_law_chunk_index_cached = original_build_index
            ai_service.create_openai_client = original_create_client

        self.assertEqual(text, "Ответ из bundle")
        self.assertEqual(sources, ["https://laws.example/bundle"])
        self.assertEqual(count, 1)

    def test_split_law_document_into_chunks_extracts_articles(self):
        chunks = ai_service._split_law_document_into_chunks(
            {
                "url": "https://laws.example/processual",
                "text": (
                    "Процессуальный кодекс штата. "
                    "Статья 19. Основания задержания. Текст статьи 19. "
                    "Статья 20. Основания для освобождения задержанного. Текст статьи 20. "
                    "Статья 21. Следующая норма. Текст статьи 21."
                ),
            }
        )

        self.assertGreaterEqual(len(chunks), 3)
        self.assertIn("Статья 20", chunks[1].article_label)
        self.assertIn("освобождения задержанного", chunks[1].text.lower())

    def test_law_qa_prefers_relevant_article_chunk_for_periphrased_query(self):
        question = "Когда задержанного обязаны отпустить?"
        relevant_chunk = ai_service._LawChunk(
            url="https://laws.example/processual",
            document_title="Процессуальный кодекс",
            article_label="Статья 20. Основания для освобождения задержанного",
            text="Статья 20. Основания для освобождения задержанного. Задержанный подлежит освобождению при отсутствии оснований для дальнейшего удержания.",
        )
        unrelated_chunk = ai_service._LawChunk(
            url="https://laws.example/criminal",
            document_title="Уголовный кодекс",
            article_label="Статья 5. Общие положения",
            text="Статья 5. Общие положения уголовной ответственности.",
        )

        relevant_score = ai_service._score_law_chunk(relevant_chunk, question)
        unrelated_score = ai_service._score_law_chunk(unrelated_chunk, question)

        self.assertGreater(relevant_score, unrelated_score)
        self.assertGreater(relevant_score, 0)

    def test_law_qa_handles_typo_and_paraphrase_in_release_question(self):
        question = "когда человека надо отпусить после задержания"
        relevant_chunk = ai_service._LawChunk(
            url="https://laws.example/processual",
            document_title="Процессуальный кодекс",
            article_label="Статья 20. Основания для освобождения задержанного",
            text="Статья 20. Основания для освобождения задержанного. Задержанный подлежит освобождению при отсутствии оснований для дальнейшего удержания.",
        )
        unrelated_chunk = ai_service._LawChunk(
            url="https://laws.example/admin",
            document_title="Административный кодекс",
            article_label="Статья 10. Общие положения",
            text="Статья 10. Общие положения административного права.",
        )

        relevant_score = ai_service._score_law_chunk(relevant_chunk, question)
        unrelated_score = ai_service._score_law_chunk(unrelated_chunk, question)

        self.assertGreater(relevant_score, unrelated_score)
        self.assertGreater(relevant_score, 0)

    def test_law_qa_expands_short_uk_question_into_criminal_code_terms(self):
        terms = ai_service._expand_question_terms("что не считается преступлением по ук")
        self.assertIn("уголовный", terms)
        self.assertIn("кодекс", terms)
        self.assertIn("преступность", terms)

    def test_law_qa_prefers_bail_article_for_multi_article_bail_question(self):
        question = "как считается залог по нескольким административным статьям"
        relevant_chunk = ai_service._LawChunk(
            url="https://laws.example/admin",
            document_title="Административный кодекс",
            article_label="Статья 14. Освобождение под залог",
            text="Статья 14. Освобождение под залог. Сумма залога устанавливается по санкции инкриминируемой статьи.",
        )
        unrelated_chunk = ai_service._LawChunk(
            url="https://laws.example/criminal",
            document_title="Уголовный кодекс",
            article_label="Статья 23. Необходимая оборона",
            text="Статья 23. Необходимая оборона.",
        )

        relevant_score = ai_service._score_law_chunk(relevant_chunk, question)
        unrelated_score = ai_service._score_law_chunk(unrelated_chunk, question)

        self.assertGreater(relevant_score, unrelated_score)
        self.assertGreater(relevant_score, 0)

    def test_law_qa_selects_criminal_code_context_for_short_uk_question(self):
        chunks = [
            ai_service._LawChunk(
                url="https://laws.example/criminal",
                document_title="Уголовный кодекс",
                article_label="Статья 23. Необходимая оборона",
                text="Статья 23. Необходимая оборона. Обстоятельство, исключающее преступность деяния.",
            ),
            ai_service._LawChunk(
                url="https://laws.example/processual",
                document_title="Процессуальный кодекс",
                article_label="Статья 20. Основания освобождения",
                text="Статья 20. Основания для освобождения задержанного.",
            ),
        ]
        selected, confidence = ai_service._select_law_qa_chunks(chunks, "что не считается преступлением по ук")

        self.assertIn(confidence, {"medium", "high"})
        self.assertIn("Уголовный кодекс", selected[0].document_title)

    def test_law_qa_prompt_warns_about_false_premise_on_low_confidence(self):
        prompt = ai_service._build_law_qa_prompt(
            server_name="BlackBerry",
            server_code="blackberry",
            model_name="gpt-5.4",
            question="Можно ли придумать норму без статьи?",
            max_answer_chars=2000,
            context_blocks=["[Источник: https://laws.example]\n[Документ: Кодекс]\n[Норма: Статья 1]\nТекст"],
            retrieval_confidence="low",
        )
        self.assertIn("неверную предпосылку", prompt)
        self.assertIn("опечатками", prompt)
        self.assertIn("Уверенность в подборе норм низкая", prompt)

    def test_normalize_ai_feedback_issues_maps_aliases_to_stable_codes(self):
        issues = ai_service.normalize_ai_feedback_issues(["wronglaw", "fact", "unknown-custom"])

        self.assertEqual(issues, ("wrong_law", "wrong_fact", "other"))

    def test_extract_relevant_law_excerpt_uses_hit_window_not_only_document_start(self):
        text = (
            "intro " * 300
            + "Article 20. Grounds for release of a detainee: the detainee must be released when there are no grounds to continue detention. "
            + "tail " * 100
        )
        excerpt = ai_service._extract_relevant_law_excerpt(
            text,
            "grounds for release of a detainee",
            max_chars=500,
        )
        self.assertIn("Article 20", excerpt)
        self.assertIn("Grounds for release of a detainee", excerpt)

    def test_build_suggest_law_context_prioritizes_processual_code_over_judicial_system_law(self):
        original_get_server_config = ai_service.get_server_config
        original_load_bundle = ai_service.load_law_bundle_chunks
        original_select_chunks = ai_service._select_law_qa_chunks

        class DummyServerConfig:
            code = "blackberry"
            name = "BlackBerry"
            law_qa_sources = ()
            law_qa_bundle_path = "bundle.json"

        processual_chunk = ai_service._LawChunk(
            url="https://laws.example/processual",
            document_title="Важно - Процессуальный кодекс штата Сан-Андреас",
            article_label="Статья 17",
            text="Порядок задержания и реализация прав задержанного.",
        )
        judicial_chunk = ai_service._LawChunk(
            url="https://laws.example/judicial",
            document_title='Важно - Закон "О судебной системе и судопроизводстве"',
            article_label="Статья 2",
            text="Представитель истца может действовать при наличии договора.",
        )

        ai_service.get_server_config = lambda server_code: DummyServerConfig()
        ai_service.load_law_bundle_chunks = lambda server_code, bundle_path: [processual_chunk, judicial_chunk]
        ai_service._select_law_qa_chunks = lambda chunks, question, profile="suggest": (list(chunks), "high")
        try:
            context = ai_service._build_suggest_law_context(
                server_code="blackberry",
                question="FIB Pavel Clayton задержали за оскорбление, адвокатский запрос, запись не поступила",
            )
        finally:
            ai_service.get_server_config = original_get_server_config
            ai_service.load_law_bundle_chunks = original_load_bundle
            ai_service._select_law_qa_chunks = original_select_chunks

        self.assertGreaterEqual(context.selected_norms_count, 1)
        self.assertIn("Процессуальный кодекс", context.selected_norms[0]["document_title"])
        self.assertNotIn("судопроизводстве", context.selected_norms[0]["document_title"].lower())

if __name__ == "__main__":
    unittest.main()

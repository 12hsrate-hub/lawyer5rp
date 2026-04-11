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
from ogp_web.services import ai_service, auth_service, complaint_service, email_service, exam_sheet_service
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
        original = ai_service.suggest_description_with_proxy_fallback
        ai_service.suggest_description_with_proxy_fallback = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("timeout"))
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
            ai_service.suggest_description_with_proxy_fallback = original
        self.assertEqual(ctx.exception.status_code, 500)

    def test_ai_service_suggest_text_passes_optional_focus_fields(self):
        captured: dict[str, str] = {}
        original = ai_service.suggest_description_with_proxy_fallback

        def fake_suggest(**kwargs):
            captured.update(kwargs)
            return "ok"

        ai_service.suggest_description_with_proxy_fallback = fake_suggest
        try:
            text = ai_service.suggest_text(
                SuggestPayload(
                    victim_name="Victim",
                    org="LSPD",
                    subject="Officer",
                    event_dt="08.04.2026 14:30",
                    raw_desc="Draft",
                    complaint_basis="wrongful_article",
                    main_focus="Спорная квалификация",
                )
            )
        finally:
            ai_service.suggest_description_with_proxy_fallback = original

        self.assertEqual(text, "ok")
        self.assertEqual(captured["complaint_basis"], "wrongful_article")
        self.assertEqual(captured["main_focus"], "Спорная квалификация")

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

    def test_law_qa_rejects_unsupported_model(self):
        with self.assertRaises(HTTPException) as ctx:
            ai_service.resolve_law_qa_model("unsupported-model")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_law_qa_uses_selected_model(self):
        original_get_server_config = ai_service.get_server_config
        original_fetch_documents = ai_service._fetch_law_documents
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
        ai_service._fetch_law_documents = lambda source_urls: [{"url": "https://laws.example/base", "text": "Статья 1. Право на защиту."}]
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
            ai_service._fetch_law_documents = original_fetch_documents
            ai_service.create_openai_client = original_create_client

        self.assertEqual(text, "Ответ по закону.")
        self.assertEqual(sources, ["https://laws.example/base"])
        self.assertEqual(count, 1)
        self.assertEqual(captured["model"], "gpt-5.4")
        self.assertIn("Не добавляй никакие реальные законы", captured["input"])


if __name__ == "__main__":
    unittest.main()

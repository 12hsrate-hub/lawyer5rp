from __future__ import annotations

import ast
import os
import unittest
from pathlib import Path

from shared import ogp_ai
from shared.ogp_ai_prompts import (
    EXAM_BATCH_SCORING_PROMPT_VERSION,
    EXAM_SCORING_PROMPT_VERSION,
    PRINCIPAL_SCAN_PROMPT_VERSION,
    SUGGEST_PROMPT_VERSION,
    build_batch_exam_scoring_prompt_spec,
    build_exam_scoring_prompt,
    build_exam_scoring_prompt_spec,
    build_principal_scan_prompt,
    build_principal_scan_prompt_spec,
    build_suggest_prompt,
    build_suggest_prompt_spec,
)
from tests.temp_helpers import make_temporary_directory


class SharedAiTests(unittest.TestCase):
    def test_proxy_fallback_tries_proxy_after_direct_failure(self):
        calls: list[str] = []
        original_create = ogp_ai.create_openai_client
        original_suggest = ogp_ai.suggest_description

        class FakeClient:
            def __init__(self, proxy_url: str):
                self.proxy_url = proxy_url

        def fake_create(api_key: str, proxy_url: str = ""):
            calls.append(proxy_url or "direct")
            if not proxy_url:
                raise RuntimeError("direct failed")
            return FakeClient(proxy_url)

        def fake_suggest(client, **kwargs):
            _ = client, kwargs
            return "ok via proxy"

        ogp_ai.create_openai_client = fake_create
        ogp_ai.suggest_description = fake_suggest
        try:
            text = ogp_ai.suggest_description_with_proxy_fallback(
                api_key="key",
                proxy_url="http://proxy:1",
                victim_name="Victim",
                org="Org",
                subject="Subject",
                event_dt="08.04.2026 14:30",
                raw_desc="Draft",
                complaint_basis="wrongful_article",
                main_focus="Спорная квалификация",
            )
        finally:
            ogp_ai.create_openai_client = original_create
            ogp_ai.suggest_description = original_suggest

        self.assertEqual(text, "ok via proxy")
        self.assertEqual(calls, ["direct", "http://proxy:1"])

    def test_ocr_proxy_fallback_tries_proxy_after_direct_failure(self):
        calls: list[str] = []
        original_create = ogp_ai.create_openai_client
        original_extract = ogp_ai.extract_principal_fields

        class FakeClient:
            def __init__(self, proxy_url: str):
                self.proxy_url = proxy_url

        def fake_create(api_key: str, proxy_url: str = ""):
            calls.append(proxy_url or "direct")
            if not proxy_url:
                raise RuntimeError("direct failed")
            return FakeClient(proxy_url)

        def fake_extract(client, *, image_data_url: str):
            _ = client, image_data_url
            return {"principal_name": "John Doe"}

        ogp_ai.create_openai_client = fake_create
        ogp_ai.extract_principal_fields = fake_extract
        try:
            payload = ogp_ai.extract_principal_fields_with_proxy_fallback(
                api_key="key",
                proxy_url="http://proxy:1",
                image_data_url="data:image/png;base64,AAAA",
            )
        finally:
            ogp_ai.create_openai_client = original_create
            ogp_ai.extract_principal_fields = original_extract

        self.assertEqual(payload["principal_name"], "John Doe")
        self.assertEqual(calls, ["direct", "http://proxy:1"])

    def test_exam_scoring_returns_100_for_exact_match_without_model_call(self):
        class DummyClient:
            def __init__(self):
                self.responses = self

            def create(self, **kwargs):
                raise AssertionError(f"model should not be called: {kwargs}")

        payload = ogp_ai.score_exam_answer(
            DummyClient(),
            user_answer="Совпадающий ответ",
            correct_answer="Совпадающий ответ",
        )

        self.assertEqual(payload["score"], 100)

    def test_exam_scoring_batch_returns_exact_match_without_model_call(self):
        class DummyClient:
            def __init__(self):
                self.responses = self

            def create(self, **kwargs):
                raise AssertionError(f"model should not be called: {kwargs}")

        original_create = ogp_ai.create_openai_client
        ogp_ai.create_openai_client = lambda api_key, proxy_url="": DummyClient()
        try:
            payload = ogp_ai.score_exam_answers_batch_with_proxy_fallback(
                api_key="key",
                proxy_url="",
                items=[
                    {
                        "column": "G",
                        "header": "question",
                        "user_answer": "Совпадающий ответ",
                        "correct_answer": "Совпадающий ответ",
                    }
                ],
            )
        finally:
            ogp_ai.create_openai_client = original_create

        self.assertEqual(payload["G"]["score"], 100)

    def test_exam_scoring_batch_can_return_stats(self):
        class DummyClient:
            def __init__(self):
                self.responses = self

            def create(self, **kwargs):
                return type("Response", (), {"output_text": '{"H": {"score": 77, "rationale": "ok"}}'})()

        original_create = ogp_ai.create_openai_client
        ogp_ai.create_openai_client = lambda api_key, proxy_url="": DummyClient()
        try:
            payload, stats = ogp_ai.score_exam_answers_batch_with_proxy_fallback(
                api_key="key",
                proxy_url="",
                items=[
                    {
                        "column": "G",
                        "header": "question G",
                        "user_answer": "Совпадающий ответ",
                        "correct_answer": "Совпадающий ответ",
                    },
                    {
                        "column": "H",
                        "header": "question H",
                        "user_answer": "alpha beta gamma",
                        "correct_answer": "delta epsilon zeta",
                    },
                ],
                return_stats=True,
            )
        finally:
            ogp_ai.create_openai_client = original_create

        self.assertEqual(payload["G"]["score"], 100)
        self.assertEqual(payload["H"]["score"], 77)
        self.assertEqual(stats["answer_count"], 2)
        self.assertEqual(stats["heuristic_count"], 1)
        self.assertEqual(stats["llm_count"], 1)
        self.assertEqual(stats["llm_calls"], 1)

    def test_extract_response_text_ignores_empty_reasoning_placeholder(self):
        response = type(
            "Response",
            (),
            {
                "output_text": "Reasoning\nEmpty reasoning item",
                "output": [
                    type(
                        "OutputItem",
                        (),
                        {
                            "type": "message",
                            "content": [
                                type("ContentItem", (), {"type": "reasoning", "text": ""})(),
                                type("ContentItem", (), {"type": "output_text", "text": "Нормальный ответ"})(),
                            ],
                        },
                    )()
                ],
            },
        )()

        self.assertEqual(ogp_ai.extract_response_text(response), "Нормальный ответ")

    def test_suggest_description_uses_cache_when_enabled(self):
        tmpdir = make_temporary_directory()
        previous_enabled = os.environ.get("OGP_AI_CACHE_ENABLED")
        previous_dir = os.environ.get("OGP_AI_CACHE_DIR")
        os.environ["OGP_AI_CACHE_ENABLED"] = "1"
        os.environ["OGP_AI_CACHE_DIR"] = tmpdir.name

        class DummyResponse:
            output_text = "cached text"

        class DummyClient:
            def __init__(self):
                self.calls = 0
                self.responses = self

            def create(self, **kwargs):
                self.calls += 1
                return DummyResponse()

        client = DummyClient()
        try:
            first = ogp_ai.suggest_description(
                client,
                victim_name="Victim",
                org="Org",
                subject="Subject",
                event_dt="08.04.2026 14:30",
                raw_desc="Draft",
                complaint_basis="wrongful_article",
                main_focus="Спорная квалификация",
            )
            second = ogp_ai.suggest_description(
                client,
                victim_name="Victim",
                org="Org",
                subject="Subject",
                event_dt="08.04.2026 14:30",
                raw_desc="Draft",
                complaint_basis="wrongful_article",
                main_focus="Спорная квалификация",
            )
        finally:
            if previous_enabled is None:
                os.environ.pop("OGP_AI_CACHE_ENABLED", None)
            else:
                os.environ["OGP_AI_CACHE_ENABLED"] = previous_enabled
            if previous_dir is None:
                os.environ.pop("OGP_AI_CACHE_DIR", None)
            else:
                os.environ["OGP_AI_CACHE_DIR"] = previous_dir
            tmpdir.cleanup()

        self.assertEqual(first, "cached text")
        self.assertEqual(second, "cached text")
        self.assertEqual(client.calls, 1)

    def test_suggest_prompt_requires_only_selected_basis_sections(self):
        prompt = build_suggest_prompt(
            victim_name="Victim",
            org="LSPD",
            subject="John Doe",
            event_dt="08.04.2026 14:30",
            raw_desc="Draft",
            complaint_basis="wrongful_article",
            main_focus="Спорная квалификация",
        )
        self.assertIn("[priority]", prompt)
        self.assertIn("[quality_check]", prompt)
        self.assertIn("[focus_input]", prompt)
        self.assertIn("[allowed_sources]", prompt)
        self.assertIn("[article_anchors]", prompt)
        self.assertIn("[basis_strategy]", prompt)
        self.assertIn("wrongful_article", prompt)
        self.assertIn("Спорная квалификация", prompt)
        self.assertIn("Тактика усиления для wrongful_article", prompt)
        self.assertIn("ст. 17 ч. 3-5", prompt)
        self.assertIn('ст. 18 ч. 1 п. "в"', prompt)
        self.assertIn('ст. 23 ч. 1 п. "б"-"в" Процессуального кодекса штата Сан-Андреас', prompt)
        self.assertIn("ст. 11-14 Процессуального кодекса штата Сан-Андреас", prompt)
        self.assertIn("ст. 71 ч. 1 Уголовного кодекса штата Сан-Андреас", prompt)
        self.assertIn("ст. 71.1 Уголовного кодекса штата Сан-Андреас", prompt)
        self.assertIn("Процессуального кодекса штата Сан-Андреас", prompt)
        self.assertIn("FC513 S.A.", prompt)
        self.assertIn("SC279-H S.A.", prompt)
        self.assertNotIn("Тактика усиления для no_materials_by_request", prompt)
        self.assertNotIn("Тактика усиления для no_video_or_no_evidence", prompt)
        self.assertIn("processualnyi-kodeks-shtata-san-andreas-redakcija-ot-29-marta-2026-goda.826899", prompt)
        self.assertIn("sudebnye-precedenty.1291064/", prompt)
        self.assertIn("dorozhnyi-kodeks-shtata-san-andreas-redakcija-ot-29-marta-2025-goda.826974", prompt)
        self.assertIn("administrativnyi-kodeks-shtata-san-andreas-redakcija-ot-29-marta-2025-goda.827016", prompt)
        self.assertIn("ugolovnyi-kodeks-shtata-san-andreas-redakcija-ot-29-marta-2026-goda.826988", prompt)
        self.assertIn("ehticheskii-kodeks-shtata-san-andreas-redakcija-ot-19-oktjabrja-2024-goda.826971", prompt)
        self.assertIn("konstitucija-shtata-san-andreas-redakcija-ot-29-marta-2026-goda.826866", prompt)
        self.assertIn("zakon-ob-advokature-i-advokatskoi-dejatelnosti", prompt)
        self.assertNotIn("sudebnye-precedenty.1291064/post-8971554", prompt)
        self.assertNotIn("zakonodatelnaja-baza.262", prompt)

    def test_suggest_prompt_contains_basis_specific_materials_strategy(self):
        prompt = build_suggest_prompt(
            victim_name="Victim",
            org="LSPD",
            subject="John Doe",
            event_dt="08.04.2026 14:30",
            raw_desc="Draft",
            complaint_basis="no_materials_by_request",
            main_focus="Не предоставили видео по запросу адвоката",
        )
        self.assertIn("адвокатскому запросу", prompt)
        self.assertIn("Тактика усиления для no_materials_by_request", prompt)
        self.assertIn("какие материалы были истребованы", prompt)
        self.assertIn("ненадлежащее исполнение сотрудником процессуальных обязанностей", prompt)
        self.assertIn("ст. 84 Уголовного кодекса штата Сан-Андреас", prompt)
        self.assertIn("ст. 4 ч. 1 п. 1", prompt)
        self.assertIn("ст. 4 ч. 1 п. 6", prompt)
        self.assertIn("ст. 5 ч. 1-3", prompt)
        self.assertIn("ст. 5 ч. 4 п. 2", prompt)
        self.assertIn("ст. 5 ч. 2", prompt)
        self.assertIn("ст. 5 ч. 5", prompt)
        self.assertIn('ст. 23 ч. 1 п. "в" Процессуального кодекса штата Сан-Андреас', prompt)
        self.assertIn("ст. 74 ч. 1 Уголовного кодекса штата Сан-Андреас", prompt)
        self.assertIn("ст. 23 Административного кодекса штата Сан-Андреас", prompt)
        self.assertIn('Закона "Об адвокатуре и адвокатской деятельности в штате Сан-Андреас"', prompt)
        self.assertIn("SC128 S.A.", prompt)
        self.assertIn("процессуальные обязанности сотрудника", prompt)
        self.assertNotIn("Тактика усиления для wrongful_article", prompt)

    def test_suggest_prompt_prioritizes_article_84_for_official_attorney_request(self):
        prompt = build_suggest_prompt(
            victim_name="George Farmondov",
            org="GOV",
            subject="Pavel Clayton",
            event_dt="12.02.2026 09:54",
            raw_desc="По официальному адвокатскому запросу не предоставили доказательства и видеоматериалы.",
            complaint_basis="no_materials_by_request",
            main_focus="Не исполнили официальный адвокатский запрос",
        )
        self.assertIn("ст. 84 Уголовного кодекса штата Сан-Андреас", prompt)
        self.assertIn("если из черновика видно, что запрос был официальным, в первую очередь опирайся на ст. 84 Уголовного кодекса штата Сан-Андреас", prompt)
        self.assertIn("не начинай правовую опору только с Закона \"Об адвокатуре и адвокатской деятельности в штате Сан-Андреас\"", prompt)
        self.assertIn("а ст. 23 Процессуального кодекса штата Сан-Андреас", prompt)

    def test_suggest_prompt_contains_basis_specific_video_strategy(self):
        prompt = build_suggest_prompt(
            victim_name="Victim",
            org="LSPD",
            subject="John Doe",
            event_dt="08.04.2026 14:30",
            raw_desc="Draft",
            complaint_basis="no_video_or_no_evidence",
            main_focus="Видео не подтверждает ключевой момент задержания",
        )
        self.assertIn("Тактика усиления для no_video_or_no_evidence", prompt)
        self.assertIn("полная видеофиксация", prompt)
        self.assertIn("ключевые обстоятельства", prompt)
        self.assertIn("не утверждай отсутствие доказательств вообще", prompt)
        self.assertIn('ст. 23 ч. 1 п. "а" Процессуального кодекса штата Сан-Андреас', prompt)
        self.assertIn('ст. 23 ч. 1 п. "в" Процессуального кодекса штата Сан-Андреас', prompt)
        self.assertIn("ст. 11-14 Процессуального кодекса штата Сан-Андреас", prompt)
        self.assertIn("ст. 4 ч. 1 п. 1", prompt)
        self.assertIn("ст. 5 ч. 1-3", prompt)
        self.assertIn("ст. 5 ч. 4 п. 2", prompt)
        self.assertIn("ст. 5 ч. 2", prompt)
        self.assertIn("ст. 74 ч. 1 Уголовного кодекса штата Сан-Андреас", prompt)
        self.assertIn("ст. 23 Административного кодекса штата Сан-Андреас", prompt)
        self.assertIn('Закона "Об адвокатуре и адвокатской деятельности в штате Сан-Андреас"', prompt)
        self.assertIn("SC427 S.A.", prompt)
        self.assertIn("SC248 S.A.", prompt)
        self.assertIn("обязанность обеспечить надлежащую процессуальную видеофиксацию", prompt)
        self.assertIn("этого достаточно для прямой ссылки", prompt)
        self.assertNotIn("Тактика усиления для no_materials_by_request", prompt)

    def test_suggest_prompt_prefers_exact_articles_for_missing_video(self):
        prompt = build_suggest_prompt(
            victim_name="Victim",
            org="LSPD",
            subject="John Doe",
            event_dt="08.04.2026 14:30",
            raw_desc="Адвокату не предоставили видеофиксацию задержания по запросу.",
            complaint_basis="no_video_or_no_evidence",
            main_focus="Не предоставили видеофиксацию",
        )
        self.assertIn("в первую очередь опирайся на ст. 4 ч. 1 п. 1", prompt)
        self.assertIn('в первую очередь опирайся на ст. 23 ч. 1 п. "а" и п. "в" Процессуального кодекса штата Сан-Андреас', prompt)
        self.assertIn("дополнительно или приоритетно опирайся на ст. 5 ч. 1", prompt)
        self.assertIn("можно дополнительно опираться на ст. 5 ч. 2 и ст. 5 ч. 3", prompt)
        self.assertIn("допускается дополнительная сдержанная ссылка на ст. 74 ч. 1 Уголовного кодекса штата Сан-Андреас", prompt)
        self.assertIn("предпочитай прецедент SC427 S.A.", prompt)
        self.assertIn("можно дополнительно опираться на прецедент SC248 S.A.", prompt)
        self.assertIn("не заменяй эти точные статьи общей формулой", prompt)
        self.assertIn("предпочитай именно эту статью, а не общую ссылку на закон", prompt)
        self.assertNotIn("ст. 3.13", prompt)
        self.assertNotIn("ст. 1.8", prompt)
        self.assertNotIn("ст. 1.7", prompt)

    def test_suggest_prompt_contains_wrongful_article_number_fallback_logic(self):
        prompt = build_suggest_prompt(
            victim_name="Victim",
            org="LSPD",
            subject="John Doe",
            event_dt="08.04.2026 14:30",
            raw_desc="Вменили статью, которая не соответствует фактам.",
            complaint_basis="wrongful_article",
            main_focus="Спорная квалификация",
        )
        self.assertIn("если в черновике уже названа конкретная статья", prompt)
        self.assertIn("если номер статьи в черновике не назван", prompt)
        self.assertIn("более сильную формулу без номера", prompt)
        self.assertIn("если из черновика видно, что сотрудник вышел за пределы полномочий", prompt)
        self.assertIn("ст. 71 ч. 1 Уголовного кодекса штата Сан-Андреас", prompt)
        self.assertIn("ст. 71.1 Уголовного кодекса штата Сан-Андреас", prompt)
        self.assertIn("если в фактах прямо указана именно заведомость", prompt)

    def test_suggest_prompt_omits_basis_sections_when_not_provided(self):
        prompt = build_suggest_prompt(
            victim_name="Victim",
            org="LSPD",
            subject="John Doe",
            event_dt="08.04.2026 14:30",
            raw_desc="Draft",
        )
        self.assertNotIn("[focus_input]", prompt)
        self.assertIn("[article_anchors]", prompt)
        self.assertIn("[basis_strategy]", prompt)
        self.assertIn("Правовые ориентиры без выбранного направления", prompt)
        self.assertIn("Тактика без выбранного направления", prompt)
        self.assertIn("Процессуального кодекса штата Сан-Андреас", prompt)
        self.assertIn('ст. 23 ч. 1 п. "а"-"в" Процессуального кодекса штата Сан-Андреас', prompt)
        self.assertIn("ст. 11-14 Процессуального кодекса штата Сан-Андреас", prompt)
        self.assertIn("ст. 71 и ст. 71.1 Уголовного кодекса штата Сан-Андреас", prompt)
        self.assertIn("ст. 74 ч. 1 Уголовного кодекса штата Сан-Андреас", prompt)
        self.assertIn("ст. 23 Административного кодекса штата Сан-Андреас", prompt)
        self.assertIn("ст. 3 ч. 2-3, ст. 4, ст. 5 и ст. 6 Дорожного кодекса штата Сан-Андреас", prompt)
        self.assertIn("ст. 4, 7 и 9 Этического кодекса штата Сан-Андреас", prompt)
        self.assertIn('Закона "Об адвокатуре и адвокатской деятельности в штате Сан-Андреас"', prompt)
        self.assertIn("делай основной акцент на процессуальных обязанностях сотрудника", prompt)
        self.assertIn("не оставляй текст без прямой ссылки", prompt)

    def test_suggest_prompt_prioritizes_excess_of_power_for_wrongful_article_cases(self):
        prompt = build_suggest_prompt(
            victim_name="George Farmondov",
            org="GOV",
            subject="Pavel Clayton",
            event_dt="12.02.2026 09:54",
            raw_desc="Доверителя задержали без подтвержденных оснований и вменили статью, не соответствующую фактическим обстоятельствам.",
            complaint_basis="wrongful_article",
            main_focus="Не было оснований и вменили не ту статью",
        )
        self.assertIn("ст. 71 ч. 1 Уголовного кодекса штата Сан-Андреас", prompt)
        self.assertIn("ст. 71.1 Уголовного кодекса штата Сан-Андреас", prompt)
        self.assertIn("если из черновика видно, что сотрудник вышел за пределы полномочий", prompt)
        self.assertIn("если в фактах прямо указана именно заведомость", prompt)

    def test_suggest_prompt_treats_missing_video_as_sufficient_for_direct_norm(self):
        prompt = build_suggest_prompt(
            victim_name="George Farmondov",
            org="GOV",
            subject="Pavel Clayton",
            event_dt="12.02.2026 09:54",
            raw_desc=(
                "По имеющимся сведениям, видеофиксация предполагаемого нарушения отсутствует, "
                "в связи с чем законность и фактические обстоятельства действий в отношении доверителя "
                "не подтверждены надлежащими материалами."
            ),
        )
        self.assertIn("если в черновике прямо сказано, что видеофиксация отсутствует", prompt)
        self.assertIn("считай это достаточным основанием", prompt)
        self.assertIn('ст. 4 ч. 1 п. 1 и ст. 5 ч. 1-3 Закона "Об адвокатуре и адвокатской деятельности в штате Сан-Андреас"', prompt)
        self.assertIn('ст. 23 ч. 1 п. "а"-"в" Процессуального кодекса штата Сан-Андреас', prompt)
        self.assertIn("не оставляй текст без прямой ссылки", prompt)

    def test_suggest_prompt_prioritizes_pk_then_uk_then_advocacy_law(self):
        prompt = build_suggest_prompt(
            victim_name="George Farmondov",
            org="GOV",
            subject="Pavel Clayton",
            event_dt="12.02.2026 09:54",
            raw_desc=(
                "Видеофиксация задержания отсутствует, причины задержания не подтверждены, "
                "законность действий сотрудника проверить невозможно."
            ),
        )
        self.assertIn('в первую очередь проверяй и используй ст. 23 ч. 1 Процессуального кодекса штата Сан-Андреас', prompt)
        self.assertIn('допускается дополнительная ссылка на ст. 74 ч. 1 Уголовного кодекса штата Сан-Андреас', prompt)
        self.assertIn('Лишь после этого, при необходимости, используй Закон "Об адвокатуре и адвокатской деятельности в штате Сан-Андреас" как дополнительную, а не основную опору', prompt)

    def test_principal_scan_prompt_requires_json_only_and_missing_fields(self):
        prompt = build_principal_scan_prompt()
        self.assertIn("JSON", prompt)
        self.assertIn('"missing_fields"', prompt)
        self.assertIn("не выдумывай данные", prompt)

    def test_exam_scoring_prompt_requires_json_and_conservative_scoring(self):
        prompt = build_exam_scoring_prompt(
            user_answer="A",
            correct_answer="B",
            column="N",
            question="На каких закрытых территориях адвокат может находиться самостоятельно?",
            exam_type="Государственный адвокат",
            key_points=["КПЗ LSPD", "КПЗ LSSD"],
        )
        self.assertIn("JSON", prompt)
        self.assertIn('"score": 1-100', prompt)
        self.assertIn("draft reference answer", prompt)
        self.assertIn("Compare by legal meaning and core conclusion", prompt)
        self.assertIn("Exam type:", prompt)
        self.assertIn("Государственный адвокат", prompt)
        self.assertIn("Minimal required points", prompt)
        self.assertIn("КПЗ LSPD", prompt)
        self.assertIn("The rationale must be one short sentence", prompt)

    def test_exam_prompt_builders_are_defined_once(self):
        module_path = Path(__file__).resolve().parents[1] / "shared" / "ogp_ai_prompts.py"
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        target_names = {
            "build_exam_scoring_prompt_spec",
            "build_exam_scoring_prompt",
            "build_batch_exam_scoring_prompt_spec",
            "build_batch_exam_scoring_prompt",
        }
        counts = {name: 0 for name in target_names}
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in counts:
                counts[node.name] += 1

        self.assertEqual(
            counts,
            {
                "build_exam_scoring_prompt_spec": 1,
                "build_exam_scoring_prompt": 1,
                "build_batch_exam_scoring_prompt_spec": 1,
                "build_batch_exam_scoring_prompt": 1,
            },
        )

    def test_prompt_specs_expose_versioned_metadata(self):
        suggest = build_suggest_prompt_spec(
            victim_name="Victim",
            org="LSPD",
            subject="John Doe",
            event_dt="08.04.2026 14:30",
            raw_desc="Draft",
            complaint_basis="wrongful_article",
            main_focus="Спорная квалификация",
        )
        scan = build_principal_scan_prompt_spec()
        scoring = build_exam_scoring_prompt_spec(user_answer="A", correct_answer="B")
        batch = build_batch_exam_scoring_prompt_spec(prompt_items="F. test")

        self.assertEqual(suggest.version, SUGGEST_PROMPT_VERSION)
        self.assertEqual(scan.version, PRINCIPAL_SCAN_PROMPT_VERSION)
        self.assertEqual(scoring.version, EXAM_SCORING_PROMPT_VERSION)
        self.assertEqual(batch.version, EXAM_BATCH_SCORING_PROMPT_VERSION)
        self.assertIn("[system]", suggest.text)
        self.assertIn("[output_contract]", scan.text)
        self.assertIn("[scoring_rules]", scoring.text)
        self.assertIn("[task]", batch.text)


if __name__ == "__main__":
    unittest.main()

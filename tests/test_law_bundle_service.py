from __future__ import annotations

import json
import sys
import types
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

if "httpx" not in sys.modules:
    sys.modules["httpx"] = types.SimpleNamespace()

from ogp_web.services import law_bundle_service
from tests.temp_helpers import make_temporary_directory


class LawBundleServiceTests(unittest.TestCase):
    def test_extract_thread_posts_reads_multiple_forum_posts(self):
        html = """
        <html>
          <head><title>Важно - Уголовный кодекс | Форум GTA 5 RP</title></head>
          <body>
            <article class="message message--post js-post" data-author="Author One" data-content="post-1">
              <div class="message-userContent">
                <article class="message-body js-selectToQuote">
                  <div class="bbWrapper">
                    Статья 1. Общие положения. Текст статьи 1.
                  </div>
                </article>
              </div>
            </article>
            <article class="message message--post js-post" data-author="Author Two" data-content="post-2">
              <div class="message-userContent">
                <article class="message-body js-selectToQuote">
                  <div class="bbWrapper">
                    Комментарии к уголовному кодексу. Комментарий к статье 60.
                  </div>
                </article>
              </div>
            </article>
          </body>
        </html>
        """

        posts = law_bundle_service._extract_thread_posts(html)

        self.assertEqual(len(posts), 2)
        self.assertEqual(posts[0]["author"], "Author One")
        self.assertIn("Статья 1", posts[0]["text"])
        self.assertEqual(posts[1]["author"], "Author Two")
        self.assertIn("Комментарий", posts[1]["text"])

    def test_should_include_post_skips_commentary(self):
        self.assertTrue(
            law_bundle_service._should_include_post(
                "Уголовный кодекс",
                "Статья 23. Необходимая оборона. Текст нормы.",
            )
        )
        self.assertFalse(
            law_bundle_service._should_include_post(
                "Уголовный кодекс",
                "Комментарии к уголовному кодексу. Комментарий к статье 60.",
            )
        )

    def test_load_law_bundle_chunks_reads_utf8_json(self):
        tmpdir = make_temporary_directory()
        try:
            bundle_path = Path(tmpdir.name) / "bundle.json"
            bundle_path.write_text(
                json.dumps(
                    {
                        "server_code": "blackberry",
                        "generated_at_utc": "2026-04-11T12:00:00+00:00",
                        "sources": [{"url": "https://laws.example/criminal"}],
                        "articles": [
                            {
                                "url": "https://laws.example/criminal",
                                "document_title": "Уголовный кодекс",
                                "article_label": "Статья 23. Необходимая оборона",
                                "text": "Статья 23. Необходимая оборона. Текст нормы.",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            chunks = law_bundle_service.load_law_bundle_chunks("blackberry", str(bundle_path))
        finally:
            tmpdir.cleanup()

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].document_title, "Уголовный кодекс")
        self.assertEqual(chunks[0].article_label, "Статья 23. Необходимая оборона")

    def test_load_law_bundle_meta_reads_generation_details(self):
        tmpdir = make_temporary_directory()
        try:
            bundle_path = Path(tmpdir.name) / "bundle.json"
            bundle_path.write_text(
                json.dumps(
                    {
                        "server_code": "blackberry",
                        "generated_at_utc": "2026-04-11T12:00:00+00:00",
                        "sources": [{"url": "https://laws.example/criminal"}],
                        "articles": [
                            {
                                "url": "https://laws.example/criminal",
                                "document_title": "Criminal Code",
                                "article_label": "Article 23",
                                "text": "Self-defense.",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            meta = law_bundle_service.load_law_bundle_meta("blackberry", str(bundle_path))
        finally:
            tmpdir.cleanup()

        self.assertIsNotNone(meta)
        assert meta is not None
        self.assertEqual(meta.server_code, "blackberry")
        self.assertEqual(meta.generated_at_utc, "2026-04-11T12:00:00+00:00")
        self.assertEqual(meta.source_count, 1)
        self.assertEqual(meta.chunk_count, 1)
        self.assertTrue(meta.fingerprint)

    def test_split_structured_text_moves_trailing_chapter_heading_to_next_articles(self):
        chunks = law_bundle_service._split_structured_text_into_chunks(
            url="https://laws.example/criminal",
            document_title="Уголовный кодекс",
            text=(
                "Статья 22. Совершение преступления группой лиц. Текст статьи 22. "
                "ГЛАВА VI. Обстоятельства, исключающие преступность деяния "
                "Статья 23. Необходимая оборона. Не является преступлением причинение вреда. "
                "Статья 24. Причинение вреда при задержании лица, совершившего преступление. Текст статьи 24."
            ),
        )

        self.assertEqual(chunks[0].article_label, "Статья 22")
        self.assertNotIn("ГЛАВА VI", chunks[0].text)
        self.assertIn("ГЛАВА VI", chunks[1].text)
        self.assertIn("Необходимая оборона", chunks[1].text)
        self.assertIn("ГЛАВА VI", chunks[2].text)


if __name__ == "__main__":
    unittest.main()

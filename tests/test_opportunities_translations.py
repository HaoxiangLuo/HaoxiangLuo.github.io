#!/usr/bin/env python3
"""Tests for the Opportunities field-level translator.

Run with the repository's Python:

    python tests/test_opportunities_translations.py
    python -m unittest discover -s tests

Every case uses fabricated records and a fake translator: no network, no model
credit, no access to the real `_data/opportunities.json`.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import fetch_opportunities as opps  # noqa: E402


class FakeTranslator:
    """Stands in for `opps.Translator`: records calls, never touches the net."""

    def __init__(self, replies: dict | None = None, fail: bool = False) -> None:
        self.replies = replies or {}
        self.fail = fail
        self.calls: list[str] = []
        self.cache: dict = {}
        self.pending = 0
        self.public_calls = 0

    def translate(self, text: str, target: str) -> str:
        if text in self.cache:  # mirrors opps.Translator's per-run cache
            return self.cache[text]
        self.calls.append(text)
        if self.fail:
            self.pending += 1
            self.cache[text] = ""
            return ""
        reply = self.replies.get(text) or ""
        if not reply:
            self.pending += 1
        self.cache[text] = reply
        return reply


def sections_with(*items: dict) -> dict:
    return {"internships": [{"date": "2026-09-29", "items": list(items)}], "academia": []}


def item(**overrides) -> dict:
    base = {
        "title": "WHS Intern",
        "url": "https://www.amazon.jobs/en/jobs/10541373/whs-intern",
        "detail": "San Fernando de Henares, Community of Madrid, ESP",
        "source": "Amazon",
        "source_zh": "亚马逊",
        "group": "company",
    }
    base.update(overrides)
    return base


class BackfillTests(unittest.TestCase):
    def test_english_title_and_detail_are_translated(self):
        record = item()
        sections = sections_with(record)
        translator = FakeTranslator(
            {
                "WHS Intern": "仓储安全实习生",
                "San Fernando de Henares, Community of Madrid, ESP": "西班牙马德里自治区 圣费尔南多-德埃纳雷斯",
            }
        )
        filled = opps.backfill_translations(sections, translator)

        self.assertEqual(filled, {"titles": 1, "details": 1})
        self.assertEqual(record["title_zh"], "仓储安全实习生")
        self.assertEqual(record["detail_zh"], "西班牙马德里自治区 圣费尔南多-德埃纳雷斯")
        # The publisher's wording is never replaced.
        self.assertEqual(record["title"], "WHS Intern")
        self.assertEqual(record["detail"], "San Fernando de Henares, Community of Madrid, ESP")

    def test_existing_translations_are_kept(self):
        record = item(title_zh="已有的中文标题", detail_zh="已有的中文地点")
        translator = FakeTranslator({"WHS Intern": "仓储安全实习生"})
        filled = opps.backfill_translations(sections_with(record), translator)

        self.assertEqual(filled, {"titles": 0, "details": 0})
        self.assertEqual(record["title_zh"], "已有的中文标题")
        self.assertEqual(record["detail_zh"], "已有的中文地点")
        self.assertEqual(translator.calls, [])

    def test_identical_text_is_requested_once(self):
        first = item()
        second = item(url="https://www.amazon.jobs/en/jobs/2/whs-intern")
        translator = FakeTranslator({"WHS Intern": "仓储安全实习生"})
        opps.backfill_translations(sections_with(first, second), translator)

        self.assertEqual(translator.calls.count("WHS Intern"), 1)
        self.assertEqual(first["title_zh"], "仓储安全实习生")
        self.assertEqual(second["title_zh"], "仓储安全实习生")

    def test_failed_translation_keeps_the_record(self):
        record = item()
        translator = FakeTranslator(fail=True)
        filled = opps.backfill_translations(sections_with(record), translator)

        self.assertEqual(filled, {"titles": 0, "details": 0})
        self.assertEqual(translator.pending, 2)
        self.assertNotIn("title_zh", record)
        self.assertNotIn("detail_zh", record)
        self.assertEqual(record["title"], "WHS Intern")
        self.assertEqual(record["url"], "https://www.amazon.jobs/en/jobs/10541373/whs-intern")
        self.assertEqual(record["source"], "Amazon")

    def test_budget_stops_the_run(self):
        sections = sections_with(item(), item(url="https://example.org/b"))
        translator = FakeTranslator({"WHS Intern": "仓储安全实习生"})
        filled = opps.backfill_translations(sections, translator, budget=1)

        self.assertEqual(filled["titles"] + filled["details"], 1)

    def test_chinese_source_uses_the_english_field(self):
        record = {"title": "联合国儿童基金会实习", "url": "https://example.org/unicef"}
        translator = FakeTranslator({"联合国儿童基金会实习": "UNICEF internship"})
        filled = opps.backfill_translations(sections_with(record), translator)

        self.assertEqual(filled, {"titles": 1, "details": 0})
        self.assertEqual(record["title_en"], "UNICEF internship")
        self.assertNotIn("title_zh", record)


class TidyTranslationTests(unittest.TestCase):
    def test_empty_reply_is_refused(self):
        self.assertEqual(opps.tidy_translation("", "zh"), "")

    def test_reply_without_chinese_is_refused(self):
        self.assertEqual(opps.tidy_translation("WHS Intern", "zh"), "")

    def test_overlong_reply_is_refused(self):
        self.assertEqual(opps.tidy_translation("译" * (opps.MAX_TRANSLATION_CHARS + 1), "zh"), "")

    def test_explanatory_prefix_is_stripped(self):
        self.assertEqual(opps.tidy_translation("翻译：仓储安全实习生", "zh"), "仓储安全实习生")

    def test_url_bearing_reply_is_refused(self):
        self.assertEqual(opps.tidy_translation("仓储安全实习生 https://example.org", "zh"), "")

    def test_english_target_rejects_chinese(self):
        self.assertEqual(opps.tidy_translation("仓储安全实习生", "en"), "")


class TranslatorSafetyTests(unittest.TestCase):
    def test_urls_and_html_are_never_sent(self):
        translator = opps.Translator(token="fake")
        self.assertFalse(translator.translatable("See https://example.org/job"))
        self.assertFalse(translator.translatable("<b>Intern</b>"))
        self.assertTrue(translator.translatable("WHS Intern"))

    def test_overlong_source_is_never_sent(self):
        translator = opps.Translator(token="fake")
        self.assertFalse(translator.translatable("x" * (opps.MAX_SOURCE_CHARS + 1)))

    def test_without_a_token_nothing_is_requested(self):
        translator = opps.Translator(token="")
        self.assertEqual(translator.translate("WHS Intern", "zh"), "")
        self.assertEqual(translator.calls, 0)
        self.assertEqual(translator.pending, 1)

    def test_identical_text_is_requested_once(self):
        translator = opps.Translator(token="fake")
        seen: list[str] = []
        translator._request = lambda text, target: seen.append(text) or "仓储安全实习生"

        self.assertEqual(translator.translate("WHS Intern", "zh"), "仓储安全实习生")
        self.assertEqual(translator.translate("WHS Intern", "zh"), "仓储安全实习生")
        self.assertEqual(seen, ["WHS Intern"])
        self.assertEqual(translator.calls, 1)

    def test_a_failed_request_is_not_retried_forever(self):
        translator = opps.Translator(token="fake")
        attempts: list[str] = []
        translator._request = lambda text, target: attempts.append(text) or "WHS Intern"

        self.assertEqual(translator.translate("WHS Intern", "zh"), "")
        self.assertEqual(len(attempts), opps.TRANSLATE_ATTEMPTS)
        self.assertEqual(translator.pending, 1)


class PageFallbackTests(unittest.TestCase):
    """The two pages must read the matching field and fall back to the source."""

    def setUp(self):
        self.en = (ROOT / "_pages" / "opportunities.html").read_text(encoding="utf-8")
        self.zh = (ROOT / "_pages" / "opportunities-zh.html").read_text(encoding="utf-8")

    def test_english_page_prefers_the_english_fields(self):
        self.assertIn("item.title_en | default: item.title", self.en)
        self.assertIn("item.detail_en | default: item.detail", self.en)

    def test_chinese_page_prefers_the_chinese_fields(self):
        self.assertIn("item.title_zh | default: item.title", self.zh)
        self.assertIn("item.detail_zh | default: item.detail", self.zh)

    def test_both_pages_keep_the_source_link(self):
        for page in (self.en, self.zh):
            self.assertIn('href="{{ item.url }}"', page)

    def test_both_pages_explain_how_the_text_is_produced(self):
        # The footer must say which parts are generated by fixed templates and
        # which are still the publisher's own wording.
        self.assertIn(
            "Chinese summaries, labels and match reasons are generated by fixed templates",
            self.en,
        )
        self.assertIn("中文摘要、标签与匹配理由由固定模板生成", self.zh)

    def test_both_pages_offer_the_four_recommendation_modules(self):
        for page, words in (
            (self.en, ("Exceptional matches", "Closing soon", "Newly published", "Remote")),
            (self.zh, ("极高匹配", "即将截止", "最新发布", "远程机会")),
        ):
            for word in words:
                self.assertIn(word, page)

    def test_both_pages_include_the_filter_bar_and_the_card_include(self):
        for page in (self.en, self.zh):
            self.assertIn("{% include opps-filters.html", page)
            self.assertIn("{% include opps-card.html", page)

    def test_both_pages_keep_a_closed_section(self):
        self.assertIn('where: "status", "closed"', self.en)
        self.assertIn('where: "status", "closed"', self.zh)


class TranslateOnlyTests(unittest.TestCase):
    def test_history_is_filled_without_collecting(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "opportunities.json"
            target.write_text(
                json.dumps(
                    {
                        "updated_at": "2026-09-29T09:43:06+08:00",
                        "internships": [{"date": "2026-09-29", "items": [item()]}],
                        "academia": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            original_output = opps.OUTPUT
            original_build = opps.build_translator
            original_gather = opps.gather
            try:
                opps.OUTPUT = target
                opps.build_translator = lambda: FakeTranslator(
                    {"WHS Intern": "仓储安全实习生"}
                )

                def explode(*_args, **_kwargs):
                    raise AssertionError("--translate-only must not collect anything")

                opps.gather = explode
                self.assertEqual(opps.main(["--translate-only"]), 0)
            finally:
                opps.OUTPUT = original_output
                opps.build_translator = original_build
                opps.gather = original_gather

            saved = json.loads(target.read_text(encoding="utf-8"))
            stored = saved["internships"][0]["items"][0]
            self.assertEqual(stored["title_zh"], "仓储安全实习生")
            self.assertEqual(stored["title"], "WHS Intern")

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "opportunities.json"
            before = json.dumps(
                {
                    "updated_at": "2026-09-29T09:43:06+08:00",
                    "internships": [{"date": "2026-09-29", "items": [item()]}],
                    "academia": [],
                },
                ensure_ascii=False,
                indent=2,
            )
            target.write_text(before, encoding="utf-8")

            original_output = opps.OUTPUT
            original_build = opps.build_translator
            try:
                opps.OUTPUT = target
                opps.build_translator = lambda: FakeTranslator({"WHS Intern": "仓储安全实习生"})
                self.assertEqual(opps.main(["--translate-only", "--dry-run"]), 0)
            finally:
                opps.OUTPUT = original_output
                opps.build_translator = original_build

            self.assertEqual(target.read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main()

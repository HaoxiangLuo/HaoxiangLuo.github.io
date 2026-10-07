#!/usr/bin/env python3
"""Tests for the Academic Frontiers Chinese fields.

Run with the repository's Python:

    python tests/test_academic_frontiers_translations.py
    python -m unittest discover -s tests

Every case uses fabricated records and a fake translator: no network, no model
credit, no OpenAlex. The point of each case is the failure it guards against —
a Chinese title is added beside the English one rather than replacing it, and a
run that runs out of budget must still leave the archive consistent.
"""

from __future__ import annotations

import sys
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import fetch_academic_frontiers as frontiers  # noqa: E402


def article(number: int, day: str, **extra) -> dict:
    record = {
        "id": f"doi:10.1000/paper{number}",
        "title": f"Paper {number}: platform publics and political talk",
        "abstract_excerpt": f"Abstract {number}: we study how platforms shape public debate.",
        "journal": "Journal of Communication",
        "published_at": day,
    }
    record.update(extra)
    return record


class FakeChinese:
    """Stand-in for the network call: deterministic, offline, counts calls."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    # Not a function on purpose: patch.object installs the instance as a class
    # attribute, so no `self` is bound and the call carries (text, prompt).
    def __call__(self, text: str, _prompt: str = "") -> str:
        self.seen.append(text)
        return "译文：" + text[:12]


class TranslationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fake = FakeChinese()
        self.patcher = unittest.mock.patch.object(
            frontiers.ArticleTranslator, "chinese", self.fake
        )
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_a_collected_article_gets_both_chinese_fields(self) -> None:
        record = article(1, "2026-10-01")
        filled, _translator, changed = frontiers.translate_articles([record], 10)
        self.assertEqual(filled, {"titles": 1, "abstracts": 1})
        self.assertEqual(changed, ["doi:10.1000/paper1"])
        # The English wording is what makes the paper findable; it stays.
        self.assertEqual(record["title"], "Paper 1: platform publics and political talk")
        self.assertTrue(record["title_zh"])
        self.assertTrue(record["abstract_excerpt_zh"])

    def test_a_stored_translation_is_never_overwritten(self) -> None:
        record = article(1, "2026-10-01", title_zh="已有标题", abstract_excerpt_zh="已有摘要")
        filled, _translator, changed = frontiers.translate_articles([record], 10)
        self.assertEqual(filled, {"titles": 0, "abstracts": 0})
        self.assertEqual(changed, [])
        self.assertEqual(record["title_zh"], "已有标题")

    def test_the_budget_stops_half_way_and_reports_what_is_left(self) -> None:
        records = [article(1, "2026-10-01"), article(2, "2026-10-02"), article(3, "2026-10-03")]
        filled, translator, changed = frontiers.translate_articles(records, 3)
        # Three fields only: the first article's pair and one field of the next.
        self.assertEqual(filled, {"titles": 2, "abstracts": 1})
        self.assertEqual(len(changed), 2)
        self.assertEqual(translator.pending, 2)

    def test_newest_articles_are_translated_before_the_backlog(self) -> None:
        fresh = [article(9, "2026-10-09")]
        history = [article(1, "2026-09-01"), article(2, "2026-09-02")]
        merged, fresh_ids = frontiers.merge_history(history, fresh)
        self.assertEqual([record["id"] for record in merged][0], "doi:10.1000/paper9")
        self.assertEqual(fresh_ids, {"doi:10.1000/paper9"})
        frontiers.translate_articles(merged, 2)
        self.assertTrue(merged[0]["title_zh"])
        self.assertFalse(merged[1].get("title_zh"))

    def test_recollecting_a_stored_article_keeps_its_translation(self) -> None:
        history = [article(1, "2026-09-01", title_zh="旧译标题", abstract_excerpt_zh="旧译摘要")]
        fresh = [article(1, "2026-09-01", title="Paper 1: platform publics and political talk")]
        merged, fresh_ids = frontiers.merge_history(history, fresh)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["title_zh"], "旧译标题")
        self.assertEqual(merged[0]["abstract_excerpt_zh"], "旧译摘要")
        self.assertEqual(fresh_ids, {"doi:10.1000/paper1"})


if __name__ == "__main__":
    unittest.main()

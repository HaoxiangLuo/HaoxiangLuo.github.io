#!/usr/bin/env python3
"""Tests for the append-only archive layer.

Run with the repository's Python:

    python tests/test_archive_data.py
    python -m unittest discover -s tests

Nothing here touches the real `_data` archives: every case builds a throwaway
repository root in a temporary directory.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import archive_data  # noqa: E402
import build_data_snapshot  # noqa: E402


def day(offset: int) -> str:
    return (datetime.now(archive_data.TZ) - timedelta(days=offset)).strftime("%Y-%m-%d")


def news_item(index: int) -> dict:
    return {
        "title": f"Headline {index}",
        "source": "BBC World",
        "url": f"https://example.org/story/{index}",
        "title_zh": f"标题 {index}",
    }


def article(index: int, published: str, doi: str | None = None) -> dict:
    return {
        "id": f"doi:10.1000/test{index}" if doi is None else doi,
        "title": f"Article {index}",
        "abstract_excerpt": f"Excerpt {index}",
        "journal": "Journal of Communication",
        "issn_l": "0021-9916",
        "published_at": published,
        "authors": [f"Author {index}"],
        "doi_url": f"https://doi.org/10.1000/test{index}",
        "landing_page_url": f"https://example.org/article/{index}",
        "source_tier": "SSCI Q1",
        "focus": ["global"],
    }


def site_update(index: int, date: str, sha: str | None = None) -> dict:
    short = sha or f"{index:07d}"
    full = sha or f"{index:040d}"
    return {
        "date": date,
        "title_zh": f"更新 {index}",
        "title_en": f"Update {index}",
        "purpose_zh": f"目的 {index}",
        "purpose_en": f"Purpose {index}",
        "details_zh": f"细节 {index}",
        "details_en": f"Details {index}",
        "sha": short,
        "url": f"https://github.com/HaoxiangLuo/HaoxiangLuo.github.io/commit/{full}",
    }


class ArchiveTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    # helpers ------------------------------------------------------------- #
    def write_index(self, dataset: str, payload: object) -> None:
        path = self.root / archive_data.SPECS[dataset]["index"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def read_index(self, dataset: str) -> object:
        path = self.root / archive_data.SPECS[dataset]["index"]
        return json.loads(path.read_text(encoding="utf-8"))

    def partitions(self, dataset: str) -> list[Path]:
        directory = archive_data.dataset_dir(self.root, dataset)
        return sorted(directory.glob("*.jsonl")) if directory.is_dir() else []

    def archive_records(self, dataset: str) -> list[dict]:
        records: list[dict] = []
        for path in self.partitions(dataset):
            found, _ = archive_data.read_jsonl(path)
            records.extend(found)
        return records


class JsonlIntegrityTests(ArchiveTestCase):
    def test_every_written_line_is_valid_json(self):
        self.write_index("daily_news", {"updated_at": None, "days": [{"date": day(1), "items": [news_item(1)]}]})
        archive_data.process_dataset(self.root, "daily_news")

        files = self.partitions("daily_news")
        self.assertEqual(len(files), 1)
        lines = [line for line in files[0].read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        parsed = json.loads(lines[0])
        self.assertEqual(parsed["id"], f"daily-news:{day(1)}")
        self.assertEqual(parsed["schema_version"], 1)

    def test_invalid_lines_are_counted_not_crashed(self):
        directory = archive_data.dataset_dir(self.root, "daily_news")
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "2026-09.jsonl").write_text(
            json.dumps({"id": "daily-news:2026-09-01", "date": "2026-09-01", "items": []}) + "\n{broken\n",
            encoding="utf-8",
        )
        records, invalid = archive_data.read_jsonl(directory / "2026-09.jsonl")
        self.assertEqual(len(records), 1)
        self.assertEqual(invalid, 1)


class DailyNewsTests(ArchiveTestCase):
    def test_migration_keeps_every_day(self):
        days = [{"date": day(offset), "items": [news_item(offset)]} for offset in range(5)]
        self.write_index("daily_news", {"updated_at": None, "days": days})

        stats = archive_data.process_dataset(self.root, "daily_news")
        self.assertEqual(stats.added, 5)
        self.assertEqual(len(self.archive_records("daily_news")), 5)

        index = self.read_index("daily_news")
        self.assertEqual([entry["date"] for entry in index["days"]], [entry["date"] for entry in days])

    def test_rerun_is_idempotent(self):
        days = [{"date": day(offset), "items": [news_item(offset)]} for offset in range(3)]
        self.write_index("daily_news", {"updated_at": None, "days": days})

        first = archive_data.process_dataset(self.root, "daily_news")
        second = archive_data.process_dataset(self.root, "daily_news")

        self.assertEqual(first.added, 3)
        self.assertEqual(second.added, 0)
        self.assertEqual(second.updated, 0)
        self.assertEqual(len(self.archive_records("daily_news")), 3)

    def test_same_date_updates_in_place_and_keeps_translations(self):
        self.write_index("daily_news", {"updated_at": None, "days": [{"date": day(0), "items": [news_item(1)]}]})
        archive_data.process_dataset(self.root, "daily_news")

        incoming = archive_data.normalize(
            "daily_news",
            {
                "date": day(0),
                # The re-collected day carries a new headline but no translation.
                "items": [{"title": "Headline 1", "source": "BBC World", "url": "https://example.org/story/1"}],
            },
        )
        archive_data.process_dataset(self.root, "daily_news", [incoming])

        records = self.archive_records("daily_news")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["items"][0]["title_zh"], "标题 1")

    def test_duplicate_ids_are_merged(self):
        payload = {"updated_at": None, "days": [{"date": day(0), "items": [news_item(1)]}]}
        payload["days"].append({"date": day(0), "items": [news_item(2)]})
        self.write_index("daily_news", payload)

        stats = archive_data.process_dataset(self.root, "daily_news")
        self.assertEqual(stats.deduplicated, 1)
        self.assertEqual(len(self.archive_records("daily_news")), 1)

    def test_monthly_partitioning(self):
        months = [day(0), day(40), day(80)]
        self.write_index("daily_news", {"updated_at": None, "days": [{"date": date, "items": []} for date in months]})
        archive_data.process_dataset(self.root, "daily_news")
        names = sorted(path.stem for path in self.partitions("daily_news"))
        self.assertEqual(names, sorted({date[:7] for date in months}))

    def test_recent_index_keeps_ninety_days(self):
        days = [{"date": day(offset), "items": [news_item(offset)]} for offset in range(0, 120, 10)]
        self.write_index("daily_news", {"updated_at": None, "days": days})
        archive_data.process_dataset(self.root, "daily_news")

        index = self.read_index("daily_news")
        self.assertEqual(len(index["days"]), len([entry for entry in days if entry["date"] >= day(89)]))
        # The archive itself never drops anything for being old.
        self.assertEqual(len(self.archive_records("daily_news")), len(days))


class FrontiersTests(ArchiveTestCase):
    def test_yearly_partition_and_retention(self):
        items = [article(index, day(index * 100)) for index in range(3)]
        self.write_index("academic_frontiers", {"updated_at": None, "items": items})
        archive_data.process_dataset(self.root, "academic_frontiers")

        self.assertEqual(sorted(path.stem for path in self.partitions("academic_frontiers")),
                         sorted({item["published_at"][:4] for item in items}))
        index = self.read_index("academic_frontiers")
        self.assertEqual(len(index["items"]), len([item for item in items if item["published_at"] >= day(179)]))
        self.assertEqual(len(self.archive_records("academic_frontiers")), len(items))

    def test_update_does_not_erase_stored_fields(self):
        published = day(5)
        self.write_index("academic_frontiers", {"updated_at": None, "items": [article(1, published)]})
        archive_data.process_dataset(self.root, "academic_frontiers")

        thinner = article(1, published)
        thinner["abstract_excerpt"] = None
        thinner["authors"] = []
        archive_data.process_dataset(self.root, "academic_frontiers", [archive_data.normalize("academic_frontiers", thinner)])

        stored = self.archive_records("academic_frontiers")[0]
        self.assertEqual(stored["abstract_excerpt"], "Excerpt 1")
        self.assertEqual(stored["authors"], ["Author 1"])

    def test_missing_doi_falls_back_to_stable_id(self):
        published = day(2)
        item = article(9, published, doi="openalex:W123456")
        self.write_index("academic_frontiers", {"updated_at": None, "items": [item]})
        archive_data.process_dataset(self.root, "academic_frontiers")
        self.assertEqual(self.archive_records("academic_frontiers")[0]["id"], "openalex:W123456")


class SiteUpdateTests(ArchiveTestCase):
    def test_full_sha_is_used_as_the_stable_id(self):
        entry = site_update(1, day(0))
        self.write_index("site_updates", [entry])
        archive_data.process_dataset(self.root, "site_updates")
        stored = self.archive_records("site_updates")[0]
        self.assertTrue(stored["id"].startswith("commit:"))
        self.assertEqual(len(stored["id"].split(":", 1)[1]), 40)
        self.assertEqual(stored["sha"], entry["sha"])

    def test_short_sha_entries_are_kept_and_marked(self):
        entry = site_update(2, day(1))
        entry["url"] = ""
        self.write_index("site_updates", [entry])
        archive_data.process_dataset(self.root, "site_updates")
        stored = self.archive_records("site_updates")[0]
        self.assertEqual(stored["sha_source"], "short")
        self.assertEqual(stored["sha"], entry["sha"])

    def test_recent_index_keeps_one_hundred_entries(self):
        entries = [site_update(index, day(index)) for index in range(120)]
        self.write_index("site_updates", entries)
        archive_data.process_dataset(self.root, "site_updates")

        index = self.read_index("site_updates")
        self.assertEqual(len(index), 100)
        self.assertEqual(len(self.archive_records("site_updates")), 120)

    def test_index_entries_lose_archive_bookkeeping(self):
        self.write_index("site_updates", [site_update(1, day(0))])
        archive_data.process_dataset(self.root, "site_updates")
        entry = self.read_index("site_updates")[0]
        self.assertNotIn("id", entry)
        self.assertNotIn("schema_version", entry)
        self.assertNotIn("fetched_at", entry)


class ManifestTests(ArchiveTestCase):
    def test_manifest_counts_and_checksums_match_the_files(self):
        self.write_index("daily_news", {"updated_at": None, "days": [{"date": day(0), "items": [news_item(1)]}]})
        self.write_index("academic_frontiers", {"updated_at": None, "items": [article(1, day(0))]})
        self.write_index("site_updates", [site_update(1, day(0))])
        archive_data.run(self.root, list(archive_data.DATASETS))

        manifest = json.loads(archive_data.manifest_path(self.root).read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], 1)
        for dataset in archive_data.DATASETS:
            entry = manifest["archives"][dataset]
            self.assertEqual(entry["format"], "jsonl")
            total = sum(part["records"] for part in entry["available"])
            self.assertEqual(total, len(self.archive_records(dataset)))
            for part in entry["available"]:
                path = self.root / part["url"].lstrip("/")
                self.assertEqual(part["sha256"], archive_data.sha256_of(path))

    def test_upsert_refreshes_the_manifest_checksum(self):
        # The collectors write through `upsert()`, so the manifest has to follow
        # that path too; otherwise the stored checksum describes the previous
        # version of the partition and the snapshot no longer verifies.
        self.write_index("site_updates", [site_update(1, day(0))])
        archive_data.run(self.root, ["site_updates"])
        archive_data.upsert(self.root, "site_updates", [site_update(2, day(1))])

        manifest = json.loads(archive_data.manifest_path(self.root).read_text(encoding="utf-8"))
        part = manifest["archives"]["site_updates"]["available"][0]
        path = self.root / part["url"].lstrip("/")
        self.assertEqual(part["sha256"], archive_data.sha256_of(path))
        self.assertEqual(part["records"], len(self.archive_records("site_updates")))

    def test_manifest_lists_only_existing_partitions(self):
        self.write_index("site_updates", [site_update(1, day(0))])
        archive_data.run(self.root, ["site_updates"])
        manifest = json.loads(archive_data.manifest_path(self.root).read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["archives"]["site_updates"]["available"]), 1)
        self.assertEqual(manifest["archives"]["daily_news"]["available"], [])


class AtomicWriteTests(ArchiveTestCase):
    def test_failed_write_keeps_the_original_file(self):
        path = self.root / "sample.json"
        path.write_text(json.dumps({"keep": True}), encoding="utf-8")

        with self.assertRaises(Exception):
            archive_data.atomic_write(path, "{not json", archive_data.validate_json)

        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"keep": True})
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_failed_jsonl_write_keeps_the_original_lines(self):
        directory = archive_data.dataset_dir(self.root, "daily_news")
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "2026-09.jsonl"
        path.write_text(json.dumps({"id": "daily-news:2026-09-01", "date": "2026-09-01", "items": []}) + "\n", encoding="utf-8")

        broken = [{"id": "daily-news:2026-09-01", "date": "2026-09-01", "items": []}, object()]
        with self.assertRaises(Exception):
            archive_data.write_jsonl(path, broken)  # type: ignore[list-item]

        records, invalid = archive_data.read_jsonl(path)
        self.assertEqual(len(records), 1)
        self.assertEqual(invalid, 0)
        self.assertEqual(list(directory.glob("*.tmp")), [])


class SnapshotTests(ArchiveTestCase):
    def test_snapshot_packages_one_year(self):
        year = day(0)[:4]
        self.write_index("daily_news", {"updated_at": None, "days": [{"date": day(0), "items": [news_item(1)]}]})
        self.write_index("academic_frontiers", {"updated_at": None, "items": [article(1, day(0))]})
        self.write_index("site_updates", [site_update(1, day(0))])
        archive_data.run(self.root, list(archive_data.DATASETS))

        output = self.root / "snapshot"
        zip_path, summary = build_data_snapshot.build_zip(self.root, int(year), output)

        self.assertTrue(zip_path.exists())
        self.assertEqual(summary["counts"]["daily_news"], 1)
        self.assertEqual(summary["counts"]["academic_frontiers"], 1)
        self.assertEqual(summary["counts"]["site_updates"], 1)
        self.assertIn("SHA256SUMS.txt", summary["files"])
        self.assertIn("README.md", summary["files"])
        self.assertIn(f"daily-news/{day(0)[:7]}.jsonl", summary["files"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

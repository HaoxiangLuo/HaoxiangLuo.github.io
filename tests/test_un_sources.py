#!/usr/bin/env python3
"""Tests for the UN collectors in scripts/un_sources.py.

These run offline against small pieces of saved markup. The point of each case
is the failure it guards against: UNDP's vacancy cards put five values in one
anchor, so reading the anchor's whole text would store "Job Title … Post level
…" as the title; an empty category feed still publishes one "no jobs" item;
UNICEF hides the duty station inside the title.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import un_sources  # noqa: E402

UNDP_PAGE = """
<div class="vacanciesTable">
  <a href="https://estm.fa.em2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/requisitions/job/37114"
     class="vacanciesTableLink vacanciesTable__row region_IN country_THA">
    <div class="vacanciesTable__cell"><div class="vacanciesTable__cell__label">Job Title</div>
      <span>Conflict Prevention and Peacebuilding Intern</span></div>
    <div class="vacanciesTable__cell"><div class="vacanciesTable__cell__label">Post level</div><span>IN</span></div>
    <div class="vacanciesTable__cell"><div class="vacanciesTable__cell__label">Apply by</div><span>Oct-7-26</span></div>
    <div class="vacanciesTable__cell"><div class="vacanciesTable__cell__label">Agency</div><span>UNDP</span></div>
    <div class="vacanciesTable__cell"><div class="vacanciesTable__cell__label">Location</div><span>Bangkok, Thailand</span></div>
  </a>
</div>
"""

UNWOMEN_PAGE = """
<table><tbody>
<tr>
  <td class="views-field views-field-title"><a href="https://estm.fa.em2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/requisitions/job/37222">National Consultant - Gender Statistics and Data - Kampala, Uganda</a></td>
  <td class="views-field views-field-field-job-type">EXT</td>
  <td class="views-field views-field-field-rss-country">UGANDA</td>
  <td class="views-field views-field-field-city">Kampala, Uganda</td>
  <td class="views-field views-field-field-deadline">08-10-2026</td>
</tr>
</tbody></table>
"""

EMPTY_FEED = """<?xml version="1.0"?><rss version="2.0"><channel>
  <item><title>No jobs currently available</title><link>https://jobs.ilo.org/</link></item>
</channel></rss>"""

UNICEF_FEED = """<?xml version="1.0"?><rss version="2.0"><channel>
  <item>
    <title>Planning, Monitoring and Evaluation (PM&amp;E) Internship, Mbabane, Eswatini (6 months only)</title>
    <link>https://jobs.unicef.org/cw/en-us/job/596000</link>
    <description>Support monitoring and evaluation.</description>
  </item>
</channel></rss>"""

UNIDO_PAGE = """
<a href="/job/Vienna-Project-Associate/1370684755/">Project Associate</a>
<a href="/job/Home-Based-Technical-Expert/1370684756/">Technical Expert</a>
"""


class UndpTests(unittest.TestCase):
    def test_cells_are_read_one_by_one(self):
        source = {"code": "undp", "name": "UNDP", "name_zh": "联合国开发计划署", "priority": 1,
         "value": "https://jobs.undp.org/cj_view_jobs.cfm"}
        un_sources.http_get = lambda url, **kwargs: UNDP_PAGE
        items = un_sources.collect_undp_html(source)
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["title"], "Conflict Prevention and Peacebuilding Intern")
        self.assertEqual(item["location"], "Bangkok, Thailand")
        self.assertEqual(item["job_id"], "37114")
        self.assertEqual(item["deadline"], "2026-10-07")
        self.assertTrue(item["url"].startswith("https://"))


class UnWomenTests(unittest.TestCase):
    def test_city_and_deadline_come_from_their_own_columns(self):
        source = {"code": "unwomen", "name": "UN Women", "name_zh": "联合国妇女署", "priority": 1,
         "value": "https://www.unwomen.org/en/jobs/undp"}
        un_sources.http_get = lambda url, **kwargs: UNWOMEN_PAGE
        items = un_sources.collect_unwomen_html(source)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["location"], "Kampala, Uganda")
        self.assertEqual(items[0]["deadline"], "2026-10-08")


class RssTests(unittest.TestCase):
    def setUp(self):
        self.original = un_sources.http_get

    def tearDown(self):
        un_sources.http_get = self.original

    def test_a_placeholder_item_is_not_an_opening(self):
        source = {"code": "ilo", "name": "ILO", "name_zh": "国际劳工组织", "priority": 3,
         "value": "https://jobs.ilo.org/rss"}
        un_sources.http_get = lambda url, **kwargs: EMPTY_FEED
        self.assertEqual(un_sources.collect_rss(source), [])

    def test_unicef_duty_station_is_read_from_the_title(self):
        source = {"code": "unicef", "name": "UNICEF", "name_zh": "联合国儿童基金会", "priority": 1,
         "value": "https://jobs.unicef.org/cw/en/rss"}
        un_sources.http_get = lambda url, **kwargs: UNICEF_FEED
        items = un_sources.collect_rss(source)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["location"], "Mbabane, Eswatini")
        self.assertEqual(items[0]["job_id"], "596000")


class SuccessFactorsTests(unittest.TestCase):
    def test_the_duty_station_is_read_from_the_slug(self):
        source = {
            "code": "unido", "name": "UNIDO", "name_zh": "联合国工发组织", "priority": 3,
            "value": "https://careers.unido.org/search/",
            "base": "https://careers.unido.org",
        }
        un_sources.http_get = lambda url, **kwargs: UNIDO_PAGE
        items = un_sources.collect_successfactors_html(source)
        self.assertEqual([item["location"] for item in items], ["Vienna", "Home-based"])
        self.assertTrue(items[0]["url"].startswith("https://careers.unido.org/"))


class RegistryTests(unittest.TestCase):
    def test_every_source_has_a_collector_and_a_chinese_name(self):
        for source in un_sources.SOURCES:
            self.assertIn(source["kind"], un_sources.COLLECTORS, source["code"])
            self.assertTrue(source["name_zh"], source["code"])
            self.assertIn(source["priority"], (1, 2, 3), source["code"])

    def test_first_priority_organisations_are_all_present(self):
        codes = {source["code"] for source in un_sources.SOURCES}
        for code in ("un", "unesco", "unicef", "undp", "unwomen", "unhcr"):
            self.assertIn(code, codes)

    def test_a_failing_shared_backend_costs_one_request(self):
        """Five sources read careers.un.org; when it is down the rest skip it."""
        un_sources._FAILED_HOSTS.clear()
        un_sources.http_get = lambda url, **kwargs: (_ for _ in ()).throw(OSError("504"))
        with self.assertRaises(Exception):
            un_sources.collect_un_careers({"code": "un", "name": "UN", "name_zh": "联合国", "priority": 1})
        self.assertIn("careers.un.org", un_sources._FAILED_HOSTS)
        with self.assertRaises(RuntimeError):
            un_sources.collect_un_careers({"code": "unep", "name": "UNEP", "name_zh": "环境署", "priority": 2})
        un_sources._FAILED_HOSTS.clear()


if __name__ == "__main__":
    unittest.main()

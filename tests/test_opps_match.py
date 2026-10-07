#!/usr/bin/env python3
"""Tests for the UN internship matching rules in scripts/opps_match.py.

Every case here is a posting that either must be kept or must never reach the
page. The rules exist to answer three questions — what suits the profile, what
is worth applying to, what is closing soon — so the tests are written as
postings rather than as functions: a finance internship has to score below the
cut-off, a digital-communication internship has to reach the top tier, and a
posting that never states its stipend must say so instead of guessing.
"""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import opps_match  # noqa: E402

TODAY = date(2026, 10, 7)

IDEAL = (
    "Digital Communication Intern",
    (
        "The Division for Digital Communication is looking for an intern to support "
        "social media analytics, audience research and content strategy. Tasks include "
        "monitoring misinformation and disinformation across digital platforms, "
        "preparing analytics reports and supporting strategic communication. "
        "Applicants must be enrolled in a Master's or PhD programme in communication, "
        "media studies or data science. The internship is home-based and lasts 6 months. "
        "A stipend of USD 1,700 per month is provided. Application deadline: 15 November 2026."
    ),
)


class ScoringTests(unittest.TestCase):
    def score(self, title: str, body: str = "", org: str = "unesco", priority: int = 1,
              location: str = "Paris, France") -> dict:
        return opps_match.score_opening(
            title, body, org_code=org, org_priority=priority, location=location, today=TODAY
        )

    def test_ideal_opening_reaches_the_top_tier(self):
        result = self.score(*IDEAL)
        self.assertEqual(result["tier"], "exceptional")
        self.assertGreaterEqual(result["score"], 90)
        self.assertIn("communication", result["areas"])
        self.assertTrue(result["phd_ok"])
        self.assertEqual(result["mode"], "remote")
        self.assertEqual(result["deadline"], "2026-11-15")
        self.assertEqual(result["days_left"], 39)
        self.assertEqual(result["stipend"], "paid")
        self.assertIn("USD 1,700", result["stipend_amount"])
        self.assertEqual(result["duration"], "6 months")
        self.assertTrue(result["reasons"])
        self.assertTrue(result["reasons_zh"])

    def test_plain_communication_internship_is_kept(self):
        result = self.score("Communication Intern", "Support the communication team with media relations and outreach.")
        self.assertEqual(result["type"], "internship")
        self.assertGreaterEqual(result["score"], 70)
        self.assertLess(result["score"], 90)

    def test_data_opening_counts_without_the_word_communication(self):
        result = self.score(
            "Data Analysis Intern",
            "Collect and analyse social media data, build dashboards and support audience analytics.",
        )
        self.assertIn("data", result["areas"])
        self.assertGreaterEqual(result["score"], opps_match.MIN_SCORE)

    def test_finance_opening_is_never_shown(self):
        result = self.score(
            "Finance Assistant Intern",
            "Support accounting, payroll and procurement. Open to undergraduate students only.",
        )
        self.assertLess(result["score"], opps_match.MIN_SCORE)
        self.assertEqual(result["tier"], "hidden")
        self.assertTrue(result["excluded"])

    def test_engineering_and_medical_openings_are_hidden(self):
        for title in ("Engineering Intern", "Clinical Research Intern"):
            self.assertLess(self.score(title, "Support the team.").get("score", 0), opps_match.MIN_SCORE)

    def test_information_and_communication_technology_is_not_communication(self):
        """An ITU post about ICT must not be filed as a communication post."""
        result = self.score(
            "Cybersecurity Intern",
            "Support work on information and communication technologies, telecommunication "
            "networks and ICT infrastructure.",
        )
        self.assertNotIn("communication", result["areas"])

    def test_consultancy_that_takes_doctoral_researchers_survives(self):
        result = self.score(
            "Consultant: Media Research",
            "Individual contractor. Open to PhD students and early-career researchers. "
            "Analyse media coverage and public opinion.",
        )
        self.assertEqual(result["type"], "consultancy")
        self.assertGreaterEqual(result["score"], opps_match.MIN_SCORE)

    def test_undergraduate_only_is_not_credited_as_graduate(self):
        result = self.score("Intern", "Open to undergraduate students only.")
        self.assertIn("undergraduate_only", result["eligibility"])
        self.assertNotIn("graduate", result["eligibility"])

    def test_a_long_off_profile_description_cannot_lift_the_score(self):
        # ITU's e-waste post reads like a data or policy opening only because
        # a long description mentions data, research and policy throughout.
        # The title says what the post is, and it says circular economy.
        body = (
            "ITU is the International Telecommunication Union, the United Nations agency "
            "for information and communication technologies. The intern supports the Global "
            "E-waste Monitor: data collection, information gathering, drafting and overall "
            "coordination. The work covers policy development and regulations governing "
            "e-waste. Ability to conduct research efficiently and draft clear documentation. "
            "Applicants must be enrolled in a Master's or PhD programme."
        )
        result = self.score(
            "Unpaid Internship - Circular Economy Intern (Geneva, Switzerland)",
            body,
            org="itu",
            priority=2,
            location="Geneva, Switzerland",
        )
        self.assertLess(result["score"], opps_match.MIN_SCORE)

    def test_a_post_named_after_the_agency_is_not_a_communication_post(self):
        self.assertNotIn(
            "communication",
            opps_match.match_areas("ITU is the International Telecommunication Union"),
        )

    def test_a_short_data_internship_still_passes(self):
        # Feeds often carry a title and nothing else. That is not evidence
        # against a post whose title already names its direction.
        result = self.score(
            "Data Analyst Intern, Istanbul, Turkiye",
            "",
            org="unwomen",
            priority=1,
            location="Istanbul, Turkiye",
        )
        self.assertGreaterEqual(result["score"], opps_match.MIN_SCORE)


class FieldTests(unittest.TestCase):
    def test_unstated_stipend_is_not_invented(self):
        result = opps_match.extract_stipend("The internship lasts three months.")
        self.assertEqual(result["paid"], "unknown")
        self.assertEqual(result["note"], "未说明 / Not stated")

    def test_unpaid_is_read(self):
        self.assertEqual(opps_match.extract_stipend("This internship is unpaid.")["paid"], "unpaid")

    def test_deadline_shapes(self):
        for text, expected in (
            ("Apply by 15 November 2026", "2026-11-15"),
            ("Deadline: 31/Dec/2026", "2026-12-31"),
            ("Application deadline Oct-7-26", "2026-10-07"),
            ("Closing date 08-10-2026", "2026-10-08"),
        ):
            self.assertEqual(opps_match.parse_date(text), expected, text)

    def test_experience_is_not_read_as_duration(self):
        self.assertEqual(opps_match.extract_duration("At least 5 years of experience is required."), "")
        self.assertEqual(opps_match.extract_duration("Duration of contract: 6 months"), "6 months")

    def test_status_never_guesses_without_a_date(self):
        self.assertEqual(opps_match.status_of(""), "open")
        self.assertEqual(opps_match.status_of("2026-10-09", TODAY), "closing")
        self.assertEqual(opps_match.status_of("2026-10-01", TODAY), "closed")

    def test_remote_and_home_based_are_detected(self):
        self.assertEqual(opps_match.extract_mode("This is a home-based assignment."), "remote")
        self.assertEqual(opps_match.extract_mode("Hybrid arrangement, two days in the office."), "hybrid")

    def test_place_from_text_finds_a_duty_station(self):
        self.assertEqual(opps_match.place_from_text("PM&E Internship, Mbabane, Eswatini (6 months)"), "Mbabane, Eswatini")
        self.assertEqual(opps_match.place_from_text("Consultant, Bucharest, Romania"), "Bucharest, Romania")
        self.assertEqual(opps_match.place_from_text("Consultant for child protection"), "")

    def test_location_is_translated(self):
        self.assertEqual(opps_match.location_zh("Geneva", "Switzerland"), "瑞士日内瓦")
        self.assertEqual(opps_match.location_zh("Home Based", "Remote"), "远程（居家）")
        self.assertEqual(opps_match.location_zh("Multiple", "Multiple"), "多个地点")


class DedupeTests(unittest.TestCase):
    def test_same_job_id_is_one_opening(self):
        first = opps_match.dedupe_key("undp", "37114", "https://a.example/job/37114", "Intern")
        second = opps_match.dedupe_key("undp", "37114", "https://b.example/job/37114", "Intern")
        self.assertEqual(first[0], second[0])

    def test_without_a_job_id_the_title_decides(self):
        key, _ = opps_match.dedupe_key("itu", "", "", "Editorial Intern")
        self.assertTrue(key.startswith("itu:"))


class LabelTests(unittest.TestCase):
    def test_every_type_and_mode_has_both_languages(self):
        for name in opps_match.TYPE_ZH:
            self.assertIn(name, opps_match.TYPE_LABELS)
        for mode in ("remote", "hybrid", "onsite", "unknown"):
            self.assertIn(mode, opps_match.MODE_ZH)
        for status in ("open", "closing", "closed", "unknown"):
            self.assertIn(status, opps_match.STATUS_ZH)

    def test_tiers_run_from_exceptional_downwards(self):
        self.assertEqual(opps_match.tier_of(95), "exceptional")
        self.assertEqual(opps_match.tier_of(85), "high")
        self.assertEqual(opps_match.tier_of(75), "good")
        self.assertEqual(opps_match.tier_of(65), "possible")
        self.assertEqual(opps_match.tier_of(40), "hidden")
        self.assertEqual(opps_match.tier_zh(95), "极高匹配")
        self.assertEqual(opps_match.tier_en(95), "Exceptional match")


if __name__ == "__main__":
    unittest.main()

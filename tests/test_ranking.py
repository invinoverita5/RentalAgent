import unittest
from datetime import UTC, datetime

from rental_agent.ranking import rank_listings


class RankListingsTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 4, 25, 12, 0, tzinfo=UTC)
        self.user_state = {
            "budget_max_per_person": 1200,
            "budget_target_per_person": 950,
            "commute_max_minutes": 30,
            "move_in_date": "2026-08-01",
        }

    def test_budget_first_ranks_lower_all_in_cost_first(self):
        result = rank_listings(
            "session_1",
            [
                self.listing("expensive", all_in_estimate_per_person=1170),
                self.listing("cheap", all_in_estimate_per_person=920),
            ],
            self.user_state,
            "budget_first",
            2,
            now=self.now,
        )

        self.assertEqual(
            [listing["listing_id"] for listing in result["ranked_listings"]],
            ["cheap", "expensive"],
        )
        self.assertEqual(result["ranking_weights"]["all_in_cost"], 0.42)
        self.assertEqual(result["confidence"], 0.8)

    def test_stale_removed_and_unknown_freshness_are_excluded(self):
        result = rank_listings(
            "session_1",
            [
                self.listing("fresh"),
                self.listing("stale", freshness_status="stale"),
                self.listing("removed", freshness_status="removed"),
                self.listing("unknown", freshness_status="unknown"),
            ],
            self.user_state,
            "student_default",
            5,
            now=self.now,
        )

        self.assertEqual(
            [listing["listing_id"] for listing in result["ranked_listings"]],
            ["fresh"],
        )
        excluded = {item["listing_id"]: item["reasons"] for item in result["excluded_listings"]}
        self.assertIn("freshness_status is stale", excluded["stale"])
        self.assertIn("freshness_status is removed", excluded["removed"])
        self.assertIn("freshness_status is unknown", excluded["unknown"])

    def test_unknown_price_basis_and_missing_cost_are_excluded(self):
        result = rank_listings(
            "session_1",
            [
                self.listing("good"),
                self.listing(
                    "unknown_price",
                    price_basis="unknown",
                    rent_per_person_monthly=None,
                    all_in_estimate_per_person=None,
                    ranking_blockers=["unknown_price_basis"],
                ),
            ],
            self.user_state,
            "student_default",
            5,
            now=self.now,
        )

        self.assertEqual(len(result["ranked_listings"]), 1)
        self.assertEqual(result["excluded_listings"][0]["listing_id"], "unknown_price")
        self.assertIn(
            "price basis is unknown",
            result["excluded_listings"][0]["reasons"],
        )

    def test_needs_verification_and_unknown_fees_add_inline_warnings(self):
        result = rank_listings(
            "session_1",
            [
                self.listing(
                    "verify",
                    freshness_status="needs_verification",
                    utilities_status="unknown",
                    fees_status="unknown",
                    all_in_estimate_per_person=None,
                )
            ],
            self.user_state,
            "student_default",
            1,
            now=self.now,
        )

        ranked = result["ranked_listings"][0]
        self.assertIn("Needs verification", ranked["inline_warnings"][0])
        self.assertIn("Utilities unknown", ranked["inline_warnings"][1])
        self.assertIn("Fees unknown", ranked["inline_warnings"][2])
        self.assertEqual(ranked["cost_basis"], "rent_only_per_person")
        self.assertEqual(result["missing_data_penalties"][0]["listing_id"], "verify")

    def test_budget_overage_is_excluded_unless_stretch_budget_allowed(self):
        excluded = rank_listings(
            "session_1",
            [self.listing("stretch", all_in_estimate_per_person=1300)],
            self.user_state,
            "student_default",
            1,
            allow_stretch_budget=False,
            now=self.now,
        )

        self.assertEqual(excluded["ranked_listings"], [])
        self.assertIn(
            "cost exceeds budget_max_per_person",
            excluded["excluded_listings"][0]["reasons"],
        )

        included = rank_listings(
            "session_1",
            [self.listing("stretch", all_in_estimate_per_person=1300)],
            self.user_state,
            "student_default",
            1,
            allow_stretch_budget=True,
            now=self.now,
        )

        self.assertEqual(included["ranked_listings"][0]["listing_id"], "stretch")
        self.assertIn(
            "Stretch budget",
            included["ranked_listings"][0]["inline_warnings"][0],
        )

    def test_commute_max_excludes_long_walks(self):
        result = rank_listings(
            "session_1",
            [self.listing("too_far", walk_minutes_to_campus=45)],
            self.user_state,
            "commute_first",
            1,
            now=self.now,
        )

        self.assertEqual(result["ranked_listings"], [])
        self.assertIn(
            "walk_minutes_to_campus exceeds commute_max_minutes",
            result["excluded_listings"][0]["reasons"],
        )

    def test_hard_required_fields_are_enforced(self):
        cases = [
            ("no_source", {"source_urls": []}, "source URL is missing"),
            ("no_location", {"address_raw": None, "address_normalized": None}, "usable location is missing"),
            ("no_dedupe", {"dedupe_status": None}, "dedupe status is missing"),
            ("disallowed", {"source_allowed_for_v1": False}, "source_allowed_for_v1 is false"),
        ]

        for listing_id, overrides, expected_reason in cases:
            with self.subTest(listing_id=listing_id):
                result = rank_listings(
                    "session_1",
                    [self.listing(listing_id, **overrides)],
                    self.user_state,
                    "student_default",
                    1,
                    now=self.now,
                )
                self.assertEqual(result["ranked_listings"], [])
                self.assertIn(expected_reason, result["excluded_listings"][0]["reasons"])

    def test_safety_context_mode_uses_allowed_language(self):
        result = rank_listings(
            "session_1",
            [
                self.listing(
                    "context_strong",
                    walk_minutes_to_campus=12,
                    student_area_fit=0.9,
                    managed_or_student_source_signal=True,
                    safety_context_notes=[
                        "Context only; this is not a safety guarantee.",
                        "Stronger context fit for a safety concern because the approximate walk to campus is short.",
                    ],
                )
            ],
            self.user_state,
            "safety_context_first",
            1,
            now=self.now,
        )

        ranked = result["ranked_listings"][0]
        rendered = " ".join(
            ranked["inline_warnings"]
            + [ranked["main_tradeoff"], ranked["fit_label"]]
        ).lower()
        self.assertEqual(result["ranking_weights"]["safety_context_fit"], 0.30)
        self.assertIn("safety_context_fit", ranked["score_breakdown"])
        self.assertNotIn("this area is safe", rendered)
        self.assertNotIn("this area is unsafe", rendered)

    def test_move_in_date_missing_warns_not_contact_ready(self):
        user_state = dict(self.user_state)
        user_state["move_in_date"] = None

        result = rank_listings(
            "session_1",
            [self.listing("one")],
            user_state,
            "student_default",
            1,
            now=self.now,
        )

        self.assertIn(
            "Move-in date unknown",
            result["ranked_listings"][0]["inline_warnings"][0],
        )

    def test_validation_errors(self):
        with self.assertRaisesRegex(ValueError, "unsupported ranking_mode"):
            rank_listings(
                "session_1",
                [self.listing("one")],
                self.user_state,
                "crime_first",
                1,
                now=self.now,
            )

        with self.assertRaisesRegex(ValueError, "top_n"):
            rank_listings(
                "session_1",
                [self.listing("one")],
                self.user_state,
                "student_default",
                0,
                now=self.now,
            )

        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            rank_listings(
                "session_1",
                [self.listing("one")],
                self.user_state,
                "student_default",
                1,
                now=datetime(2026, 4, 25, 12, 0),
            )

    def listing(self, listing_id, **overrides):
        value = {
            "listing_id": listing_id,
            "source_urls": [f"https://example.edu/{listing_id}"],
            "title": f"Listing {listing_id}",
            "address_raw": "315 N 33rd St, Philadelphia, PA",
            "address_normalized": "315 N 33rd St, Philadelphia, PA",
            "rent_per_person_monthly": 950,
            "all_in_estimate_per_person": 1000,
            "price_basis": "per_person",
            "utilities_status": "included",
            "fees_status": "known",
            "dedupe_status": "unique",
            "freshness_status": "fresh_today",
            "ranking_blockers": [],
            "missing_data_penalty": 0,
            "walk_minutes_to_campus": 18,
            "student_area_fit": 0.8,
            "managed_or_student_source_signal": True,
            "parent_explainability_notes": ["Allowed public v1 source."],
            "safety_context_notes": ["Context only; this is not a safety guarantee."],
            "confidence": 0.8,
        }
        value.update(overrides)
        return value


if __name__ == "__main__":
    unittest.main()

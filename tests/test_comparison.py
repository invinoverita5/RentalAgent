import unittest
from datetime import UTC, datetime

from rental_agent.comparison import compare_listings


class CompareListingsTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 4, 25, 12, 0, tzinfo=UTC)
        self.user_state = {
            "budget_max_per_person": 1200,
            "budget_target_per_person": 950,
            "commute_max_minutes": 30,
            "move_in_date": "2026-08-01",
        }

    def test_fewer_than_two_listings_returns_missing_selection_response(self):
        result = compare_listings(
            "session_1",
            ["one"],
            ["overall"],
            self.user_state,
            [self.listing("one")],
            now=self.now,
        )

        self.assertEqual(result["comparison_rows"], [])
        self.assertEqual(result["best_for_student"], None)
        self.assertIn("Select at least two", result["blocking_unknowns"][0])

    def test_stale_removed_and_unknown_freshness_block_comparison(self):
        for status in ("stale", "removed", "unknown"):
            with self.subTest(status=status):
                result = compare_listings(
                    "session_1",
                    ["one", "two"],
                    ["overall"],
                    self.user_state,
                    [
                        self.listing("one"),
                        self.listing("two", freshness_status=status),
                    ],
                    now=self.now,
                )

                self.assertEqual(result["comparison_rows"], [])
                self.assertIn(
                    f"freshness_status is {status}",
                    result["blocking_unknowns"][0],
                )

    def test_missing_price_or_location_blocks_comparison(self):
        result = compare_listings(
            "session_1",
            ["one", "two"],
            ["cost", "commute"],
            self.user_state,
            [
                self.listing("one"),
                self.listing(
                    "two",
                    price_basis="unknown",
                    rent_per_person_monthly=None,
                    all_in_estimate_per_person=None,
                    address_raw=None,
                    address_normalized=None,
                ),
            ],
            now=self.now,
        )

        self.assertEqual(result["comparison_rows"], [])
        self.assertIn("price basis is unknown", " ".join(result["blocking_unknowns"]))
        self.assertIn("usable location is missing", " ".join(result["blocking_unknowns"]))

    def test_compares_selected_listings_with_facts_and_inferences(self):
        result = compare_listings(
            "session_1",
            ["cheap", "close"],
            ["overall"],
            self.user_state,
            [
                self.listing(
                    "cheap",
                    all_in_estimate_per_person=900,
                    walk_minutes_to_campus=28,
                ),
                self.listing(
                    "close",
                    all_in_estimate_per_person=1050,
                    walk_minutes_to_campus=10,
                ),
            ],
            now=self.now,
        )

        self.assertEqual(len(result["comparison_rows"]), 2)
        self.assertEqual(result["best_for_student"], "close")
        self.assertIsNotNone(result["best_parent_balanced"])
        self.assertTrue(result["main_tradeoffs"])
        first_row = result["comparison_rows"][0]
        self.assertTrue(
            all(fact["claim_type"] == "tool_fact" for fact in first_row["facts"])
        )
        self.assertTrue(
            all(
                inference["claim_type"] == "model_inference"
                for inference in first_row["inferences"]
            )
        )

    def test_dimension_filter_only_returns_requested_dimensions(self):
        result = compare_listings(
            "session_1",
            ["one", "two"],
            ["cost", "freshness"],
            self.user_state,
            [
                self.listing("one"),
                self.listing("two", all_in_estimate_per_person=1100),
            ],
            now=self.now,
        )

        dimensions = {
            fact["dimension"]
            for row in result["comparison_rows"]
            for fact in row["facts"]
        }
        self.assertEqual(dimensions, {"cost", "freshness"})
        self.assertEqual(result["comparison_rows"][0]["inferences"], [])

    def test_non_blocking_unknowns_are_reported_with_rows(self):
        user_state = dict(self.user_state)
        user_state["move_in_date"] = None
        result = compare_listings(
            "session_1",
            ["one", "two"],
            ["overall"],
            user_state,
            [
                self.listing("one", utilities_status="unknown"),
                self.listing("two", freshness_status="needs_verification"),
            ],
            now=self.now,
        )

        self.assertEqual(len(result["comparison_rows"]), 2)
        rendered_unknowns = " ".join(result["blocking_unknowns"])
        self.assertIn("Move-in date is unknown", rendered_unknowns)
        self.assertIn("utilities are unknown", rendered_unknowns)
        self.assertIn("same-day freshness needs verification", rendered_unknowns)

    def test_safety_context_language_is_caveated(self):
        result = compare_listings(
            "session_1",
            ["one", "two"],
            ["safety_context_fit"],
            self.user_state,
            [
                self.listing("one"),
                self.listing("two", safety_context_notes=["Context only."]),
            ],
            now=self.now,
        )

        rendered = str(result).lower()
        self.assertIn("not a guarantee of safety", rendered)
        self.assertNotIn("this area is safe", rendered)
        self.assertNotIn("this area is unsafe", rendered)

    def test_missing_listing_context_blocks_comparison(self):
        result = compare_listings(
            "session_1",
            ["one", "two"],
            ["overall"],
            self.user_state,
            None,
            now=self.now,
        )

        self.assertIn(
            "Comparable listing records are missing",
            result["blocking_unknowns"][0],
        )

    def test_invalid_dimension_and_naive_datetime_raise(self):
        with self.assertRaisesRegex(ValueError, "unsupported comparison dimension"):
            compare_listings(
                "session_1",
                ["one", "two"],
                ["crime_score"],
                self.user_state,
                [self.listing("one"), self.listing("two")],
                now=self.now,
            )

        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            compare_listings(
                "session_1",
                ["one", "two"],
                ["overall"],
                self.user_state,
                [self.listing("one"), self.listing("two")],
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
            "parent_explainability_notes": ["allowed public v1 source"],
            "safety_context_notes": ["Context only; this is not a safety guarantee."],
            "confidence": 0.8,
            "lease_terms": ["12 months"],
            "available_date": "2026-08-01",
        }
        value.update(overrides)
        return value


if __name__ == "__main__":
    unittest.main()

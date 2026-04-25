import unittest
from datetime import UTC, datetime

from rental_agent.enrichment import enrich_listings


class EnrichListingsTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 4, 25, 12, 0, tzinfo=UTC)

    def test_per_person_listing_gets_context_and_approximate_commute(self):
        result = enrich_listings(
            "session_1",
            "campus_drexel_university_city",
            [
                self.snapshot(
                    "1",
                    raw_title="Room in 4BR near campus",
                    raw_price="$980/person",
                    raw_location="3210 Chestnut St, Philadelphia, PA",
                    lat=39.9557,
                    lng=-75.1895,
                    utilities_raw="utilities included",
                    fees_raw="no monthly fees",
                )
            ],
            None,
            now=self.now,
        )

        listing = result["canonical_listings"][0]
        self.assertEqual(listing["price_basis"], "per_person")
        self.assertEqual(listing["rent_per_person_monthly"], 980)
        self.assertEqual(listing["all_in_estimate_per_person"], 980)
        self.assertGreater(listing["walk_minutes_to_campus"], 0)
        self.assertIn("Approximate walking estimate", listing["commute_label"])
        self.assertIn("Safety/context", listing["limitations"][0])
        self.assertNotIn("safety_score", listing)
        self.assertFalse(result["enrichment_errors"])

    def test_total_unit_price_splits_by_bedroom_count(self):
        result = enrich_listings(
            "session_1",
            "campus_drexel_university_city",
            [
                self.snapshot(
                    "1",
                    raw_title="3BR student apartment",
                    raw_price="$3,300 total",
                    raw_location="315 N 33rd St, Philadelphia, PA",
                    utilities_monthly_estimate=70,
                    fees_monthly_estimate=0,
                )
            ],
            None,
            now=self.now,
        )

        listing = result["canonical_listings"][0]
        self.assertEqual(listing["price_basis"], "total_unit")
        self.assertEqual(listing["bedrooms"], 3)
        self.assertEqual(listing["rent_total_monthly"], 3300)
        self.assertEqual(listing["rent_per_person_monthly"], 1100)
        self.assertEqual(listing["all_in_estimate_per_person"], 1170)
        self.assertIn("Assumed one occupant per bedroom", listing["price_assumptions"][0])

    def test_unknown_price_basis_blocks_ranking_and_adds_penalty(self):
        result = enrich_listings(
            "session_1",
            "campus_drexel_university_city",
            [
                self.snapshot(
                    "1",
                    raw_title="Student room",
                    raw_price="$1,000",
                    raw_location="University City",
                )
            ],
            None,
            now=self.now,
        )

        listing = result["canonical_listings"][0]
        self.assertEqual(listing["price_basis"], "unknown")
        self.assertIsNone(listing["rent_per_person_monthly"])
        self.assertIn("unknown_price_basis", listing["ranking_blockers"])
        self.assertIn("price_basis", listing["missing_fields"])
        self.assertGreater(listing["missing_data_penalty"], 0)

    def test_dedupes_specific_addresses_but_not_broad_locations(self):
        specific_result = enrich_listings(
            "session_1",
            "campus_drexel_university_city",
            [
                self.snapshot(
                    "1",
                    raw_location="315 N 33rd St, Philadelphia, PA",
                    source_url="https://offcampushousing.drexel.edu/listing/1",
                ),
                self.snapshot(
                    "2",
                    raw_location="315 N 33rd St, Philadelphia, PA",
                    source_url="https://offcampushousing.drexel.edu/listing/2",
                ),
            ],
            None,
            now=self.now,
        )

        self.assertEqual(len(specific_result["canonical_listings"]), 1)
        self.assertEqual(
            specific_result["canonical_listings"][0]["dedupe_status"],
            "merged",
        )
        self.assertEqual(len(specific_result["duplicate_groups"]), 1)

        broad_result = enrich_listings(
            "session_1",
            "campus_drexel_university_city",
            [
                self.snapshot("1", raw_location="University City"),
                self.snapshot("2", raw_location="University City"),
            ],
            None,
            now=self.now,
        )

        self.assertEqual(len(broad_result["canonical_listings"]), 2)
        self.assertEqual(
            broad_result["canonical_listings"][0]["dedupe_status"],
            "unknown",
        )

    def test_missing_coordinates_are_caveated_not_invented(self):
        result = enrich_listings(
            "session_1",
            "campus_temple_main",
            [
                self.snapshot(
                    "1",
                    source_id="temple_off_campus_housing",
                    source_url="https://offcampus.temple.edu/listing/1",
                    raw_price="$900/person",
                    raw_location="Main Campus / Templetown",
                )
            ],
            None,
            now=self.now,
        )

        listing = result["canonical_listings"][0]
        self.assertIsNone(listing["walk_minutes_to_campus"])
        self.assertIn("listing_coordinates", listing["missing_fields"])
        self.assertIn("coordinates are missing", listing["commute_label"])

    def test_safety_language_is_contextual_and_no_safety_score_field_exists(self):
        result = enrich_listings(
            "session_1",
            "campus_upenn_university_city",
            [
                self.snapshot(
                    "1",
                    source_id="penn_off_campus_services",
                    source_url="https://off-campus-services.business-services.upenn.edu/listing/1",
                    raw_price="$1,100/person",
                    raw_location="Spruce Hill",
                    lat=39.951,
                    lng=-75.205,
                )
            ],
            None,
            now=self.now,
        )

        listing = result["canonical_listings"][0]
        rendered = " ".join(
            listing["safety_context_notes"]
            + listing["parent_explainability_notes"]
            + listing["limitations"]
            + result["limitations"]
        ).lower()
        self.assertNotIn("safety_score", listing)
        self.assertNotIn("this area is safe", rendered)
        self.assertNotIn("this area is unsafe", rendered)
        self.assertIn("not a safety guarantee", rendered)

    def test_invalid_snapshots_are_reported_as_enrichment_errors(self):
        result = enrich_listings(
            "session_1",
            "campus_drexel_university_city",
            [
                {"source_url": "https://offcampushousing.drexel.edu/listing/1"},
                self.snapshot("1"),
            ],
            None,
            now=self.now,
        )

        self.assertEqual(len(result["canonical_listings"]), 1)
        self.assertEqual(
            result["enrichment_errors"][0]["error_type"],
            "snapshot_validation_error",
        )

    def test_empty_snapshots_and_unknown_campus_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "listing_snapshots"):
            enrich_listings(
                "session_1",
                "campus_drexel_university_city",
                [],
                None,
                now=self.now,
            )

        with self.assertRaisesRegex(ValueError, "unknown campus_id"):
            enrich_listings(
                "session_1",
                "campus_unknown",
                [self.snapshot("1")],
                None,
                now=self.now,
            )

    def test_invalid_options_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported enrichment option"):
            enrich_listings(
                "session_1",
                "campus_drexel_university_city",
                [self.snapshot("1")],
                {"crime_score": True},
                now=self.now,
            )

        with self.assertRaisesRegex(ValueError, "must be a boolean"):
            enrich_listings(
                "session_1",
                "campus_drexel_university_city",
                [self.snapshot("1")],
                {"dedupe": "yes"},
                now=self.now,
            )

    def test_naive_datetime_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            enrich_listings(
                "session_1",
                "campus_drexel_university_city",
                [self.snapshot("1")],
                None,
                now=datetime(2026, 4, 25, 12, 0),
            )

    def snapshot(self, listing_id, **overrides):
        value = {
            "snapshot_id": f"snap_{listing_id}",
            "source_id": "drexel_off_campus_housing",
            "source_url": f"https://offcampushousing.drexel.edu/listing/{listing_id}",
            "source_listing_id": listing_id,
            "raw_title": f"Listing {listing_id}",
            "raw_price": "$1,000/person",
            "raw_location": "University City",
            "freshness_status": "fresh_today",
        }
        value.update(overrides)
        return value


if __name__ == "__main__":
    unittest.main()

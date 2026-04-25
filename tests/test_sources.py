import unittest
from datetime import UTC, datetime

from rental_agent.sources import (
    SourcePolicy,
    get_source_registry,
    select_sources_for_retrieval,
)


class SourceRegistryTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 4, 25, 12, 0, tzinfo=UTC)

    def test_registry_can_scope_sources_to_campus(self):
        sources = get_source_registry("campus_drexel_university_city")

        source_ids = {source["source_id"] for source in sources}
        self.assertIn("drexel_off_campus_housing", source_ids)
        self.assertIn("facebook_student_sublets", source_ids)
        self.assertNotIn("temple_off_campus_housing", source_ids)

    def test_registry_can_hide_blocked_and_disallowed_sources(self):
        sources = get_source_registry(
            "campus_drexel_university_city",
            include_blocked=False,
        )

        self.assertEqual(
            {source["source_id"] for source in sources},
            {"drexel_off_campus_housing"},
        )

    def test_select_sources_skips_disallowed_before_fetch(self):
        result = select_sources_for_retrieval(
            "campus_drexel_university_city",
            now=self.now,
        )

        selected_ids = {source["source_id"] for source in result["selected_sources"]}
        skipped_by_id = {
            skipped["source"]["source_id"]: skipped["reason"]
            for skipped in result["skipped_sources"]
        }

        self.assertEqual(selected_ids, {"drexel_off_campus_housing"})
        self.assertEqual(
            skipped_by_id["drexel_housing_guidance"],
            "source_allowed_for_v1 is false",
        )
        self.assertEqual(
            skipped_by_id["facebook_student_sublets"],
            "source requires login or private access",
        )
        self.assertEqual(skipped_by_id["zillow"], "source_allowed_for_v1 is false")

    def test_avoid_sources_policy_skips_selected_source(self):
        result = select_sources_for_retrieval(
            "campus_temple_main",
            {
                "avoid_sources": ["temple_off_campus_housing"],
            },
            now=self.now,
        )

        self.assertEqual(result["selected_sources"], [])
        skipped_by_id = {
            skipped["source"]["source_id"]: skipped["reason"]
            for skipped in result["skipped_sources"]
        }
        self.assertEqual(
            skipped_by_id["temple_off_campus_housing"],
            "source_id listed in avoid_sources",
        )

    def test_allowed_source_types_policy_skips_other_types(self):
        result = select_sources_for_retrieval(
            "campus_upenn_university_city",
            SourcePolicy(allowed_source_types=("property_manager",)),
            now=self.now,
        )

        self.assertEqual(result["selected_sources"], [])
        self.assertTrue(
            all(
                "source_type" in skipped["reason"]
                or skipped["reason"] == "source_allowed_for_v1 is false"
                for skipped in result["skipped_sources"]
            )
        )

    def test_login_required_source_never_runs_when_public_only_policy_enabled(self):
        result = select_sources_for_retrieval(
            "campus_temple_main",
            {
                "require_source_allowed_for_v1": False,
                "non_login_public_only": True,
            },
            now=self.now,
        )

        skipped_by_id = {
            skipped["source"]["source_id"]: skipped["reason"]
            for skipped in result["skipped_sources"]
        }
        self.assertEqual(
            skipped_by_id["facebook_student_sublets"],
            "source requires login or private access",
        )

    def test_blocked_adapter_skip_reason_is_reported(self):
        result = select_sources_for_retrieval(
            "campus_temple_main",
            {
                "allowed_source_types": ["student_housing_portal"],
                "non_login_public_only": False,
                "require_source_allowed_for_v1": False,
            },
            now=self.now,
        )

        skipped_by_id = {
            skipped["source"]["source_id"]: skipped["reason"]
            for skipped in result["skipped_sources"]
        }
        self.assertEqual(
            skipped_by_id["facebook_student_sublets"],
            "adapter_status is blocked",
        )

    def test_unknown_campus_returns_source_error_separate_from_empty_results(self):
        result = select_sources_for_retrieval("campus_unknown", now=self.now)

        self.assertEqual(result["selected_sources"], [])
        self.assertEqual(result["skipped_sources"], [])
        self.assertEqual(
            result["source_errors"],
            [
                {
                    "source_id": None,
                    "error_type": "unknown_campus",
                    "message": "No source registry records exist for campus_id 'campus_unknown'.",
                }
            ],
        )

    def test_invalid_source_type_policy_raises(self):
        with self.assertRaisesRegex(ValueError, "unsupported allowed source type"):
            select_sources_for_retrieval(
                "campus_drexel_university_city",
                {"allowed_source_types": ["facebook_group"]},
                now=self.now,
            )

    def test_invalid_policy_field_types_raise(self):
        invalid_policies = (
            {"allowed_source_types": "official_university_portal"},
            {"allowed_source_types": ["official_university_portal", 7]},
            {"non_login_public_only": "false"},
            {"require_source_allowed_for_v1": "true"},
            {"avoid_sources": "zillow"},
            {"avoid_sources": ["zillow", 7]},
        )

        for policy in invalid_policies:
            with self.subTest(policy=policy):
                with self.assertRaisesRegex(ValueError, "must"):
                    select_sources_for_retrieval(
                        "campus_drexel_university_city",
                        policy,
                        now=self.now,
                    )

    def test_naive_datetime_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            select_sources_for_retrieval(
                "campus_drexel_university_city",
                now=datetime(2026, 4, 25, 12, 0),
            )


if __name__ == "__main__":
    unittest.main()

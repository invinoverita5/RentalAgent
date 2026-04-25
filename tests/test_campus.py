import unittest

from rental_agent.campus import get_campus_context


class GetCampusContextTests(unittest.TestCase):
    def test_resolves_drexel_without_confirmation(self):
        result = get_campus_context("Drexel")

        self.assertFalse(result["needs_user_confirmation"])
        self.assertEqual(result["university_name"], "Drexel University")
        self.assertEqual(
            result["selected_campus_id"],
            "campus_drexel_university_city",
        )
        self.assertEqual(
            result["campuses"][0]["address"],
            "3141 Chestnut Street, Philadelphia, PA 19104",
        )
        self.assertTrue(result["official_resources"])

    def test_campus_hint_does_not_break_school_alias_resolution(self):
        result = get_campus_context("Drexel", campus_hint="University City")

        self.assertFalse(result["needs_user_confirmation"])
        self.assertEqual(
            result["selected_campus_id"],
            "campus_drexel_university_city",
        )

    def test_resolves_temple_alias(self):
        result = get_campus_context("temple main")

        self.assertFalse(result["needs_user_confirmation"])
        self.assertEqual(result["university_name"], "Temple University")
        self.assertEqual(result["selected_campus_id"], "campus_temple_main")
        self.assertIn("Broad Street", result["campuses"][0]["address"])

    def test_resolves_penn_alias(self):
        result = get_campus_context("UPenn")

        self.assertFalse(result["needs_user_confirmation"])
        self.assertEqual(result["university_name"], "University of Pennsylvania")
        self.assertEqual(
            result["selected_campus_id"],
            "campus_upenn_university_city",
        )

    def test_ambiguous_university_city_input_returns_choices(self):
        result = get_campus_context("University City")

        self.assertTrue(result["needs_user_confirmation"])
        self.assertIsNone(result["selected_campus_id"])
        self.assertEqual(
            {campus["campus_id"] for campus in result["campuses"]},
            {"campus_drexel_university_city", "campus_upenn_university_city"},
        )

    def test_later_philadelphia_school_is_clear_unsupported_response(self):
        result = get_campus_context("Villanova University")

        self.assertTrue(result["needs_user_confirmation"])
        self.assertEqual(result["campuses"], [])
        self.assertIn("later expansion", result["unsupported_reason"])

    def test_unknown_school_is_clear_unsupported_response(self):
        result = get_campus_context("Somewhere Else College")

        self.assertTrue(result["needs_user_confirmation"])
        self.assertEqual(result["campuses"], [])
        self.assertIn("Only Drexel, Temple, and Penn", result["unsupported_reason"])

    def test_context_type_filtering_and_commute_filter(self):
        result = get_campus_context(
            "Penn",
            max_commute_minutes=15,
            context_types=["campus_anchor", "student_areas"],
        )

        self.assertTrue(result["student_areas"])
        self.assertEqual(result["official_resources"], [])
        self.assertEqual(result["transport_notes"], [])
        self.assertTrue(
            all(area["student_area_fit"] >= 0.75 for area in result["student_areas"])
        )

    def test_context_notes_do_not_make_safe_or_unsafe_claims(self):
        for university in ("Drexel", "Temple", "Penn"):
            result = get_campus_context(university)
            notes = " ".join(result["transport_notes"] + result["housing_notes"]).lower()

            self.assertNotIn("this area is safe", notes)
            self.assertNotIn("this area is unsafe", notes)


if __name__ == "__main__":
    unittest.main()

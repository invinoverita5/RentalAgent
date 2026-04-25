import unittest
from datetime import UTC, datetime

from rental_agent.state import SessionStateStore, delete_user_state, update_user_state


class UpdateUserStateTests(unittest.TestCase):
    def setUp(self):
        self.store = SessionStateStore()
        self.now = datetime(2026, 4, 25, 12, 0, tzinfo=UTC)

    def update(self, session_id="session_1", updates=None, assumptions=None):
        return update_user_state(
            session_id,
            updates or {},
            assumptions or [],
            store=self.store,
            now=self.now,
        )

    def test_creates_session_and_defaults_budget_to_per_person(self):
        result = self.update(
            updates={
                "university": "Drexel University",
                "budget_max_per_person": 1200,
                "roommates_open": True,
            }
        )

        self.assertEqual(
            result["changed_fields"],
            ["university", "budget_max_per_person", "roommates_open"],
        )
        self.assertEqual(result["state"]["budget_max_per_person"], 1200.0)
        self.assertEqual(result["state"]["roommates_open"], True)
        self.assertIn("campus_id", result["missing_critical_fields"])
        self.assertEqual(
            result["state"]["assumptions"],
            [
                {
                    "field": "budget_basis",
                    "assumption": "Budget interpreted as monthly per-person rent.",
                    "confidence": 0.75,
                }
            ],
        )

    def test_reports_conflict_without_overwriting_existing_constraint(self):
        self.update(updates={"budget_max_per_person": 1200})

        result = self.update(updates={"budget_max_per_person": 1400})

        self.assertEqual(result["changed_fields"], [])
        self.assertEqual(result["state"]["budget_max_per_person"], 1200.0)
        self.assertEqual(
            result["conflicts"],
            ["budget_max_per_person already has value 1200.0; received 1400.0"],
        )

    def test_updates_soft_parent_preference_inside_same_session(self):
        self.update(
            updates={
                "parents_involved": True,
                "parent_priority": "building reliability",
            }
        )

        result = self.update(updates={"parent_priority": "shorter walk and managed source"})

        self.assertEqual(result["changed_fields"], ["parent_priority"])
        self.assertEqual(result["state"]["parents_involved"], True)
        self.assertEqual(
            result["state"]["parent_priority"],
            "shorter walk and managed source",
        )

    def test_validates_enums_and_iso_dates(self):
        with self.assertRaisesRegex(ValueError, "safety_context_priority"):
            self.update(updates={"safety_context_priority": "safest"})

        with self.assertRaisesRegex(ValueError, "move_in_date"):
            self.update(updates={"move_in_date": "next fall"})

        result = self.update(updates={"move_in_date": "2026-08-15"})
        self.assertEqual(result["state"]["move_in_date"], "2026-08-15")

    def test_roommate_intent_can_strengthen_budget_assumption(self):
        self.update(updates={"budget_max_per_person": 1200})

        result = self.update(updates={"roommates_open": True})

        self.assertEqual(
            result["state"]["assumptions"],
            [
                {
                    "field": "budget_basis",
                    "assumption": "Budget interpreted as monthly per-person rent.",
                    "confidence": 0.75,
                }
            ],
        )

    def test_delete_user_state_removes_state_and_assumptions(self):
        self.update(
            updates={
                "university": "Temple University",
                "budget_max_per_person": 1000,
            }
        )

        deleted = delete_user_state("session_1", store=self.store)

        self.assertEqual(deleted, {"session_id": "session_1", "deleted": True})
        self.assertIsNone(self.store.get("session_1"))

    def test_missing_critical_fields_include_roommate_intent_when_budget_known(self):
        result = self.update(
            updates={
                "university": "University of Pennsylvania",
                "campus_id": "campus_upenn_university_city",
                "budget_max_per_person": 1300,
            }
        )

        self.assertEqual(result["missing_critical_fields"], ["roommates_open"])


if __name__ == "__main__":
    unittest.main()

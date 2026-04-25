import unittest

from rental_agent.renderer import (
    NEEDS_VERIFICATION_WARNING,
    render_comparison,
    render_initial_setup,
    render_no_results,
    render_ranked_shortlist,
)


class RendererTests(unittest.TestCase):
    def test_initial_setup_renders_budget_assumption_and_move_in_caveat(self):
        rendered = render_initial_setup(
            {
                "university": "Drexel University",
                "budget_max_per_person": 1200,
                "move_in_date": None,
            },
            [{"question": "When do you need to move in?"}],
        )

        self.assertIn("Drexel University", rendered)
        self.assertIn("$1200 max means per person per month", rendered)
        self.assertIn("Before I search", rendered)
        self.assertIn("move-in date", rendered)

    def test_ranked_shortlist_cards_include_required_fields(self):
        rendered = render_ranked_shortlist(
            self.ranking_result(),
            [self.listing("listing_1")],
            {"move_in_date": "2026-08-01"},
        )

        self.assertIn("1. Managed 3BR - balanced student fit", rendered)
        self.assertIn("Cost: about $1100/person monthly, estimated all-in", rendered)
        self.assertIn("Walk to campus: 18 minutes estimated", rendered)
        self.assertIn("Freshness: fresh today", rendered)
        self.assertIn("Why it fits:", rendered)
        self.assertIn("Main trade-off: Balanced option", rendered)
        self.assertIn("Source: https://example.edu/listing_1", rendered)

    def test_ranked_shortlist_renders_needs_verification_warning(self):
        ranking = self.ranking_result(
            freshness_status="needs_verification",
            inline_warnings=[
                "Needs verification: listing should be rechecked before contact.",
            ],
        )

        rendered = render_ranked_shortlist(
            ranking,
            [self.listing("listing_1")],
            {"move_in_date": "2026-08-01"},
        )

        self.assertIn("Freshness: needs verification", rendered)
        self.assertIn(NEEDS_VERIFICATION_WARNING, rendered)

    def test_ranked_shortlist_renders_move_in_caveat_when_unknown(self):
        rendered = render_ranked_shortlist(
            self.ranking_result(),
            [self.listing("listing_1")],
            {"move_in_date": None},
        )

        self.assertIn("move-in date", rendered)
        self.assertIn("genuinely viable", rendered)

    def test_ranked_shortlist_renders_safety_context_without_overclaim(self):
        rendered = render_ranked_shortlist(
            self.ranking_result(ranking_mode="safety_context_first"),
            [self.listing("listing_1")],
            {"move_in_date": "2026-08-01"},
        )
        lowered = rendered.lower()

        self.assertIn("not a guarantee of safety", lowered)
        self.assertNotIn("this area is safe", lowered)
        self.assertNotIn("this area is unsafe", lowered)

    def test_no_results_renders_exclusions_and_move_in_caveat(self):
        rendered = render_no_results(
            {
                "excluded_listings": [
                    {
                        "listing_id": "listing_1",
                        "reasons": ["price basis is unknown"],
                    }
                ]
            },
            {"move_in_date": None},
        )

        self.assertIn("I did not find rankable listings", rendered)
        self.assertIn("price basis is unknown", rendered)
        self.assertIn("move-in date", rendered)

    def test_comparison_renders_best_fits_facts_and_inferences(self):
        rendered = render_comparison(
            {
                "comparison_rows": [
                    {
                        "listing_id": "listing_1",
                        "facts": [
                            {
                                "claim": "All-in estimate is about $1100/person per month.",
                            }
                        ],
                        "inferences": [
                            {
                                "claim": (
                                    "Safety-context fit is based on allowed proxies. "
                                    "This is not a guarantee of safety."
                                ),
                            }
                        ],
                        "warnings": ["Needs verification before contact."],
                    }
                ],
                "best_for_student": "listing_1",
                "best_parent_balanced": "listing_1",
                "main_tradeoffs": ["listing_1 is lower cost."],
                "blocking_unknowns": ["utilities are unknown"],
            }
        )

        self.assertIn("Best fit for you: listing_1", rendered)
        self.assertIn("Best parent-balanced fit: listing_1", rendered)
        self.assertIn("Fact: All-in estimate", rendered)
        self.assertIn("Inference: Safety-context", rendered)
        self.assertIn("utilities are unknown", rendered)

    def test_comparison_blocked_response(self):
        rendered = render_comparison(
            {
                "comparison_rows": [],
                "blocking_unknowns": ["Select at least two listings to compare."],
            }
        )

        self.assertIn("I cannot compare those listings yet", rendered)
        self.assertIn("Select at least two", rendered)

    def test_renderer_blocks_disallowed_safety_phrases(self):
        with self.assertRaisesRegex(AssertionError, "disallowed safety phrase"):
            render_comparison(
                {
                    "comparison_rows": [
                        {
                            "listing_id": "listing_1",
                            "facts": [{"claim": "This area is safe."}],
                            "inferences": [],
                            "warnings": [],
                        }
                    ],
                    "best_for_student": "listing_1",
                    "best_parent_balanced": "listing_1",
                }
            )

    def ranking_result(self, **overrides):
        value = {
            "ranking_mode": "student_default",
            "ranked_listings": [
                {
                    "listing_id": "listing_1",
                    "rank": 1,
                    "fit_label": "balanced student fit",
                    "main_tradeoff": "Balanced option",
                    "inline_warnings": [],
                    "cost_basis": "all_in_estimate_per_person",
                    "cost_per_person_monthly": 1100,
                    "freshness_status": "fresh_today",
                    "source_urls": ["https://example.edu/listing_1"],
                    "score_breakdown": {
                        "all_in_cost": 90,
                        "commute": 80,
                    },
                }
            ],
        }
        value.update(overrides)
        for key, item_value in overrides.items():
            if key in value["ranked_listings"][0]:
                value["ranked_listings"][0][key] = item_value
        return value

    def listing(self, listing_id):
        return {
            "listing_id": listing_id,
            "title": "Managed 3BR",
            "source_urls": [f"https://example.edu/{listing_id}"],
            "walk_minutes_to_campus": 18,
            "managed_or_student_source_signal": True,
            "safety_context_notes": [
                "Context only; this is not a safety guarantee.",
            ],
        }


if __name__ == "__main__":
    unittest.main()

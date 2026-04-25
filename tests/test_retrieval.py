import unittest
from datetime import UTC, datetime

from rental_agent.retrieval import (
    ListingSnapshotStore,
    delete_listing_snapshots,
    retrieve_listings,
)
from rental_agent.sources import SourceRecord


class FakeAdapter:
    def __init__(self, snapshots=None, error=None):
        self.snapshots = snapshots or []
        self.error = error
        self.calls = []

    def retrieve(self, *, source, search_constraints, limit, retrieved_at):
        self.calls.append(
            {
                "source": source,
                "search_constraints": search_constraints,
                "limit": limit,
                "retrieved_at": retrieved_at,
            }
        )
        if self.error:
            raise self.error
        if not isinstance(self.snapshots, list):
            return self.snapshots
        return self.snapshots[:limit]


class RetrieveListingsTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 4, 25, 12, 0, tzinfo=UTC)
        self.store = ListingSnapshotStore()

    def test_default_registry_does_not_invent_listings_without_active_adapter(self):
        result = retrieve_listings(
            "session_1",
            "campus_drexel_university_city",
            {"budget_max_per_person": 1200},
            None,
            10,
            store=self.store,
            now=self.now,
        )

        self.assertEqual(result["listing_snapshots"], [])
        self.assertEqual(result["result_count"], 0)
        self.assertIn(
            {
                "source_id": "drexel_off_campus_housing",
                "error_type": "adapter_not_active",
                "message": "Source adapter status is 'manual_only'; no fetch attempted.",
            },
            result["source_errors"],
        )
        self.assertEqual(self.store.get_for_session("session_1"), [])

    def test_adapter_backed_snapshots_are_validated_limited_and_stored(self):
        source = self.active_source()
        adapter = FakeAdapter(
            snapshots=[
                self.snapshot("listing_1", raw_price="$1,000/person"),
                self.snapshot("listing_2", raw_price="$1,100/person"),
            ]
        )

        result = retrieve_listings(
            "session_1",
            "campus_test",
            {"budget_max_per_person": 1200},
            None,
            1,
            registry=(source,),
            adapters={"test_source": adapter},
            store=self.store,
            now=self.now,
        )

        self.assertEqual(result["result_count"], 1)
        self.assertEqual(result["listing_snapshots"][0]["source_id"], "test_source")
        self.assertEqual(
            result["listing_snapshots"][0]["source_url"],
            "https://example.edu/listing_1",
        )
        self.assertEqual(
            result["listing_snapshots"][0]["freshness_status"],
            "fresh_today",
        )
        self.assertEqual(result["listing_snapshots"][0]["parser_version"], "test-parser")
        self.assertEqual(adapter.calls[0]["limit"], 1)
        self.assertEqual(
            self.store.get_for_session("session_1"),
            result["listing_snapshots"],
        )

    def test_disallowed_sources_are_skipped_before_adapter_can_run(self):
        source = self.disallowed_source()
        adapter = FakeAdapter(snapshots=[self.snapshot("listing_1")])

        result = retrieve_listings(
            "session_1",
            "campus_test",
            {},
            None,
            10,
            registry=(source,),
            adapters={"test_source": adapter},
            store=self.store,
            now=self.now,
        )

        self.assertEqual(result["listing_snapshots"], [])
        self.assertEqual(adapter.calls, [])
        self.assertEqual(
            result["skipped_sources"][0]["reason"],
            "source_allowed_for_v1 is false",
        )

    def test_adapter_errors_are_source_errors_not_empty_results(self):
        source = self.active_source()
        adapter = FakeAdapter(error=RuntimeError("blocked by source"))

        result = retrieve_listings(
            "session_1",
            "campus_test",
            {},
            None,
            10,
            registry=(source,),
            adapters={"test_source": adapter},
            store=self.store,
            now=self.now,
        )

        self.assertEqual(result["listing_snapshots"], [])
        self.assertEqual(
            result["source_errors"],
            [
                {
                    "source_id": "test_source",
                    "error_type": "adapter_error",
                    "message": "RuntimeError: blocked by source",
                }
            ],
        )

    def test_adapter_must_return_list(self):
        source = self.active_source()
        adapter = FakeAdapter(snapshots=self.snapshot("listing_1"))

        result = retrieve_listings(
            "session_1",
            "campus_test",
            {},
            None,
            10,
            registry=(source,),
            adapters={"test_source": adapter},
            store=self.store,
            now=self.now,
        )

        self.assertEqual(result["listing_snapshots"], [])
        self.assertEqual(
            result["source_errors"],
            [
                {
                    "source_id": "test_source",
                    "error_type": "adapter_error",
                    "message": "Adapter must return a list of listing snapshot mappings.",
                }
            ],
        )

    def test_invalid_snapshots_are_rejected(self):
        source = self.active_source()
        adapter = FakeAdapter(
            snapshots=[
                self.snapshot("listing_1", freshness_status="stale"),
                self.snapshot("listing_2", source_id="wrong_source"),
                self.snapshot("listing_3", source_url="https://other.example/listing"),
                self.snapshot("listing_4", source_allowed_for_v1="true"),
                self.snapshot("listing_5", freshness_evidence="fresh"),
                self.snapshot("listing_6", parser_version=1),
                {"source_url": "https://example.edu/missing-id"},
            ]
        )

        result = retrieve_listings(
            "session_1",
            "campus_test",
            {},
            None,
            10,
            registry=(source,),
            adapters={"test_source": adapter},
            store=self.store,
            now=self.now,
        )

        self.assertEqual(result["listing_snapshots"], [])
        self.assertEqual(
            [error["error_type"] for error in result["source_errors"]],
            [
                "snapshot_validation_error",
                "snapshot_validation_error",
                "snapshot_validation_error",
                "snapshot_validation_error",
                "snapshot_validation_error",
                "snapshot_validation_error",
                "snapshot_validation_error",
            ],
        )

    def test_delete_listing_snapshots_removes_session_snapshots(self):
        source = self.active_source()
        adapter = FakeAdapter(snapshots=[self.snapshot("listing_1")])
        retrieve_listings(
            "session_1",
            "campus_test",
            {},
            None,
            5,
            registry=(source,),
            adapters={"test_source": adapter},
            store=self.store,
            now=self.now,
        )

        result = delete_listing_snapshots("session_1", store=self.store)

        self.assertEqual(result, {"session_id": "session_1", "deleted": True})
        self.assertEqual(self.store.get_for_session("session_1"), [])

    def test_naive_datetime_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            retrieve_listings(
                "session_1",
                "campus_test",
                {},
                None,
                5,
                registry=(self.active_source(),),
                now=datetime(2026, 4, 25, 12, 0),
            )

    def test_limit_must_be_positive(self):
        with self.assertRaisesRegex(ValueError, "limit"):
            retrieve_listings(
                "session_1",
                "campus_test",
                {},
                None,
                0,
                registry=(self.active_source(),),
                now=self.now,
            )

    def active_source(self):
        return SourceRecord(
            source_id="test_source",
            source_name="Test Source",
            source_type="official_university_portal",
            base_url="https://example.edu/",
            source_allowed_for_v1=True,
            requires_login=False,
            access_control_notes="Public test source.",
            robots_or_terms_notes="Fixture only.",
            adapter_status="active",
            campus_ids=("campus_test",),
        )

    def disallowed_source(self):
        return SourceRecord(
            source_id="test_source",
            source_name="Test Source",
            source_type="official_university_portal",
            base_url="https://example.edu/",
            source_allowed_for_v1=False,
            requires_login=False,
            access_control_notes="Disallowed fixture.",
            robots_or_terms_notes="Fixture only.",
            adapter_status="active",
            campus_ids=("campus_test",),
        )

    def snapshot(self, listing_id, **overrides):
        value = {
            "snapshot_id": f"snap_{listing_id}",
            "source_id": "test_source",
            "source_url": f"https://example.edu/{listing_id}",
            "source_listing_id": listing_id,
            "raw_title": f"Listing {listing_id}",
            "raw_price": "$1,000",
            "raw_location": "University City",
            "raw_html_hash": "hash",
            "retrieved_at": "2026-04-25T12:00:00Z",
            "freshness_status": "fresh_today",
            "freshness_evidence": ["Adapter fixture marked fresh."],
            "parser_version": "test-parser",
            "source_allowed_for_v1": True,
        }
        value.update(overrides)
        return value


if __name__ == "__main__":
    unittest.main()

"""Student Rental Agent prototype runtime."""

from rental_agent.campus import get_campus_context
from rental_agent.comparison import compare_listings
from rental_agent.enrichment import enrich_listings
from rental_agent.ranking import rank_listings
from rental_agent.renderer import (
    render_comparison,
    render_initial_setup,
    render_no_results,
    render_ranked_shortlist,
)
from rental_agent.retrieval import (
    DEFAULT_LISTING_STORE,
    ListingSnapshot,
    ListingSnapshotStore,
    delete_listing_snapshots,
    retrieve_listings,
)
from rental_agent.sources import (
    SOURCE_REGISTRY,
    SourcePolicy,
    SourceRecord,
    get_source_registry,
    select_sources_for_retrieval,
)
from rental_agent.state import (
    DEFAULT_STORE,
    SessionStateStore,
    delete_user_state,
    update_user_state,
)

__all__ = [
    "DEFAULT_STORE",
    "DEFAULT_LISTING_STORE",
    "SOURCE_REGISTRY",
    "ListingSnapshot",
    "ListingSnapshotStore",
    "SessionStateStore",
    "SourcePolicy",
    "SourceRecord",
    "compare_listings",
    "delete_listing_snapshots",
    "delete_user_state",
    "enrich_listings",
    "get_campus_context",
    "get_source_registry",
    "rank_listings",
    "render_comparison",
    "render_initial_setup",
    "render_no_results",
    "render_ranked_shortlist",
    "retrieve_listings",
    "select_sources_for_retrieval",
    "update_user_state",
]

"""Comparison helper for selected enriched rental listings."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from rental_agent.ranking import rank_listings


COMPARISON_VERSION = "comparison-v1"

COMPARISON_DIMENSIONS = {
    "cost",
    "commute",
    "freshness",
    "student_fit",
    "parent_explainability",
    "lease",
    "safety_context_fit",
    "overall",
}

BLOCKING_FRESHNESS_STATUSES = {"stale", "removed", "unknown"}


def compare_listings(
    session_id: str,
    listing_ids: list[str],
    comparison_dimensions: list[str],
    user_state: dict[str, Any],
    listings: list[dict[str, Any]] | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Compare selected enriched listings without inventing missing facts."""

    if not session_id:
        raise ValueError("session_id is required")
    if not isinstance(user_state, dict):
        raise ValueError("user_state must be a mapping")

    created_at = _utc_now(now)
    dimensions = _normalize_dimensions(comparison_dimensions)
    if not isinstance(listing_ids, list) or len(listing_ids) < 2:
        return _blocked_response(
            session_id,
            dimensions,
            created_at,
            ["Select at least two listings to compare."],
        )
    if not isinstance(listings, list) or not listings:
        return _blocked_response(
            session_id,
            dimensions,
            created_at,
            ["Comparable listing records are missing."],
        )

    listing_by_id = {
        listing.get("listing_id"): deepcopy(listing)
        for listing in listings
        if isinstance(listing, dict)
    }
    selected: list[dict[str, Any]] = []
    blocking_unknowns: list[str] = []

    for listing_id in listing_ids:
        if not isinstance(listing_id, str) or not listing_id:
            blocking_unknowns.append("Selected listing ID is missing.")
            continue
        listing = listing_by_id.get(listing_id)
        if listing is None:
            blocking_unknowns.append(f"{listing_id}: listing record is missing.")
            continue
        selected.append(listing)
        blocking_unknowns.extend(_blocking_unknowns(listing))

    if blocking_unknowns:
        return _blocked_response(session_id, dimensions, created_at, blocking_unknowns)

    student_ranking = rank_listings(
        session_id,
        selected,
        user_state,
        "student_default",
        len(selected),
        now=now,
    )
    parent_ranking = rank_listings(
        session_id,
        selected,
        user_state,
        "parent_balanced",
        len(selected),
        now=now,
    )
    rows = [_comparison_row(listing, dimensions) for listing in selected]
    best_for_student = _first_ranked_listing_id(student_ranking)
    best_parent_balanced = _first_ranked_listing_id(parent_ranking)

    return {
        "comparison_id": _comparison_id(session_id, listing_ids, created_at),
        "session_id": session_id,
        "comparison_dimensions": dimensions,
        "comparison_rows": rows,
        "best_for_student": best_for_student,
        "best_parent_balanced": best_parent_balanced,
        "main_tradeoffs": _main_tradeoffs(
            selected,
            best_for_student,
            best_parent_balanced,
        ),
        "blocking_unknowns": _non_blocking_unknowns(selected, user_state),
        "confidence": _comparison_confidence(rows),
        "created_at": created_at,
        "comparison_version": COMPARISON_VERSION,
    }


def _comparison_row(listing: dict[str, Any], dimensions: list[str]) -> dict[str, Any]:
    claims: list[dict[str, Any]] = []
    inferences: list[dict[str, Any]] = []

    if _include_dimension(dimensions, "cost"):
        claims.append(_cost_claim(listing))
    if _include_dimension(dimensions, "commute"):
        claims.append(_commute_claim(listing))
    if _include_dimension(dimensions, "freshness"):
        claims.append(_freshness_claim(listing))
    if _include_dimension(dimensions, "student_fit"):
        claims.append(_student_fit_claim(listing))
    if _include_dimension(dimensions, "lease"):
        claims.extend(_lease_claims(listing))
    if _include_dimension(dimensions, "parent_explainability"):
        inferences.append(_parent_inference(listing))
    if _include_dimension(dimensions, "safety_context_fit"):
        inferences.append(_safety_context_inference(listing))

    row = {
        "listing_id": listing["listing_id"],
        "title": listing.get("title"),
        "source_urls": deepcopy(listing.get("source_urls", [])),
        "facts": claims,
        "inferences": inferences,
        "warnings": _row_warnings(listing),
        "confidence": _row_confidence(listing, claims, inferences),
    }
    _assert_safe_language(row)
    return row


def _cost_claim(listing: dict[str, Any]) -> dict[str, Any]:
    all_in = _optional_number(listing.get("all_in_estimate_per_person"))
    rent = _optional_number(listing.get("rent_per_person_monthly"))
    if all_in is not None:
        claim = f"All-in estimate is about ${all_in:g}/person per month."
    else:
        claim = f"Rent is about ${rent:g}/person per month; all-in cost is incomplete."
    return _tool_fact("cost", claim, listing)


def _commute_claim(listing: dict[str, Any]) -> dict[str, Any]:
    walk_minutes = _optional_number(listing.get("walk_minutes_to_campus"))
    if walk_minutes is None:
        claim = "Approximate walking commute is not available."
    else:
        claim = f"Approximate walking commute is {walk_minutes:g} minutes."
    return _tool_fact("commute", claim, listing)


def _freshness_claim(listing: dict[str, Any]) -> dict[str, Any]:
    return _tool_fact(
        "freshness",
        f"Freshness status is {listing.get('freshness_status')}.",
        listing,
    )


def _student_fit_claim(listing: dict[str, Any]) -> dict[str, Any]:
    fit = _optional_number(listing.get("student_area_fit"))
    if fit is None:
        claim = "Student-area fit proxy is not available."
    else:
        claim = f"Student-area fit proxy is {fit:.2f}."
    return _tool_fact("student_fit", claim, listing)


def _lease_claims(listing: dict[str, Any]) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    lease_terms = listing.get("lease_terms")
    if isinstance(lease_terms, list) and lease_terms:
        claims.append(
            _tool_fact("lease", "Lease terms: " + ", ".join(lease_terms), listing)
        )
    else:
        claims.append(_tool_fact("lease", "Lease terms are unknown.", listing))
    available_date = listing.get("available_date")
    if isinstance(available_date, str) and available_date:
        claims.append(
            _tool_fact("lease", f"Available date is {available_date}.", listing)
        )
    return claims


def _parent_inference(listing: dict[str, Any]) -> dict[str, Any]:
    notes = _string_notes(listing.get("parent_explainability_notes"))
    if notes:
        claim = "Parent-balanced explainability is stronger because " + "; ".join(notes)
    else:
        claim = "Parent-balanced explainability has limited supporting context."
    return _model_inference("parent_explainability", claim, notes, listing)


def _safety_context_inference(listing: dict[str, Any]) -> dict[str, Any]:
    notes = _string_notes(listing.get("safety_context_notes"))
    if notes:
        claim = "Safety-context fit is based on allowed proxies: " + "; ".join(notes)
    else:
        claim = "Safety-context fit has limited supporting proxy context."
    claim += " This is not a guarantee of safety."
    return _model_inference("safety_context_fit", claim, notes, listing)


def _tool_fact(dimension: str, claim: str, listing: dict[str, Any]) -> dict[str, Any]:
    return {
        "dimension": dimension,
        "claim": claim,
        "claim_type": "tool_fact",
        "source_tool": "enrich_listings",
        "confidence": _optional_number(listing.get("confidence")) or 0.5,
    }


def _model_inference(
    dimension: str,
    claim: str,
    based_on: list[str],
    listing: dict[str, Any],
) -> dict[str, Any]:
    return {
        "dimension": dimension,
        "claim": claim,
        "claim_type": "model_inference",
        "based_on": based_on,
        "confidence": min(
            0.85,
            (_optional_number(listing.get("confidence")) or 0.5) + 0.05,
        ),
    }


def _blocking_unknowns(listing: dict[str, Any]) -> list[str]:
    listing_id = listing.get("listing_id", "<unknown>")
    unknowns: list[str] = []
    freshness_status = listing.get("freshness_status")
    if freshness_status in BLOCKING_FRESHNESS_STATUSES:
        unknowns.append(f"{listing_id}: freshness_status is {freshness_status}.")
    elif freshness_status not in {
        "fresh_today",
        "needs_verification",
        "seen_within_7_days",
    }:
        unknowns.append(f"{listing_id}: freshness_status is missing or unsupported.")
    if listing.get("price_basis") in (None, "", "unknown"):
        unknowns.append(f"{listing_id}: price basis is unknown.")
    if _optional_number(listing.get("rent_per_person_monthly")) is None:
        unknowns.append(f"{listing_id}: rent per person is missing.")
    if not (listing.get("address_raw") or listing.get("address_normalized")):
        unknowns.append(f"{listing_id}: usable location is missing.")
    return unknowns


def _non_blocking_unknowns(
    selected: list[dict[str, Any]],
    user_state: dict[str, Any],
) -> list[str]:
    unknowns: list[str] = []
    if not user_state.get("move_in_date"):
        unknowns.append("Move-in date is unknown, so neither listing is contact-ready.")
    for listing in selected:
        listing_id = listing["listing_id"]
        if listing.get("utilities_status") == "unknown":
            unknowns.append(f"{listing_id}: utilities are unknown.")
        if listing.get("fees_status") == "unknown":
            unknowns.append(f"{listing_id}: recurring fees are unknown.")
        if listing.get("freshness_status") != "fresh_today":
            unknowns.append(f"{listing_id}: same-day freshness needs verification.")
    return unknowns


def _row_warnings(listing: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if listing.get("freshness_status") != "fresh_today":
        warnings.append("Needs verification before contact.")
    if listing.get("all_in_estimate_per_person") is None:
        warnings.append("All-in monthly cost is incomplete.")
    if _optional_number(listing.get("walk_minutes_to_campus")) is None:
        warnings.append("Approximate walking commute is missing.")
    return warnings


def _main_tradeoffs(
    selected: list[dict[str, Any]],
    best_for_student: str | None,
    best_parent_balanced: str | None,
) -> list[str]:
    tradeoffs: list[str] = []
    cheapest = min(selected, key=lambda listing: _cost_value(listing) or float("inf"))
    shortest = min(
        selected,
        key=lambda listing: _optional_number(listing.get("walk_minutes_to_campus"))
        or float("inf"),
    )
    if (
        best_for_student
        and best_parent_balanced
        and best_for_student != best_parent_balanced
    ):
        tradeoffs.append(
            "Best-for-student differs from parent-balanced: "
            f"{best_for_student} vs {best_parent_balanced}."
        )
    if cheapest["listing_id"] != shortest["listing_id"]:
        tradeoffs.append(
            f"{cheapest['listing_id']} is lower cost, while "
            f"{shortest['listing_id']} has the shorter approximate walk."
        )
    if not tradeoffs:
        tradeoffs.append(
            "The selected listings are close on the compared v1 dimensions."
        )
    return tradeoffs


def _blocked_response(
    session_id: str,
    dimensions: list[str],
    created_at: str,
    blocking_unknowns: list[str],
) -> dict[str, Any]:
    return {
        "comparison_id": _comparison_id(session_id, [], created_at),
        "session_id": session_id,
        "comparison_dimensions": dimensions,
        "comparison_rows": [],
        "best_for_student": None,
        "best_parent_balanced": None,
        "main_tradeoffs": [],
        "blocking_unknowns": blocking_unknowns,
        "confidence": 0,
        "created_at": created_at,
        "comparison_version": COMPARISON_VERSION,
    }


def _normalize_dimensions(value: list[str]) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError("comparison_dimensions must include at least one dimension")
    invalid = set(value) - COMPARISON_DIMENSIONS
    if invalid:
        invalid_list = ", ".join(sorted(invalid))
        raise ValueError(f"unsupported comparison dimension(s): {invalid_list}")
    normalized = []
    for dimension in value:
        if dimension not in normalized:
            normalized.append(dimension)
    return normalized


def _include_dimension(dimensions: list[str], dimension: str) -> bool:
    return "overall" in dimensions or dimension in dimensions


def _first_ranked_listing_id(ranking: dict[str, Any]) -> str | None:
    if not ranking["ranked_listings"]:
        return None
    return ranking["ranked_listings"][0]["listing_id"]


def _comparison_confidence(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0
    return round(sum(row["confidence"] for row in rows) / len(rows), 2)


def _row_confidence(
    listing: dict[str, Any],
    claims: list[dict[str, Any]],
    inferences: list[dict[str, Any]],
) -> float:
    base = _optional_number(listing.get("confidence")) or 0.5
    missing_penalty = len(_row_warnings(listing)) * 0.04
    sparse_penalty = 0 if claims or inferences else 0.1
    return max(0.1, min(0.95, round(base - missing_penalty - sparse_penalty, 2)))


def _cost_value(listing: dict[str, Any]) -> float | None:
    all_in = _optional_number(listing.get("all_in_estimate_per_person"))
    if all_in is not None:
        return all_in
    return _optional_number(listing.get("rent_per_person_monthly"))


def _string_notes(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _comparison_id(session_id: str, listing_ids: list[str], created_at: str) -> str:
    key = f"{session_id}:{','.join(listing_ids)}:{created_at}"
    return "comparison_" + sha256(key.encode("utf-8")).hexdigest()[:12]


def _optional_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _assert_safe_language(row: dict[str, Any]) -> None:
    rendered = str(row).lower()
    if "this area is safe" in rendered or "this area is unsafe" in rendered:
        raise AssertionError("comparison output must not make safe/unsafe area claims")


def _utc_now(now: datetime | None = None) -> str:
    value = now or datetime.now(UTC)
    if value.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

"""User-facing response templates for the v1 prototype."""

from __future__ import annotations

from typing import Any


NEEDS_VERIFICATION_WARNING = (
    "Needs verification: I found this in a recent source snapshot, but I could "
    "not confirm same-day availability. I would not contact the landlord until "
    "this is rechecked."
)

NO_RESULTS_MESSAGE = (
    "I did not find rankable listings from the allowed v1 sources with those "
    "constraints. I can widen the budget, widen the walk radius, include more "
    "property-manager sources, or keep the same constraints and retry later."
)

MOVE_IN_CAVEAT = (
    "I can search broadly without your move-in date, but I will need it before "
    "treating any listing as genuinely viable."
)

SAFETY_CONTEXT_NOTE = (
    "Safety context: This looks stronger for your concern only when allowed "
    "context proxies support it. This is not a guarantee of safety."
)

BLOCKED_SAFETY_PHRASES = (
    "this area is safe",
    "this area is unsafe",
    "safest option",
    "safe at night",
    "your parents should not worry",
)


def render_initial_setup(
    state: dict[str, Any],
    questions: list[dict[str, Any]] | None = None,
) -> str:
    """Render the setup response after state and campus context are known."""

    university = state.get("university") or "that campus"
    budget = state.get("budget_max_per_person")
    lines = [f"I can start with {university}."]
    if budget is not None:
        lines.append(
            f"I am assuming your ${_format_number(budget)} max means per person per month."
        )

    questions = questions or []
    if questions:
        lines.append("")
        lines.append("Before I search, I need one thing: " + questions[0]["question"])

    if not state.get("move_in_date"):
        lines.append("")
        lines.append(MOVE_IN_CAVEAT)

    return _checked_response("\n".join(lines))


def render_ranked_shortlist(
    ranking_result: dict[str, Any],
    listings: list[dict[str, Any]],
    user_state: dict[str, Any],
) -> str:
    """Render ranked listing cards from rank_listings output."""

    ranked = ranking_result.get("ranked_listings") or []
    if not ranked:
        return render_no_results(ranking_result, user_state)

    listing_by_id = {
        listing.get("listing_id"): listing
        for listing in listings
        if isinstance(listing, dict)
    }
    lines = ["Here are the strongest ranked options from the verified tool outputs:"]

    for ranked_listing in ranked:
        listing = listing_by_id.get(ranked_listing["listing_id"], {})
        lines.append("")
        lines.extend(_ranked_card_lines(ranked_listing, listing))

    if any(_needs_verification(item) for item in ranked):
        lines.append("")
        lines.append(NEEDS_VERIFICATION_WARNING)

    if not user_state.get("move_in_date"):
        lines.append("")
        lines.append(MOVE_IN_CAVEAT)

    if _uses_safety_context(ranking_result, listings):
        lines.append("")
        lines.append(SAFETY_CONTEXT_NOTE)

    return _checked_response("\n".join(lines))


def render_no_results(
    ranking_result: dict[str, Any] | None = None,
    user_state: dict[str, Any] | None = None,
) -> str:
    """Render a no-rankable-listings response with relevant caveats."""

    lines = [NO_RESULTS_MESSAGE]
    excluded = (ranking_result or {}).get("excluded_listings") or []
    if excluded:
        lines.append("")
        lines.append("Excluded or blocked examples:")
        for item in excluded[:3]:
            reasons = item.get("reasons") or [item.get("reason", "not rankable")]
            lines.append(
                f"- {item.get('listing_id') or 'unknown listing'}: {', '.join(reasons)}"
            )
    if user_state is not None and not user_state.get("move_in_date"):
        lines.append("")
        lines.append(MOVE_IN_CAVEAT)
    return _checked_response("\n".join(lines))


def render_comparison(comparison_result: dict[str, Any]) -> str:
    """Render selected-listing comparison output."""

    rows = comparison_result.get("comparison_rows") or []
    if not rows:
        unknowns = comparison_result.get("blocking_unknowns") or [
            "I need at least two comparable listings."
        ]
        lines = ["I cannot compare those listings yet."]
        lines.extend(f"- {unknown}" for unknown in unknowns)
        return _checked_response("\n".join(lines))

    best_for_student = _value_or_unknown(comparison_result.get("best_for_student"))
    lines = [
        f"Best fit for you: {best_for_student}",
        "Best parent-balanced fit: "
        + _value_or_unknown(comparison_result.get("best_parent_balanced")),
        "",
    ]

    tradeoffs = comparison_result.get("main_tradeoffs") or []
    if tradeoffs:
        lines.append("The real trade-off is " + tradeoffs[0])

    blocking_unknowns = comparison_result.get("blocking_unknowns") or []
    if blocking_unknowns:
        lines.append(
            "I would verify "
            + "; ".join(blocking_unknowns)
            + " before treating either as ready to contact."
        )

    lines.append("")
    lines.append("Comparison details:")
    for row in rows:
        lines.append(f"- {row['listing_id']}:")
        for fact in row.get("facts", [])[:4]:
            lines.append(f"  Fact: {fact['claim']}")
        for inference in row.get("inferences", [])[:2]:
            lines.append(f"  Inference: {inference['claim']}")
        for warning in row.get("warnings", []):
            lines.append(f"  Warning: {warning}")

    return _checked_response("\n".join(lines))


def _ranked_card_lines(
    ranked_listing: dict[str, Any],
    listing: dict[str, Any],
) -> list[str]:
    title = listing.get("title") or ranked_listing["listing_id"]
    rank = ranked_listing.get("rank") or "?"
    fit_label = ranked_listing.get("fit_label") or "ranked fit"
    cost = _cost_line(ranked_listing)
    commute = _commute_line(listing)
    freshness = _freshness_line(ranked_listing)
    why = _why_it_fits_line(ranked_listing, listing)
    tradeoff = ranked_listing.get("main_tradeoff") or "No major trade-off provided."
    source = _source_line(ranked_listing, listing)

    lines = [
        f"{rank}. {title} - {fit_label}",
        f"Cost: {cost}",
        f"Walk to campus: {commute}",
        f"Freshness: {freshness}",
        f"Why it fits: {why}",
        f"Main trade-off: {tradeoff}",
        f"Source: {source}",
    ]
    for warning in ranked_listing.get("inline_warnings", []):
        lines.append(f"Warning: {warning}")
    return lines


def _cost_line(ranked_listing: dict[str, Any]) -> str:
    value = _optional_number(ranked_listing.get("cost_per_person_monthly"))
    basis = ranked_listing.get("cost_basis")
    if value is None:
        return "Cost unavailable from tool output."
    if basis == "all_in_estimate_per_person":
        return f"about ${_format_number(value)}/person monthly, estimated all-in"
    return f"about ${_format_number(value)}/person monthly, rent-only"


def _commute_line(listing: dict[str, Any]) -> str:
    minutes = _optional_number(listing.get("walk_minutes_to_campus"))
    if minutes is None:
        return "not available from tool output"
    return f"{_format_number(minutes)} minutes estimated"


def _freshness_line(ranked_listing: dict[str, Any]) -> str:
    status = ranked_listing.get("freshness_status") or "unknown"
    if status == "fresh_today":
        return "fresh today"
    if status in {"needs_verification", "seen_within_7_days"}:
        return "needs verification"
    return status.replace("_", " ")


def _why_it_fits_line(
    ranked_listing: dict[str, Any],
    listing: dict[str, Any],
) -> str:
    breakdown = ranked_listing.get("score_breakdown") or {}
    strongest = sorted(breakdown.items(), key=lambda item: item[1], reverse=True)[:2]
    parts = [
        f"{name.replace('_', ' ')} scored {_format_number(score)}"
        for name, score in strongest
    ]
    if listing.get("managed_or_student_source_signal"):
        parts.append("source passed the v1 public-source policy")
    return "; ".join(parts) if parts else "ranking score came from tool output"


def _source_line(ranked_listing: dict[str, Any], listing: dict[str, Any]) -> str:
    urls = ranked_listing.get("source_urls") or listing.get("source_urls") or []
    if urls:
        return urls[0]
    return "source URL missing from renderer input"


def _needs_verification(ranked_listing: dict[str, Any]) -> bool:
    if ranked_listing.get("freshness_status") in {
        "needs_verification",
        "seen_within_7_days",
    }:
        return True
    warnings = " ".join(ranked_listing.get("inline_warnings", [])).lower()
    return "needs verification" in warnings


def _uses_safety_context(
    ranking_result: dict[str, Any],
    listings: list[dict[str, Any]],
) -> bool:
    if ranking_result.get("ranking_mode") in {"safety_context_first", "parent_balanced"}:
        return True
    return any(listing.get("safety_context_notes") for listing in listings)


def _checked_response(value: str) -> str:
    lowered = value.lower()
    for phrase in BLOCKED_SAFETY_PHRASES:
        if phrase in lowered:
            raise AssertionError(f"response contains disallowed safety phrase: {phrase}")
    return value


def _optional_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _format_number(value: Any) -> str:
    number = _optional_number(value)
    if number is None:
        return str(value)
    return str(int(number)) if number.is_integer() else f"{number:g}"


def _value_or_unknown(value: Any) -> str:
    if isinstance(value, str) and value:
        return value
    return "unknown"

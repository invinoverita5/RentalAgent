"""Fixed-preset ranking for enriched v1 rental listings."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any


RANKING_VERSION = "ranking-v1"

RANKING_PRESETS: dict[str, dict[str, float]] = {
    "student_default": {
        "all_in_cost": 0.28,
        "commute": 0.24,
        "student_area_fit": 0.20,
        "freshness": 0.14,
        "listing_quality": 0.10,
        "parent_explainability": 0.04,
    },
    "budget_first": {
        "all_in_cost": 0.42,
        "commute": 0.18,
        "freshness": 0.14,
        "student_area_fit": 0.12,
        "listing_quality": 0.10,
        "parent_explainability": 0.04,
    },
    "commute_first": {
        "commute": 0.40,
        "all_in_cost": 0.22,
        "freshness": 0.14,
        "student_area_fit": 0.12,
        "listing_quality": 0.08,
        "parent_explainability": 0.04,
    },
    "safety_context_first": {
        "safety_context_fit": 0.30,
        "commute": 0.24,
        "all_in_cost": 0.18,
        "freshness": 0.14,
        "student_area_fit": 0.08,
        "listing_quality": 0.06,
    },
    "parent_balanced": {
        "parent_explainability": 0.24,
        "safety_context_fit": 0.22,
        "freshness": 0.18,
        "commute": 0.18,
        "all_in_cost": 0.14,
        "student_area_fit": 0.04,
    },
}

FRESHNESS_SCORES = {
    "fresh_today": 100.0,
    "needs_verification": 62.0,
    "seen_within_7_days": 58.0,
}

EXCLUDED_FRESHNESS_STATUSES = {"stale", "removed", "unknown"}
VALID_DEDUPE_STATUSES = {"unique", "merged", "possible_duplicate", "unknown"}


def rank_listings(
    session_id: str,
    listings: list[dict[str, Any]],
    user_state: dict[str, Any],
    ranking_mode: str,
    top_n: int,
    allow_stretch_budget: bool = False,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Rank enriched listings with fixed v1 presets and explicit caveats."""

    if not session_id:
        raise ValueError("session_id is required")
    if not isinstance(listings, list) or not listings:
        raise ValueError("listings must include at least one listing")
    if not isinstance(user_state, dict):
        raise ValueError("user_state must be a mapping")
    if ranking_mode not in RANKING_PRESETS:
        raise ValueError(f"unsupported ranking_mode: {ranking_mode}")
    if not isinstance(top_n, int) or top_n <= 0:
        raise ValueError("top_n must be a positive integer")
    if not isinstance(allow_stretch_budget, bool):
        raise ValueError("allow_stretch_budget must be a boolean")

    created_at = _utc_now(now)
    normalized_listings = [deepcopy(listing) for listing in listings]
    rankable: list[dict[str, Any]] = []
    excluded_listings: list[dict[str, Any]] = []

    for listing in normalized_listings:
        reasons = _hard_exclusion_reasons(
            listing,
            user_state,
            allow_stretch_budget,
        )
        if reasons:
            excluded_listings.append(
                {
                    "listing_id": listing.get("listing_id"),
                    "reasons": reasons,
                }
            )
            continue
        rankable.append(listing)

    ranked_candidates = [
        _ranked_candidate(listing, user_state, ranking_mode, allow_stretch_budget)
        for listing in rankable
    ]
    ranked_candidates.sort(key=lambda item: (-item["score"], item["listing_id"]))

    ranked_listings = []
    for index, candidate in enumerate(ranked_candidates[:top_n], start=1):
        candidate["rank"] = index
        ranked_listings.append(candidate)

    return {
        "ranking_id": _ranking_id(session_id, ranking_mode, created_at),
        "session_id": session_id,
        "ranking_mode": ranking_mode,
        "ranked_listings": ranked_listings,
        "excluded_listings": excluded_listings,
        "ranking_weights": deepcopy(RANKING_PRESETS[ranking_mode]),
        "missing_data_penalties": _missing_data_penalties(ranked_candidates),
        "confidence": _ranking_confidence(ranked_listings),
        "created_at": created_at,
        "ranking_version": RANKING_VERSION,
    }


def _ranked_candidate(
    listing: dict[str, Any],
    user_state: dict[str, Any],
    ranking_mode: str,
    allow_stretch_budget: bool,
) -> dict[str, Any]:
    features = _feature_scores(listing, user_state)
    weights = RANKING_PRESETS[ranking_mode]
    raw_score = sum(features[feature] * weight for feature, weight in weights.items())
    penalty = _optional_number(listing.get("missing_data_penalty")) or 0
    score = max(0.0, round(raw_score - (penalty * 15), 2))
    warnings = _inline_warnings(listing, user_state, allow_stretch_budget)

    return {
        "listing_id": listing["listing_id"],
        "rank": None,
        "score": score,
        "score_breakdown": {feature: round(features[feature], 2) for feature in weights},
        "hard_filter_passed": True,
        "fit_label": _fit_label(ranking_mode),
        "main_tradeoff": _main_tradeoff(listing, warnings, features),
        "inline_warnings": warnings,
        "cost_basis": _cost_basis(listing),
        "cost_per_person_monthly": _cost_value(listing),
        "freshness_status": listing["freshness_status"],
        "source_urls": _source_urls(listing),
        "missing_data_penalty": round(penalty, 2),
        "confidence": _candidate_confidence(listing, warnings),
    }


def _feature_scores(
    listing: dict[str, Any],
    user_state: dict[str, Any],
) -> dict[str, float]:
    commute_score = _commute_score(listing.get("walk_minutes_to_campus"), user_state)
    source_signal = bool(listing.get("managed_or_student_source_signal"))
    student_area_score = _student_area_score(listing.get("student_area_fit"))

    return {
        "all_in_cost": _cost_score(_cost_value(listing), user_state),
        "commute": commute_score,
        "student_area_fit": student_area_score,
        "freshness": _freshness_score(listing.get("freshness_status")),
        "listing_quality": _listing_quality_score(listing),
        "parent_explainability": _parent_explainability_score(listing),
        "safety_context_fit": _safety_context_fit_score(
            commute_score,
            student_area_score,
            source_signal,
            listing.get("safety_context_notes", []),
        ),
    }


def _hard_exclusion_reasons(
    listing: dict[str, Any],
    user_state: dict[str, Any],
    allow_stretch_budget: bool,
) -> list[str]:
    reasons: list[str] = []

    listing_id = listing.get("listing_id")
    if not isinstance(listing_id, str) or not listing_id:
        reasons.append("listing_id is missing")

    freshness_status = listing.get("freshness_status")
    if freshness_status in EXCLUDED_FRESHNESS_STATUSES:
        reasons.append(f"freshness_status is {freshness_status}")
    elif freshness_status not in FRESHNESS_SCORES:
        reasons.append("freshness_status is missing or unsupported")

    if listing.get("source_allowed_for_v1") is False:
        reasons.append("source_allowed_for_v1 is false")
    if not _source_urls(listing):
        reasons.append("source URL is missing")

    price_basis = listing.get("price_basis")
    if price_basis in (None, "", "unknown"):
        reasons.append("price basis is unknown")
    if _cost_value(listing) is None:
        reasons.append("per-person cost is missing")
    if any(
        blocker in {"unknown_price_basis", "missing_per_person_rent"}
        for blocker in listing.get("ranking_blockers", [])
    ):
        reasons.append("listing has price ranking blockers")

    if not _has_usable_location(listing):
        reasons.append("usable location is missing")
    if listing.get("dedupe_status") not in VALID_DEDUPE_STATUSES:
        reasons.append("dedupe status is missing")

    budget_max = _optional_number(user_state.get("budget_max_per_person"))
    cost = _cost_value(listing)
    if (
        budget_max is not None
        and cost is not None
        and cost > budget_max
        and not allow_stretch_budget
    ):
        reasons.append("cost exceeds budget_max_per_person")

    commute_max = _optional_number(user_state.get("commute_max_minutes"))
    walk_minutes = _optional_number(listing.get("walk_minutes_to_campus"))
    if (
        commute_max is not None
        and walk_minutes is not None
        and walk_minutes > commute_max
    ):
        reasons.append("walk_minutes_to_campus exceeds commute_max_minutes")

    return reasons


def _inline_warnings(
    listing: dict[str, Any],
    user_state: dict[str, Any],
    allow_stretch_budget: bool,
) -> list[str]:
    warnings: list[str] = []
    if listing["freshness_status"] in {"needs_verification", "seen_within_7_days"}:
        warnings.append(
            "Needs verification: listing should be rechecked before contact."
        )
    if listing.get("utilities_status") == "unknown":
        warnings.append("Utilities unknown: cost is rent-only.")
    if listing.get("fees_status") == "unknown":
        warnings.append("Fees unknown: all-in cost may be incomplete.")
    if not user_state.get("move_in_date"):
        warnings.append("Move-in date unknown: do not treat as contact-ready.")

    budget_max = _optional_number(user_state.get("budget_max_per_person"))
    cost = _cost_value(listing)
    if (
        allow_stretch_budget
        and budget_max is not None
        and cost is not None
        and cost > budget_max
    ):
        warnings.append("Stretch budget: cost is above budget_max_per_person.")
    return warnings


def _source_urls(listing: dict[str, Any]) -> list[str]:
    source_urls = listing.get("source_urls")
    if isinstance(source_urls, list) and all(
        isinstance(url, str) for url in source_urls
    ):
        return [url for url in source_urls if url]
    source_url = listing.get("source_url")
    if isinstance(source_url, str) and source_url:
        return [source_url]
    return []


def _has_usable_location(listing: dict[str, Any]) -> bool:
    if listing.get("address_normalized") or listing.get("address_raw"):
        return True
    return _optional_number(listing.get("lat")) is not None and _optional_number(
        listing.get("lng")
    ) is not None


def _cost_value(listing: dict[str, Any]) -> float | None:
    all_in = _optional_number(listing.get("all_in_estimate_per_person"))
    if all_in is not None:
        return all_in
    return _optional_number(listing.get("rent_per_person_monthly"))


def _cost_basis(listing: dict[str, Any]) -> str:
    if _optional_number(listing.get("all_in_estimate_per_person")) is not None:
        return "all_in_estimate_per_person"
    return "rent_only_per_person"


def _cost_score(cost: float | None, user_state: dict[str, Any]) -> float:
    if cost is None:
        return 0

    budget_target = _optional_number(user_state.get("budget_target_per_person"))
    budget_max = _optional_number(user_state.get("budget_max_per_person"))
    if (
        budget_target is not None
        and budget_max is not None
        and budget_max > budget_target
    ):
        if cost <= budget_target:
            return 100
        if cost <= budget_max:
            stretch = (cost - budget_target) / (budget_max - budget_target)
            return max(55, 100 - (stretch * 35))
        overage = (cost - budget_max) / budget_max
        return max(20, 55 - (overage * 80))
    if budget_max is not None:
        if cost <= budget_max:
            return max(55, 100 - ((cost / budget_max) * 35))
        overage = (cost - budget_max) / budget_max
        return max(20, 55 - (overage * 80))
    return max(20, 100 - (cost / 2500 * 55))


def _commute_score(value: Any, user_state: dict[str, Any]) -> float:
    walk_minutes = _optional_number(value)
    if walk_minutes is None:
        return 35

    commute_max = _optional_number(user_state.get("commute_max_minutes"))
    if commute_max is not None and commute_max > 0:
        if walk_minutes <= commute_max:
            return max(55, 100 - ((walk_minutes / commute_max) * 35))
        overage = (walk_minutes - commute_max) / commute_max
        return max(20, 55 - (overage * 60))

    if walk_minutes <= 10:
        return 100
    if walk_minutes <= 20:
        return 86
    if walk_minutes <= 30:
        return 68
    if walk_minutes <= 45:
        return 45
    return 25


def _student_area_score(value: Any) -> float:
    student_area_fit = _optional_number(value)
    if student_area_fit is None:
        return 45
    if student_area_fit <= 1:
        return max(0, min(100, student_area_fit * 100))
    return max(0, min(100, student_area_fit))


def _freshness_score(value: Any) -> float:
    if not isinstance(value, str):
        return 0
    return FRESHNESS_SCORES.get(value, 0)


def _listing_quality_score(listing: dict[str, Any]) -> float:
    confidence = _optional_number(listing.get("confidence")) or 0.5
    penalty = _optional_number(listing.get("missing_data_penalty")) or 0
    return max(0, min(100, (confidence * 100) - (penalty * 35)))


def _parent_explainability_score(listing: dict[str, Any]) -> float:
    notes = listing.get("parent_explainability_notes")
    note_count = len(notes) if isinstance(notes, list) else 0
    source_bonus = 15 if listing.get("managed_or_student_source_signal") else 0
    freshness_bonus = 10 if listing.get("freshness_status") == "fresh_today" else 0
    return min(100, 45 + source_bonus + freshness_bonus + (note_count * 10))


def _safety_context_fit_score(
    commute_score: float,
    student_area_score: float,
    source_signal: bool,
    safety_context_notes: Any,
) -> float:
    note_count = (
        len(safety_context_notes) if isinstance(safety_context_notes, list) else 0
    )
    source_score = 100 if source_signal else 45
    note_score = min(100, 45 + (note_count * 12))
    return round(
        (commute_score * 0.35)
        + (student_area_score * 0.25)
        + (source_score * 0.25)
        + (note_score * 0.15),
        2,
    )


def _fit_label(ranking_mode: str) -> str:
    labels = {
        "student_default": "balanced student fit",
        "budget_first": "budget-forward fit",
        "commute_first": "commute-forward fit",
        "safety_context_first": "context-forward fit",
        "parent_balanced": "parent-balanced fit",
    }
    return labels[ranking_mode]


def _main_tradeoff(
    listing: dict[str, Any],
    warnings: list[str],
    features: dict[str, float],
) -> str:
    if warnings:
        return warnings[0]
    if features["all_in_cost"] < 65:
        return "Cost is the main trade-off compared with stronger-fit alternatives."
    if features["commute"] < 65:
        return "Commute is the main trade-off compared with closer alternatives."
    if listing.get("all_in_estimate_per_person") is None:
        return "Cost is rent-only because all-in monthly cost is incomplete."
    return "Balanced option with no major v1 ranking caveat."


def _missing_data_penalties(rankings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    penalties: list[dict[str, Any]] = []
    for ranked in rankings:
        warnings = ranked["inline_warnings"]
        penalty = max(float(ranked["missing_data_penalty"]), len(warnings) * 0.05)
        if penalty:
            penalties.append(
                {
                    "listing_id": ranked["listing_id"],
                    "penalty": round(penalty, 2),
                    "reasons": warnings,
                }
            )
    return penalties


def _candidate_confidence(listing: dict[str, Any], warnings: list[str]) -> float:
    base_confidence = _optional_number(listing.get("confidence")) or 0.5
    confidence = base_confidence - (len(warnings) * 0.04)
    return max(0.1, min(0.95, round(confidence, 2)))


def _ranking_confidence(ranked_listings: list[dict[str, Any]]) -> float:
    if not ranked_listings:
        return 0
    total = sum(float(listing["confidence"]) for listing in ranked_listings)
    return round(total / len(ranked_listings), 2)


def _ranking_id(session_id: str, ranking_mode: str, created_at: str) -> str:
    key = f"{session_id}:{ranking_mode}:{created_at}"
    return "ranking_" + sha256(key.encode("utf-8")).hexdigest()[:12]


def _optional_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _utc_now(now: datetime | None = None) -> str:
    value = now or datetime.now(UTC)
    if value.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

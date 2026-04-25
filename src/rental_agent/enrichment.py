"""Listing normalization and enrichment for the v1 prototype."""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import UTC, datetime
from hashlib import sha256
from math import atan2, ceil, cos, radians, sin, sqrt
import re
from typing import Any

from rental_agent.campus import CAMPUS_RECORDS, CampusRecord
from rental_agent.sources import SOURCE_REGISTRY, SourceRecord


ENRICHMENT_VERSION = "enrichment-v1"

FRESHNESS_ORDER = {
    "fresh_today": 0,
    "needs_verification": 1,
    "seen_within_7_days": 2,
    "unknown": 3,
    "stale": 4,
    "removed": 5,
}

DEFAULT_ENRICHMENT_OPTIONS = {
    "dedupe": True,
    "calculate_price_per_person": True,
    "estimate_all_in_cost": True,
    "calculate_approx_walk_commute": True,
    "include_safety_context_proxies": True,
    "include_parent_explainability": True,
}

ADDRESS_LINE_RE = re.compile(
    r"\b(st|street|ave|avenue|blvd|boulevard|rd|road|dr|drive|ln|lane|"
    r"ct|court|pl|place|way)\b",
    re.IGNORECASE,
)
BEDROOM_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(?:br|bed|beds|bedroom|bedrooms)\b",
    re.IGNORECASE,
)
BATHROOM_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(?:ba|bath|baths|bathroom|bathrooms)\b",
    re.IGNORECASE,
)
PRICE_RE = re.compile(r"\$?\s*([0-9][0-9,]*(?:\.\d+)?)")


def enrich_listings(
    session_id: str,
    campus_id: str,
    listing_snapshots: list[dict[str, Any]],
    enrichment_options: dict[str, Any] | None = None,
    *,
    campus_records: tuple[CampusRecord, ...] = CAMPUS_RECORDS,
    source_registry: tuple[SourceRecord, ...] = SOURCE_REGISTRY,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Normalize retrieved snapshots and add conservative enrichment fields."""

    if not session_id:
        raise ValueError("session_id is required")
    if not campus_id:
        raise ValueError("campus_id is required")
    if not isinstance(listing_snapshots, list) or not listing_snapshots:
        raise ValueError("listing_snapshots must include at least one snapshot")

    campus = _campus_for_id(campus_id, campus_records)
    if campus is None:
        raise ValueError(f"unknown campus_id: {campus_id}")

    options = _normalize_options(enrichment_options)
    source_by_id = {source.source_id: source for source in source_registry}
    created_at = _utc_now(now)

    normalized_snapshots: list[dict[str, Any]] = []
    enrichment_errors: list[dict[str, Any]] = []
    for index, snapshot in enumerate(deepcopy(listing_snapshots)):
        try:
            normalized_snapshots.append(_normalize_snapshot(snapshot))
        except ValueError as exc:
            enrichment_errors.append(
                {
                    "snapshot_index": index,
                    "snapshot_id": snapshot.get("snapshot_id")
                    if isinstance(snapshot, dict)
                    else None,
                    "error_type": "snapshot_validation_error",
                    "message": str(exc),
                }
            )

    grouped_snapshots = _group_snapshots(normalized_snapshots, options["dedupe"])
    canonical_listings: list[dict[str, Any]] = []
    duplicate_groups: list[dict[str, Any]] = []

    for group in grouped_snapshots:
        listing = _canonical_listing(
            group,
            campus,
            source_by_id,
            options,
            created_at,
        )
        canonical_listings.append(listing)
        if len(group) > 1:
            duplicate_groups.append(
                {
                    "canonical_listing_id": listing["listing_id"],
                    "merged_snapshot_ids": [
                        snapshot["snapshot_id"] for snapshot in group
                    ],
                    "match_reason": "same normalized specific address",
                }
            )

    return {
        "canonical_listings": canonical_listings,
        "duplicate_groups": duplicate_groups,
        "enrichment_errors": enrichment_errors,
        "limitations": _global_limitations(options),
        "created_at": created_at,
        "enrichment_version": ENRICHMENT_VERSION,
    }


def _normalize_snapshot(snapshot: Any) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        raise ValueError("snapshot must be a mapping")
    freshness_status = _required_string(snapshot, "freshness_status")
    if freshness_status not in FRESHNESS_ORDER:
        raise ValueError(f"unsupported freshness_status: {freshness_status}")

    return {
        "snapshot_id": _required_string(snapshot, "snapshot_id"),
        "source_id": _required_string(snapshot, "source_id"),
        "source_url": _required_string(snapshot, "source_url"),
        "source_listing_id": _optional_string(snapshot.get("source_listing_id")),
        "raw_title": _optional_string(snapshot.get("raw_title")),
        "raw_price": _optional_string(snapshot.get("raw_price")),
        "raw_location": _optional_string(snapshot.get("raw_location")),
        "freshness_status": freshness_status,
        "lat": _optional_number(snapshot.get("lat")),
        "lng": _optional_number(snapshot.get("lng")),
        "bedrooms": _optional_number(snapshot.get("bedrooms")),
        "bathrooms": _optional_number(snapshot.get("bathrooms")),
        "available_date": _optional_string(snapshot.get("available_date")),
        "lease_terms": _string_sequence(snapshot.get("lease_terms", ()), "lease_terms"),
        "furnished": _optional_bool(snapshot.get("furnished")),
        "contact": deepcopy(snapshot.get("contact")),
        "utilities_raw": _optional_string(snapshot.get("utilities_raw")),
        "fees_raw": _optional_string(snapshot.get("fees_raw")),
        "utilities_monthly_estimate": _optional_number(
            snapshot.get("utilities_monthly_estimate")
        ),
        "fees_monthly_estimate": _optional_number(snapshot.get("fees_monthly_estimate")),
    }


def _group_snapshots(
    snapshots: list[dict[str, Any]],
    dedupe_enabled: bool,
) -> list[list[dict[str, Any]]]:
    if not dedupe_enabled:
        return [[snapshot] for snapshot in snapshots]

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for snapshot in snapshots:
        grouped[_dedupe_key(snapshot)].append(snapshot)
    return list(grouped.values())


def _canonical_listing(
    group: list[dict[str, Any]],
    campus: CampusRecord,
    source_by_id: dict[str, SourceRecord],
    options: dict[str, bool],
    created_at: str,
) -> dict[str, Any]:
    primary = group[0]
    source_urls = sorted({snapshot["source_url"] for snapshot in group})
    title = _first_value(group, "raw_title")
    address_raw = _first_value(group, "raw_location")
    address_normalized = _normalize_address(address_raw)
    bedrooms = _first_number(group, "bedrooms") or _infer_number(
        [title, primary["raw_price"], address_raw],
        BEDROOM_RE,
    )
    bathrooms = _first_number(group, "bathrooms") or _infer_number(
        [title, primary["raw_price"], address_raw],
        BATHROOM_RE,
    )
    lat = _first_number(group, "lat")
    lng = _first_number(group, "lng")
    rent_raw = _first_value(group, "raw_price")
    price = (
        _parse_price(rent_raw, bedrooms)
        if options["calculate_price_per_person"]
        else _empty_price()
    )
    utilities = _utility_context(group)
    fees = _fee_context(group)
    all_in_estimate = _all_in_estimate(price, utilities, fees, options)
    freshness_status = _least_fresh_status(group)
    source_records = [
        source_by_id[source_id]
        for source_id in {snapshot["source_id"] for snapshot in group}
        if source_id in source_by_id
    ]
    managed_or_student_source_signal = _managed_or_student_source_signal(source_records)
    walk = _walk_context(lat, lng, campus, options)
    student_area_fit = _student_area_fit(address_normalized, campus)
    missing_fields = _missing_fields(
        address_raw=address_raw,
        price=price,
        utilities=utilities,
        fees=fees,
        walk=walk,
        options=options,
    )
    ranking_blockers = _ranking_blockers(price)
    missing_data_penalty = _missing_data_penalty(missing_fields, ranking_blockers)
    listing_id = _listing_id(group, address_normalized)
    limitations = _listing_limitations(walk, price, utilities, fees)

    listing = {
        "listing_id": listing_id,
        "source_urls": source_urls,
        "snapshot_ids": [snapshot["snapshot_id"] for snapshot in group],
        "title": title,
        "address_raw": address_raw,
        "address_normalized": address_normalized,
        "lat": lat,
        "lng": lng,
        "rent_raw": rent_raw,
        "rent_total_monthly": price["rent_total_monthly"],
        "rent_per_person_monthly": price["rent_per_person_monthly"],
        "price_basis": price["price_basis"],
        "utilities_status": utilities["utilities_status"],
        "fees_status": fees["fees_status"],
        "all_in_estimate_per_person": all_in_estimate,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "available_date": _first_value(group, "available_date"),
        "lease_terms": _merged_sequence(group, "lease_terms"),
        "furnished": _first_bool(group, "furnished"),
        "contact": _first_value(group, "contact"),
        "dedupe_status": _dedupe_status(group, address_normalized),
        "freshness_status": freshness_status,
        "missing_fields": missing_fields,
        "ranking_blockers": ranking_blockers,
        "missing_data_penalty": missing_data_penalty,
        "price_assumptions": price["assumptions"],
        "walk_minutes_to_campus": walk["walk_minutes_to_campus"],
        "walk_distance_miles": walk["walk_distance_miles"],
        "commute_confidence": walk["commute_confidence"],
        "commute_label": walk["commute_label"],
        "student_area_fit": student_area_fit,
        "managed_or_student_source_signal": managed_or_student_source_signal,
        "parent_explainability_notes": _parent_notes(
            options,
            source_records,
            managed_or_student_source_signal,
            freshness_status,
            walk,
        ),
        "safety_context_notes": _safety_context_notes(
            options,
            walk,
            student_area_fit,
            managed_or_student_source_signal,
        ),
        "limitations": limitations,
        "confidence": _confidence(price, walk, address_raw, freshness_status),
        "enriched_at": created_at,
        "enrichment_version": ENRICHMENT_VERSION,
    }
    _assert_no_safety_score(listing)
    return listing


def _parse_price(raw_price: str | None, bedrooms: float | None) -> dict[str, Any]:
    if not raw_price:
        return _empty_price()

    amount = _price_amount(raw_price)
    if amount is None:
        return _empty_price()

    text = raw_price.lower()
    price_basis = _price_basis(text)
    rent_total_monthly = None
    rent_per_person_monthly = None
    assumptions: list[str] = []

    if price_basis == "per_person":
        rent_per_person_monthly = amount
    elif price_basis == "per_bedroom":
        rent_per_person_monthly = amount
        assumptions.append("Assumed one occupant per bedroom for per-bedroom rent.")
    elif price_basis == "total_unit":
        rent_total_monthly = amount
        if bedrooms and bedrooms > 0:
            rent_per_person_monthly = round(amount / bedrooms, 2)
            bedroom_count = _format_number(bedrooms)
            assumptions.append(
                "Assumed one occupant per bedroom across "
                f"{bedroom_count} bedroom(s)."
            )
    elif price_basis == "from_price":
        rent_per_person_monthly = amount
        assumptions.append("From-price treated as a lower-bound rent estimate.")

    return {
        "rent_total_monthly": rent_total_monthly,
        "rent_per_person_monthly": rent_per_person_monthly,
        "price_basis": price_basis,
        "assumptions": assumptions,
    }


def _price_basis(text: str) -> str:
    if "from" in text:
        return "from_price"
    if any(marker in text for marker in ("/person", "per person", "per-person", " pp")):
        return "per_person"
    if any(
        marker in text
        for marker in (
            "/bed",
            "per bed",
            "per bedroom",
            "per room",
            "/room",
            "per-bedroom",
        )
    ):
        return "per_bedroom"
    if any(marker in text for marker in ("total", "entire", "whole unit", "unit rent")):
        return "total_unit"
    return "unknown"


def _empty_price() -> dict[str, Any]:
    return {
        "rent_total_monthly": None,
        "rent_per_person_monthly": None,
        "price_basis": "unknown",
        "assumptions": [],
    }


def _price_amount(raw_price: str) -> float | None:
    match = PRICE_RE.search(raw_price)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def _utility_context(group: list[dict[str, Any]]) -> dict[str, Any]:
    raw = " ".join(
        value.lower()
        for value in (
            _optional_string(snapshot.get("utilities_raw")) for snapshot in group
        )
        if value
    )
    estimate = _first_number(group, "utilities_monthly_estimate")
    if estimate is not None:
        return {"utilities_status": "partial", "utilities_monthly_estimate": estimate}
    if raw and "included" in raw and "not included" not in raw:
        return {"utilities_status": "included", "utilities_monthly_estimate": 0}
    if raw and any(
        marker in raw for marker in ("not included", "plus utilities", "separate")
    ):
        return {"utilities_status": "not_included", "utilities_monthly_estimate": None}
    return {"utilities_status": "unknown", "utilities_monthly_estimate": None}


def _fee_context(group: list[dict[str, Any]]) -> dict[str, Any]:
    raw = " ".join(
        value.lower()
        for value in (_optional_string(snapshot.get("fees_raw")) for snapshot in group)
        if value
    )
    estimate = _first_number(group, "fees_monthly_estimate")
    if estimate is not None:
        return {"fees_status": "partial", "fees_monthly_estimate": estimate}
    if raw and any(marker in raw for marker in ("no fee", "no monthly fee", "included")):
        return {"fees_status": "known", "fees_monthly_estimate": 0}
    return {"fees_status": "unknown", "fees_monthly_estimate": None}


def _all_in_estimate(
    price: dict[str, Any],
    utilities: dict[str, Any],
    fees: dict[str, Any],
    options: dict[str, bool],
) -> float | None:
    if not options["estimate_all_in_cost"]:
        return None
    rent = price["rent_per_person_monthly"]
    if rent is None:
        return None

    utility_estimate = utilities["utilities_monthly_estimate"]
    fee_estimate = fees["fees_monthly_estimate"]
    if utility_estimate is None or fee_estimate is None:
        return None
    return round(rent + utility_estimate + fee_estimate, 2)


def _walk_context(
    lat: float | None,
    lng: float | None,
    campus: CampusRecord,
    options: dict[str, bool],
) -> dict[str, Any]:
    if not options["calculate_approx_walk_commute"]:
        return {
            "walk_minutes_to_campus": None,
            "walk_distance_miles": None,
            "commute_confidence": 0,
            "commute_label": "Approximate walking commute not requested.",
        }
    if lat is None or lng is None:
        return {
            "walk_minutes_to_campus": None,
            "walk_distance_miles": None,
            "commute_confidence": 0,
            "commute_label": (
                "Approximate walking commute not calculated because coordinates "
                "are missing."
            ),
        }

    distance_miles = _haversine_miles(lat, lng, campus.lat, campus.lng)
    route_factor = 1.25
    walking_mph = 3.0
    walk_minutes = ceil((distance_miles * route_factor / walking_mph) * 60)
    return {
        "walk_minutes_to_campus": walk_minutes,
        "walk_distance_miles": round(distance_miles * route_factor, 2),
        "commute_confidence": 0.58,
        "commute_label": (
            "Approximate walking estimate from coordinates; verify the real route "
            "before relying on it."
        ),
    }


def _haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    earth_radius_miles = 3958.7613
    phi1 = radians(lat1)
    phi2 = radians(lat2)
    delta_phi = radians(lat2 - lat1)
    delta_lambda = radians(lng2 - lng1)
    haversine = (
        sin(delta_phi / 2) ** 2
        + cos(phi1) * cos(phi2) * sin(delta_lambda / 2) ** 2
    )
    return earth_radius_miles * 2 * atan2(sqrt(haversine), sqrt(1 - haversine))


def _student_area_fit(address_normalized: str | None, campus: CampusRecord) -> float | None:
    if not address_normalized:
        return None
    address_key = _key(address_normalized)
    for area in campus.student_areas:
        area_key = _key(area["name"])
        if area_key in address_key or address_key in area_key:
            return area["student_area_fit"]
    return None


def _managed_or_student_source_signal(source_records: list[SourceRecord]) -> bool | None:
    if not source_records:
        return None
    return any(
        record.source_allowed_for_v1
        and not record.requires_login
        and record.source_type
        in {"official_university_portal", "student_housing_portal", "property_manager"}
        for record in source_records
    )


def _parent_notes(
    options: dict[str, bool],
    source_records: list[SourceRecord],
    managed_or_student_source_signal: bool | None,
    freshness_status: str,
    walk: dict[str, Any],
) -> list[str]:
    if not options["include_parent_explainability"]:
        return []

    notes: list[str] = []
    if managed_or_student_source_signal:
        source_names = ", ".join(
            sorted({record.source_name for record in source_records})
        )
        notes.append(f"Source is an allowed public v1 source: {source_names}.")
    if freshness_status == "fresh_today":
        notes.append("Freshness status is same-day from the retrieval pipeline.")
    elif freshness_status == "needs_verification":
        notes.append("Freshness still needs same-day verification before contact.")
    if walk["walk_minutes_to_campus"] is not None:
        notes.append(
            f"Campus commute has an approximate walking estimate of {walk['walk_minutes_to_campus']} minutes."
        )
    return notes


def _safety_context_notes(
    options: dict[str, bool],
    walk: dict[str, Any],
    student_area_fit: float | None,
    managed_or_student_source_signal: bool | None,
) -> list[str]:
    if not options["include_safety_context_proxies"]:
        return []

    notes = ["Context only; this is not a safety guarantee."]
    if (
        walk["walk_minutes_to_campus"] is not None
        and walk["walk_minutes_to_campus"] <= 20
    ):
        notes.append(
            "Stronger context fit for a safety concern because the approximate walk to campus is short."
        )
    if student_area_fit is not None and student_area_fit >= 0.8:
        notes.append("Student-area context proxy is strong for this campus.")
    if managed_or_student_source_signal:
        notes.append(
            "Source context is stronger than private or login-gated sources because "
            "it passed the v1 public-source policy."
        )
    return notes


def _missing_fields(
    *,
    address_raw: str | None,
    price: dict[str, Any],
    utilities: dict[str, Any],
    fees: dict[str, Any],
    walk: dict[str, Any],
    options: dict[str, bool],
) -> list[str]:
    missing: list[str] = []
    if not address_raw:
        missing.append("address_or_location")
    if price["price_basis"] == "unknown":
        missing.append("price_basis")
    if price["rent_per_person_monthly"] is None:
        missing.append("rent_per_person_monthly")
    if utilities["utilities_status"] == "unknown":
        missing.append("utilities")
    if fees["fees_status"] == "unknown":
        missing.append("fees")
    if (
        options["calculate_approx_walk_commute"]
        and walk["walk_minutes_to_campus"] is None
    ):
        missing.append("listing_coordinates")
    return missing


def _ranking_blockers(price: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if price["price_basis"] == "unknown":
        blockers.append("unknown_price_basis")
    if price["rent_per_person_monthly"] is None:
        blockers.append("missing_per_person_rent")
    return blockers


def _missing_data_penalty(
    missing_fields: list[str],
    ranking_blockers: list[str],
) -> float:
    penalty = (0.08 * len(missing_fields)) + (0.2 * len(ranking_blockers))
    return min(1.0, round(penalty, 2))


def _listing_limitations(
    walk: dict[str, Any],
    price: dict[str, Any],
    utilities: dict[str, Any],
    fees: dict[str, Any],
) -> list[str]:
    limitations = [
        "Safety/context enrichment uses allowed proxies only and does not rate area conditions."
    ]
    limitations.append(walk["commute_label"])
    if price["price_basis"] == "unknown":
        limitations.append(
            "Price basis is unknown, so this listing should not be ranked yet."
        )
    if utilities["utilities_status"] == "unknown":
        limitations.append(
            "Utilities are unknown and should be verified before comparing all-in cost."
        )
    if fees["fees_status"] == "unknown":
        limitations.append(
            "Recurring fees are unknown and should be verified before comparing all-in cost."
        )
    return limitations


def _confidence(
    price: dict[str, Any],
    walk: dict[str, Any],
    address_raw: str | None,
    freshness_status: str,
) -> float:
    confidence = 0.45
    if address_raw:
        confidence += 0.12
    if price["price_basis"] != "unknown":
        confidence += 0.18
    if price["rent_per_person_monthly"] is not None:
        confidence += 0.1
    if walk["walk_minutes_to_campus"] is not None:
        confidence += 0.08
    if freshness_status == "fresh_today":
        confidence += 0.07
    return min(0.95, round(confidence, 2))


def _listing_id(group: list[dict[str, Any]], address_normalized: str | None) -> str:
    primary = group[0]
    if _is_specific_address(address_normalized):
        key = f"{primary['source_id']}:{address_normalized}"
    else:
        source_key = primary["source_listing_id"] or primary["source_url"]
        key = f"{primary['source_id']}:{source_key}"
    return "listing_" + sha256(key.encode("utf-8")).hexdigest()[:12]


def _dedupe_key(snapshot: dict[str, Any]) -> str:
    normalized_address = _normalize_address(snapshot["raw_location"])
    if _is_specific_address(normalized_address):
        return "address:" + _key(normalized_address)
    return "source_url:" + snapshot["source_url"]


def _dedupe_status(group: list[dict[str, Any]], address_normalized: str | None) -> str:
    if len(group) > 1:
        return "merged"
    if _is_specific_address(address_normalized):
        return "unique"
    return "unknown"


def _least_fresh_status(group: list[dict[str, Any]]) -> str:
    statuses = [snapshot["freshness_status"] for snapshot in group]
    return max(statuses, key=lambda status: FRESHNESS_ORDER.get(status, 3))


def _normalize_address(value: str | None) -> str | None:
    if not value:
        return None
    return " ".join(value.replace("\n", " ").split())


def _is_specific_address(value: str | None) -> bool:
    if not value:
        return False
    return any(character.isdigit() for character in value) and bool(
        ADDRESS_LINE_RE.search(value)
    )


def _key(value: str) -> str:
    return " ".join(
        "".join(
            character.lower() if character.isalnum() else " " for character in value
        ).split()
    )


def _global_limitations(options: dict[str, bool]) -> list[str]:
    limitations = [
        "Enrichment is based on retrieved listing snapshots; missing source fields stay missing.",
        "Safety/context fields are proxy notes only, not area safety ratings.",
    ]
    if options["calculate_approx_walk_commute"]:
        limitations.append(
            "Walking estimates are approximate coordinate-based estimates, not live route calculations."
        )
    return limitations


def _normalize_options(options: dict[str, Any] | None) -> dict[str, bool]:
    if options is None:
        return dict(DEFAULT_ENRICHMENT_OPTIONS)
    if not isinstance(options, dict):
        raise ValueError("enrichment_options must be a mapping")

    unknown = set(options) - set(DEFAULT_ENRICHMENT_OPTIONS)
    if unknown:
        unknown_list = ", ".join(sorted(unknown))
        raise ValueError(f"unsupported enrichment option(s): {unknown_list}")

    normalized = dict(DEFAULT_ENRICHMENT_OPTIONS)
    for key, value in options.items():
        if not isinstance(value, bool):
            raise ValueError(f"{key} must be a boolean")
        normalized[key] = value
    return normalized


def _campus_for_id(
    campus_id: str,
    campus_records: tuple[CampusRecord, ...],
) -> CampusRecord | None:
    return next(
        (campus for campus in campus_records if campus.campus_id == campus_id),
        None,
    )


def _first_value(group: list[dict[str, Any]], key: str) -> Any:
    for snapshot in group:
        value = snapshot.get(key)
        if value not in (None, "", []):
            return deepcopy(value)
    return None


def _first_number(group: list[dict[str, Any]], key: str) -> float | None:
    for snapshot in group:
        value = snapshot.get(key)
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
    return None


def _first_bool(group: list[dict[str, Any]], key: str) -> bool | None:
    for snapshot in group:
        value = snapshot.get(key)
        if isinstance(value, bool):
            return value
    return None


def _merged_sequence(group: list[dict[str, Any]], key: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for snapshot in group:
        for item in snapshot.get(key, ()):
            if item not in seen:
                values.append(item)
                seen.add(item)
    return values


def _infer_number(values: list[Any], pattern: re.Pattern[str]) -> float | None:
    for value in values:
        if not isinstance(value, str):
            continue
        match = pattern.search(value)
        if match:
            return float(match.group(1))
    return None


def _format_number(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:g}"


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("optional string fields must be strings or null")
    return value.strip() or None


def _required_string(value: dict[str, Any], key: str) -> str:
    raw_value = value.get(key)
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise ValueError(f"{key} is required")
    return raw_value.strip()


def _optional_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("optional numeric fields must be numbers or null")
    return float(value)


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError("optional boolean fields must be booleans or null")
    return value


def _string_sequence(value: Any, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, list | tuple):
        raise ValueError(f"{field_name} must be a sequence of strings")
    if not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must contain only strings")
    return tuple(value)


def _assert_no_safety_score(value: dict[str, Any]) -> None:
    if "safety_score" in value:
        raise AssertionError("v1 enrichment must not produce a safety_score field")


def _utc_now(now: datetime | None = None) -> str:
    value = now or datetime.now(UTC)
    if value.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

"""Campus context fixtures and resolver for the Philadelphia v1 prototype."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any


DEFAULT_CONTEXT_TYPES = {
    "campus_anchor",
    "student_areas",
    "official_resources",
    "transport",
    "housing_notes",
}


@dataclass(frozen=True)
class CampusRecord:
    university_id: str
    university_name: str
    campus_id: str
    campus_name: str
    address: str
    lat: float
    lng: float
    aliases: tuple[str, ...]
    anchor_points: tuple[dict[str, Any], ...]
    student_areas: tuple[dict[str, Any], ...]
    official_resources: tuple[dict[str, Any], ...]
    transport_notes: tuple[str, ...]
    housing_notes: tuple[str, ...]
    recommended_initial_search_radius_miles: float

    def campus_summary(self) -> dict[str, Any]:
        return {
            "campus_id": self.campus_id,
            "campus_name": self.campus_name,
            "address": self.address,
            "lat": self.lat,
            "lng": self.lng,
            "anchor_points": deepcopy(list(self.anchor_points)),
        }


CAMPUS_RECORDS: tuple[CampusRecord, ...] = (
    CampusRecord(
        university_id="uni_drexel",
        university_name="Drexel University",
        campus_id="campus_drexel_university_city",
        campus_name="University City Campus",
        address="3141 Chestnut Street, Philadelphia, PA 19104",
        lat=39.9566,
        lng=-75.1899,
        aliases=(
            "drexel",
            "drexel university",
            "drexel university city",
            "drexel university city campus",
        ),
        anchor_points=(
            {
                "name": "Main Building",
                "address": "3141 Chestnut Street, Philadelphia, PA 19104",
                "lat": 39.9566,
                "lng": -75.1899,
            },
        ),
        student_areas=(
            {
                "name": "University City core",
                "fit_reason": "Closest broad search area to Drexel's University City academic core.",
                "student_area_fit": 0.9,
            },
            {
                "name": "Powelton Village",
                "fit_reason": "Common off-campus student rental area near the Drexel campus edge.",
                "student_area_fit": 0.82,
            },
            {
                "name": "Mantua edge",
                "fit_reason": "Can be close to campus, but listing address and route details matter more.",
                "student_area_fit": 0.64,
            },
        ),
        official_resources=(
            {
                "name": "Drexel Off-Campus Housing",
                "resource_type": "official_university_portal",
                "url": "https://offcampushousing.drexel.edu/",
            },
            {
                "name": "Drexel Off-Campus Housing Guidance",
                "resource_type": "official_housing_resource",
                "url": "https://drexel.edu/studentlife/campus-living/commuter-resources/off-campus-housing",
            },
            {
                "name": "Drexel Public Safety Escorts",
                "resource_type": "campus_safety_resource",
                "url": "https://drexel.edu/publicsafety/policing-security/escorts",
            },
        ),
        transport_notes=(
            "University City has walk, bike, SEPTA, and trolley access, but v1 only estimates walking time.",
            "Treat any late-night route as listing-specific and needing separate verification.",
        ),
        housing_notes=(
            "Use public, non-login official or managed-source listings for v1 retrieval.",
            "Do not treat campus-area context as a same-day listing availability signal.",
        ),
        recommended_initial_search_radius_miles=1.5,
    ),
    CampusRecord(
        university_id="uni_temple",
        university_name="Temple University",
        campus_id="campus_temple_main",
        campus_name="Main Campus",
        address="1801 North Broad Street, Philadelphia, PA 19122",
        lat=39.9812,
        lng=-75.1552,
        aliases=(
            "temple",
            "temple university",
            "temple main",
            "temple main campus",
        ),
        anchor_points=(
            {
                "name": "Main Campus Broad Street anchor",
                "address": "1801 North Broad Street, Philadelphia, PA 19122",
                "lat": 39.9812,
                "lng": -75.1552,
            },
        ),
        student_areas=(
            {
                "name": "Main Campus / Templetown",
                "fit_reason": "Closest broad search area to the Temple Main Campus academic core.",
                "student_area_fit": 0.88,
            },
            {
                "name": "Cecil B. Moore / Broad corridor",
                "fit_reason": "Often practical for campus access; exact route should be checked per listing.",
                "student_area_fit": 0.78,
            },
            {
                "name": "Avenue North",
                "fit_reason": "Managed and student-oriented buildings may appear here, depending on source.",
                "student_area_fit": 0.72,
            },
        ),
        official_resources=(
            {
                "name": "Temple Off-Campus Housing",
                "resource_type": "official_university_portal",
                "url": "https://offcampus.temple.edu/",
            },
            {
                "name": "Temple University Housing And Residential Life",
                "resource_type": "official_housing_resource",
                "url": "https://studentaffairs.temple.edu/housing",
            },
            {
                "name": "Temple Walking Escort Program",
                "resource_type": "campus_safety_resource",
                "url": "https://safety.temple.edu/safety-initiatives-programs/safety-outreach-programs/walking-escort-main-hsc-campus",
            },
        ),
        transport_notes=(
            "Temple Main Campus is served by Broad Street Line access and nearby bus routes.",
            "v1 uses approximate walking time only; transit routing is a later provider integration.",
        ),
        housing_notes=(
            "Prefer official Temple off-campus and managed public pages in the v1 source policy.",
            "Do not infer safety from neighborhood names; use only route, source, and building context proxies later.",
        ),
        recommended_initial_search_radius_miles=1.25,
    ),
    CampusRecord(
        university_id="uni_upenn",
        university_name="University of Pennsylvania",
        campus_id="campus_upenn_university_city",
        campus_name="University City Campus",
        address="3451 Walnut Street, Philadelphia, PA 19104",
        lat=39.9522,
        lng=-75.1932,
        aliases=(
            "penn",
            "upenn",
            "u penn",
            "university of pennsylvania",
            "university of pennsylvania university city",
            "penn university city",
        ),
        anchor_points=(
            {
                "name": "College Hall / central campus anchor",
                "address": "3451 Walnut Street, Philadelphia, PA 19104",
                "lat": 39.9522,
                "lng": -75.1932,
            },
        ),
        student_areas=(
            {
                "name": "University City core",
                "fit_reason": "Closest broad search area to Penn's central campus.",
                "student_area_fit": 0.9,
            },
            {
                "name": "Spruce Hill",
                "fit_reason": "Common off-campus rental area west of central campus.",
                "student_area_fit": 0.8,
            },
            {
                "name": "Cedar Park / Walnut Hill",
                "fit_reason": "Can widen options, with listing-specific commute verification needed.",
                "student_area_fit": 0.64,
            },
        ),
        official_resources=(
            {
                "name": "Penn Off-Campus Services",
                "resource_type": "official_housing_resource",
                "url": "https://off-campus-services.business-services.upenn.edu/",
            },
            {
                "name": "Penn Residential Services",
                "resource_type": "official_housing_resource",
                "url": "https://residential-services.business-services.upenn.edu/",
            },
            {
                "name": "Penn Walking Escort",
                "resource_type": "campus_safety_resource",
                "url": "https://www.publicsafety.upenn.edu/about/security-services",
            },
        ),
        transport_notes=(
            "University City has walk, bike, trolley, SEPTA, and regional rail access.",
            "v1 estimates walking time only and should label commute values as approximate.",
        ),
        housing_notes=(
            "Use Penn official resources and public managed-source pages for v1 discovery.",
            "Move-in date is not required for broad search but blocks contact-ready recommendations.",
        ),
        recommended_initial_search_radius_miles=1.5,
    ),
)

UNSUPPORTED_PHILADELPHIA_SCHOOLS = {
    "jefferson",
    "thomas jefferson university",
    "saint josephs",
    "saint joseph's",
    "saint joseph's university",
    "st josephs",
    "st joseph's university",
    "la salle",
    "la salle university",
    "villanova",
    "villanova university",
    "bryn mawr",
    "bryn mawr college",
    "haverford",
    "haverford college",
}


def get_campus_context(
    university_name: str,
    campus_hint: str | None = None,
    city_hint: str | None = "Philadelphia",
    max_commute_minutes: float | None = None,
    context_types: list[str] | None = None,
) -> dict[str, Any]:
    """Resolve a v1 Philadelphia campus and return static context."""

    if not university_name or not university_name.strip():
        raise ValueError("university_name is required")

    selected_context_types = set(context_types or DEFAULT_CONTEXT_TYPES)
    unsupported_context_types = selected_context_types - DEFAULT_CONTEXT_TYPES
    if unsupported_context_types:
        values = ", ".join(sorted(unsupported_context_types))
        raise ValueError(f"unsupported context type(s): {values}")

    normalized_primary_query = _normalize_query(university_name)
    normalized_queries = [normalized_primary_query]
    if campus_hint:
        normalized_queries.append(_normalize_query(f"{university_name} {campus_hint}"))

    matches = _match_campus_queries(normalized_queries)

    if not matches and _is_supported_later(normalized_primary_query):
        return _unsupported_response(
            university_name,
            city_hint,
            reason="This Philadelphia school is listed for later expansion, not v1.",
        )

    if not matches:
        return _unsupported_response(
            university_name,
            city_hint,
            reason="Only Drexel, Temple, and Penn are supported in v1.",
        )

    if len(matches) > 1:
        return _ambiguous_response(
            university_name,
            city_hint,
            matches,
            selected_context_types,
        )

    campus = matches[0]
    return _campus_context_response(
        campus,
        selected_context_types,
        city_hint=city_hint,
        max_commute_minutes=max_commute_minutes,
    )


def _match_campus_queries(normalized_queries: list[str]) -> list[CampusRecord]:
    for normalized_query in normalized_queries:
        matches = _match_campuses(normalized_query)
        if matches:
            return matches
    return []


def _match_campuses(normalized_query: str) -> list[CampusRecord]:
    exact_matches = _exact_matches(normalized_query)
    if exact_matches:
        return exact_matches

    if normalized_query in {"university city", "university city campus"}:
        return [
            campus
            for campus in CAMPUS_RECORDS
            if campus.campus_name == "University City Campus"
        ]

    return _fuzzy_matches(normalized_query)


def _exact_matches(normalized_query: str) -> list[CampusRecord]:
    return [
        campus
        for campus in CAMPUS_RECORDS
        if normalized_query in {_normalize_query(alias) for alias in campus.aliases}
    ]


def _fuzzy_matches(normalized_query: str) -> list[CampusRecord]:
    matches: list[CampusRecord] = []
    for campus in CAMPUS_RECORDS:
        alias_scores = [
            _match_score(normalized_query, _normalize_query(alias))
            for alias in campus.aliases
        ]
        if max(alias_scores, default=0) >= 0.82:
            matches.append(campus)
    return matches


def _campus_context_response(
    campus: CampusRecord,
    context_types: set[str],
    *,
    city_hint: str | None,
    max_commute_minutes: float | None,
) -> dict[str, Any]:
    student_areas = (
        _filter_student_areas(campus.student_areas, max_commute_minutes)
        if "student_areas" in context_types
        else []
    )

    return {
        "university_id": campus.university_id,
        "university_name": campus.university_name,
        "campuses": [campus.campus_summary()],
        "selected_campus_id": campus.campus_id,
        "student_areas": deepcopy(list(student_areas)),
        "official_resources": deepcopy(list(campus.official_resources))
        if "official_resources" in context_types
        else [],
        "transport_notes": list(campus.transport_notes)
        if "transport" in context_types
        else [],
        "housing_notes": list(campus.housing_notes)
        if "housing_notes" in context_types
        else [],
        "recommended_initial_search_radius_miles": campus.recommended_initial_search_radius_miles,
        "confidence": 0.94,
        "needs_user_confirmation": False,
        "city_hint": city_hint,
    }


def _ambiguous_response(
    university_name: str,
    city_hint: str | None,
    matches: list[CampusRecord],
    context_types: set[str],
) -> dict[str, Any]:
    return {
        "university_id": "",
        "university_name": university_name,
        "campuses": [
            campus.campus_summary()
            if "campus_anchor" in context_types
            else {"campus_id": campus.campus_id, "campus_name": campus.campus_name}
            for campus in matches
        ],
        "selected_campus_id": None,
        "student_areas": [],
        "official_resources": [],
        "transport_notes": [],
        "housing_notes": [
            "Multiple v1 campuses match this input; ask the user to choose before searching."
        ],
        "recommended_initial_search_radius_miles": 0,
        "confidence": 0.55,
        "needs_user_confirmation": True,
        "city_hint": city_hint,
    }


def _unsupported_response(
    university_name: str,
    city_hint: str | None,
    *,
    reason: str,
) -> dict[str, Any]:
    return {
        "university_id": "",
        "university_name": university_name,
        "campuses": [],
        "selected_campus_id": None,
        "student_areas": [],
        "official_resources": [],
        "transport_notes": [],
        "housing_notes": [reason],
        "recommended_initial_search_radius_miles": 0,
        "confidence": 0,
        "needs_user_confirmation": True,
        "city_hint": city_hint,
        "unsupported_reason": reason,
    }


def _filter_student_areas(
    student_areas: tuple[dict[str, Any], ...],
    max_commute_minutes: float | None,
) -> tuple[dict[str, Any], ...]:
    if max_commute_minutes is None or max_commute_minutes >= 25:
        return student_areas
    return tuple(area for area in student_areas if area["student_area_fit"] >= 0.75)


def _is_supported_later(normalized_query: str) -> bool:
    return normalized_query in {
        _normalize_query(value) for value in UNSUPPORTED_PHILADELPHIA_SCHOOLS
    }


def _match_score(left: str, right: str) -> float:
    if left in right or right in left:
        return 0.9
    return SequenceMatcher(None, left, right).ratio()


def _normalize_query(value: str) -> str:
    cleaned = value.lower().replace("&", " and ")
    return " ".join(
        "".join(character if character.isalnum() else " " for character in cleaned).split()
    )

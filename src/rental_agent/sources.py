"""Source registry and v1 source-policy filtering."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


SOURCE_TYPES = {
    "official_university_portal",
    "student_housing_portal",
    "property_manager",
}

ADAPTER_STATUSES = {
    "active",
    "paused",
    "manual_only",
    "blocked",
}

DEFAULT_ALLOWED_SOURCE_TYPES = (
    "official_university_portal",
    "student_housing_portal",
    "property_manager",
)


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    source_name: str
    source_type: str
    base_url: str
    source_allowed_for_v1: bool
    requires_login: bool
    access_control_notes: str
    robots_or_terms_notes: str
    adapter_status: str
    campus_ids: tuple[str, ...]
    last_health_check_at: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        if self.source_type not in SOURCE_TYPES:
            raise ValueError(f"unsupported source_type: {self.source_type}")
        if self.adapter_status not in ADAPTER_STATUSES:
            raise ValueError(f"unsupported adapter_status: {self.adapter_status}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_name": self.source_name,
            "source_type": self.source_type,
            "base_url": self.base_url,
            "source_allowed_for_v1": self.source_allowed_for_v1,
            "requires_login": self.requires_login,
            "access_control_notes": self.access_control_notes,
            "robots_or_terms_notes": self.robots_or_terms_notes,
            "adapter_status": self.adapter_status,
            "campus_ids": list(self.campus_ids),
            "last_health_check_at": self.last_health_check_at,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class SourcePolicy:
    allowed_source_types: tuple[str, ...] = DEFAULT_ALLOWED_SOURCE_TYPES
    non_login_public_only: bool = True
    require_source_allowed_for_v1: bool = True
    avoid_sources: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, value: dict[str, Any] | None = None) -> "SourcePolicy":
        if value is None:
            return cls()

        allowed_source_types = tuple(
            value.get("allowed_source_types", DEFAULT_ALLOWED_SOURCE_TYPES)
        )
        invalid_types = set(allowed_source_types) - SOURCE_TYPES
        if invalid_types:
            invalid = ", ".join(sorted(invalid_types))
            raise ValueError(f"unsupported allowed source type(s): {invalid}")

        return cls(
            allowed_source_types=allowed_source_types,
            non_login_public_only=bool(value.get("non_login_public_only", True)),
            require_source_allowed_for_v1=bool(
                value.get("require_source_allowed_for_v1", True)
            ),
            avoid_sources=tuple(value.get("avoid_sources", ())),
        )


SOURCE_REGISTRY: tuple[SourceRecord, ...] = (
    SourceRecord(
        source_id="drexel_off_campus_housing",
        source_name="Drexel Off-Campus Housing",
        source_type="official_university_portal",
        base_url="https://offcampushousing.drexel.edu/",
        source_allowed_for_v1=True,
        requires_login=False,
        access_control_notes="Public official portal landing page; adapters must not bypass blocks or login prompts.",
        robots_or_terms_notes="Use only public pages available without authentication.",
        adapter_status="manual_only",
        campus_ids=("campus_drexel_university_city",),
        notes="curl may receive 403; retrieval adapters must treat that as a source error, not as permission to bypass.",
    ),
    SourceRecord(
        source_id="temple_off_campus_housing",
        source_name="Temple Off-Campus Housing",
        source_type="official_university_portal",
        base_url="https://offcampus.temple.edu/",
        source_allowed_for_v1=True,
        requires_login=False,
        access_control_notes="Public official portal landing page; adapters must not bypass blocks or login prompts.",
        robots_or_terms_notes="Use only public pages available without authentication.",
        adapter_status="manual_only",
        campus_ids=("campus_temple_main",),
        notes="curl may receive 403; retrieval adapters must treat that as a source error, not as permission to bypass.",
    ),
    SourceRecord(
        source_id="penn_off_campus_services",
        source_name="Penn Off-Campus Services",
        source_type="official_university_portal",
        base_url="https://off-campus-services.business-services.upenn.edu/",
        source_allowed_for_v1=True,
        requires_login=False,
        access_control_notes="Public official resource; listing adapters must use only public non-login pages.",
        robots_or_terms_notes="Use only public pages available without authentication.",
        adapter_status="manual_only",
        campus_ids=("campus_upenn_university_city",),
    ),
    SourceRecord(
        source_id="drexel_housing_guidance",
        source_name="Drexel Off-Campus Housing Guidance",
        source_type="official_university_portal",
        base_url="https://drexel.edu/studentlife/campus-living/commuter-resources/off-campus-housing",
        source_allowed_for_v1=False,
        requires_login=False,
        access_control_notes="Official guidance page, not a listing source.",
        robots_or_terms_notes="Can be shown as a resource but must not feed listing discovery.",
        adapter_status="manual_only",
        campus_ids=("campus_drexel_university_city",),
    ),
    SourceRecord(
        source_id="facebook_student_sublets",
        source_name="Facebook Student Sublet Groups",
        source_type="student_housing_portal",
        base_url="https://www.facebook.com/groups/",
        source_allowed_for_v1=False,
        requires_login=True,
        access_control_notes="Private or login-gated groups are out of scope for v1.",
        robots_or_terms_notes="Do not scrape or access private groups.",
        adapter_status="blocked",
        campus_ids=(
            "campus_drexel_university_city",
            "campus_temple_main",
            "campus_upenn_university_city",
        ),
    ),
    SourceRecord(
        source_id="zillow",
        source_name="Zillow",
        source_type="property_manager",
        base_url="https://www.zillow.com/",
        source_allowed_for_v1=False,
        requires_login=False,
        access_control_notes="Excluded from v1 source policy.",
        robots_or_terms_notes="Do not use in v1 retrieval.",
        adapter_status="blocked",
        campus_ids=(
            "campus_drexel_university_city",
            "campus_temple_main",
            "campus_upenn_university_city",
        ),
    ),
    SourceRecord(
        source_id="apartments_com",
        source_name="Apartments.com",
        source_type="property_manager",
        base_url="https://www.apartments.com/",
        source_allowed_for_v1=False,
        requires_login=False,
        access_control_notes="Excluded from v1 source policy.",
        robots_or_terms_notes="Do not use in v1 retrieval.",
        adapter_status="blocked",
        campus_ids=(
            "campus_drexel_university_city",
            "campus_temple_main",
            "campus_upenn_university_city",
        ),
    ),
)


def get_source_registry(
    campus_id: str | None = None,
    *,
    include_blocked: bool = True,
    registry: tuple[SourceRecord, ...] = SOURCE_REGISTRY,
) -> list[dict[str, Any]]:
    """Return source records, optionally scoped to one campus."""

    records = _records_for_campus(campus_id, registry)
    if not include_blocked:
        records = [
            record
            for record in records
            if record.source_allowed_for_v1
            and not record.requires_login
            and record.adapter_status != "blocked"
        ]
    return [record.to_dict() for record in records]


def select_sources_for_retrieval(
    campus_id: str,
    source_policy: SourcePolicy | dict[str, Any] | None = None,
    *,
    registry: tuple[SourceRecord, ...] = SOURCE_REGISTRY,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Apply v1 source policy before any retrieval adapter can run."""

    if not campus_id:
        raise ValueError("campus_id is required")

    policy = (
        source_policy
        if isinstance(source_policy, SourcePolicy)
        else SourcePolicy.from_mapping(source_policy)
    )

    selected_sources: list[dict[str, Any]] = []
    skipped_sources: list[dict[str, Any]] = []
    source_errors: list[dict[str, Any]] = []

    campus_records = _records_for_campus(campus_id, registry)
    if not campus_records:
        source_errors.append(
            {
                "source_id": None,
                "error_type": "unknown_campus",
                "message": f"No source registry records exist for campus_id {campus_id!r}.",
            }
        )

    for record in campus_records:
        skip_reason = _skip_reason(record, policy)
        if skip_reason:
            skipped_sources.append(
                {
                    "source": record.to_dict(),
                    "reason": skip_reason,
                }
            )
            continue

        selected_sources.append(record.to_dict())

    return {
        "selected_sources": selected_sources,
        "skipped_sources": skipped_sources,
        "source_errors": source_errors,
        "policy": {
            "allowed_source_types": list(policy.allowed_source_types),
            "non_login_public_only": policy.non_login_public_only,
            "require_source_allowed_for_v1": policy.require_source_allowed_for_v1,
            "avoid_sources": list(policy.avoid_sources),
        },
        "selected_count": len(selected_sources),
        "skipped_count": len(skipped_sources),
        "evaluated_at": _utc_now(now),
    }


def _records_for_campus(
    campus_id: str | None,
    registry: tuple[SourceRecord, ...],
) -> list[SourceRecord]:
    if campus_id is None:
        return list(registry)
    return [record for record in registry if campus_id in record.campus_ids]


def _skip_reason(record: SourceRecord, policy: SourcePolicy) -> str | None:
    if record.source_id in policy.avoid_sources:
        return "source_id listed in avoid_sources"
    if record.source_type not in policy.allowed_source_types:
        return f"source_type {record.source_type!r} is not allowed by policy"
    if policy.non_login_public_only and record.requires_login:
        return "source requires login or private access"
    if policy.require_source_allowed_for_v1 and not record.source_allowed_for_v1:
        return "source_allowed_for_v1 is false"
    if record.adapter_status == "blocked":
        return "adapter_status is blocked"
    return None


def _utc_now(now: datetime | None = None) -> str:
    value = now or datetime.now(UTC)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

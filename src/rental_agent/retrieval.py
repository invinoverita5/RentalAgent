"""Listing retrieval pipeline skeleton with tool-backed snapshot validation."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import urlparse

from rental_agent.sources import (
    SOURCE_REGISTRY,
    SourcePolicy,
    SourceRecord,
    select_sources_for_retrieval,
)


PARSER_VERSION = "retrieval-skeleton-v1"
FRESHNESS_STATUSES = {
    "fresh_today",
    "seen_within_7_days",
    "needs_verification",
    "stale",
    "removed",
    "unknown",
}
RANKABLE_FRESHNESS_STATUSES = {"fresh_today", "needs_verification"}


class ListingSourceAdapter(Protocol):
    """Adapter contract for source-specific listing retrieval."""

    def retrieve(
        self,
        *,
        source: dict[str, Any],
        search_constraints: dict[str, Any],
        limit: int,
        retrieved_at: str,
    ) -> list[dict[str, Any]]:
        """Return listing snapshots from one already-approved source."""


@dataclass(frozen=True)
class ListingSnapshot:
    snapshot_id: str
    source_id: str
    source_url: str
    source_listing_id: str | None
    raw_title: str | None
    raw_price: str | None
    raw_location: str | None
    raw_html_hash: str | None
    retrieved_at: str
    freshness_status: str
    freshness_evidence: tuple[str, ...]
    parser_version: str
    source_allowed_for_v1: bool

    def __post_init__(self) -> None:
        if not self.snapshot_id:
            raise ValueError("snapshot_id is required")
        if not self.source_id:
            raise ValueError("source_id is required")
        if not self.source_url:
            raise ValueError("source_url is required")
        if self.freshness_status not in FRESHNESS_STATUSES:
            raise ValueError(f"unsupported freshness_status: {self.freshness_status}")
        if not self.parser_version:
            raise ValueError("parser_version is required")

    @classmethod
    def from_mapping(
        cls,
        value: dict[str, Any],
        *,
        source_id: str,
        source_allowed_for_v1: bool,
        retrieved_at: str,
    ) -> "ListingSnapshot":
        if not isinstance(value, dict):
            raise ValueError("snapshot must be a mapping")
        snapshot_source_id = value.get("source_id", source_id)
        if snapshot_source_id != source_id:
            raise ValueError("snapshot source_id does not match selected source")
        snapshot_source_allowed_for_v1 = value.get(
            "source_allowed_for_v1",
            source_allowed_for_v1,
        )
        if not isinstance(snapshot_source_allowed_for_v1, bool):
            raise ValueError("snapshot source_allowed_for_v1 must be boolean")

        return cls(
            snapshot_id=_required_string(value, "snapshot_id"),
            source_id=snapshot_source_id,
            source_url=_required_string(value, "source_url"),
            source_listing_id=_optional_string(value.get("source_listing_id")),
            raw_title=_optional_string(value.get("raw_title")),
            raw_price=_optional_string(value.get("raw_price")),
            raw_location=_optional_string(value.get("raw_location")),
            raw_html_hash=_optional_string(value.get("raw_html_hash")),
            retrieved_at=_string_value(
                value.get("retrieved_at", retrieved_at),
                field_name="retrieved_at",
            ),
            freshness_status=str(value.get("freshness_status", "needs_verification")),
            freshness_evidence=_string_sequence(
                value.get("freshness_evidence", ()),
                field_name="freshness_evidence",
            ),
            parser_version=_string_value(
                value.get("parser_version", PARSER_VERSION),
                field_name="parser_version",
            ),
            source_allowed_for_v1=snapshot_source_allowed_for_v1,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "source_id": self.source_id,
            "source_url": self.source_url,
            "source_listing_id": self.source_listing_id,
            "raw_title": self.raw_title,
            "raw_price": self.raw_price,
            "raw_location": self.raw_location,
            "raw_html_hash": self.raw_html_hash,
            "retrieved_at": self.retrieved_at,
            "freshness_status": self.freshness_status,
            "freshness_evidence": list(self.freshness_evidence),
            "parser_version": self.parser_version,
            "source_allowed_for_v1": self.source_allowed_for_v1,
        }


@dataclass
class ListingSnapshotStore:
    """In-memory listing snapshot store for prototype debugging."""

    _snapshots_by_session: dict[str, list[ListingSnapshot]] = field(default_factory=dict)

    def add_many(self, session_id: str, snapshots: list[ListingSnapshot]) -> None:
        self._snapshots_by_session.setdefault(session_id, []).extend(deepcopy(snapshots))

    def get_for_session(self, session_id: str) -> list[dict[str, Any]]:
        return [
            snapshot.to_dict()
            for snapshot in deepcopy(self._snapshots_by_session.get(session_id, []))
        ]

    def delete_for_session(self, session_id: str) -> bool:
        return self._snapshots_by_session.pop(session_id, None) is not None

    def clear(self) -> None:
        self._snapshots_by_session.clear()


DEFAULT_LISTING_STORE = ListingSnapshotStore()


def retrieve_listings(
    session_id: str,
    campus_id: str,
    search_constraints: dict[str, Any] | None,
    source_policy: SourcePolicy | dict[str, Any] | None,
    limit: int,
    *,
    registry: tuple[SourceRecord, ...] = SOURCE_REGISTRY,
    adapters: dict[str, ListingSourceAdapter] | None = None,
    store: ListingSnapshotStore = DEFAULT_LISTING_STORE,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Select approved sources and retrieve validated listing snapshots."""

    if not session_id:
        raise ValueError("session_id is required")
    if not campus_id:
        raise ValueError("campus_id is required")
    if limit <= 0:
        raise ValueError("limit must be greater than zero")

    retrieved_at = _utc_now(now)
    constraints = deepcopy(search_constraints or {})
    selection = select_sources_for_retrieval(
        campus_id,
        source_policy,
        registry=registry,
        now=now,
    )
    adapters = adapters or {}
    snapshots: list[ListingSnapshot] = []
    source_errors = list(selection["source_errors"])

    for source in selection["selected_sources"]:
        if len(snapshots) >= limit:
            break

        source_id = source["source_id"]
        if source["adapter_status"] != "active":
            source_errors.append(
                _source_error(
                    source_id,
                    "adapter_not_active",
                    f"Source adapter status is {source['adapter_status']!r}; no fetch attempted.",
                )
            )
            continue

        adapter = adapters.get(source_id)
        if adapter is None:
            source_errors.append(
                _source_error(
                    source_id,
                    "adapter_missing",
                    "No retrieval adapter is registered for this selected source.",
                )
            )
            continue

        try:
            raw_snapshots = adapter.retrieve(
                source=deepcopy(source),
                search_constraints=deepcopy(constraints),
                limit=limit - len(snapshots),
                retrieved_at=retrieved_at,
            )
        except Exception as exc:
            source_errors.append(
                _source_error(source_id, "adapter_error", f"{type(exc).__name__}: {exc}")
            )
            continue
        if not isinstance(raw_snapshots, list):
            source_errors.append(
                _source_error(
                    source_id,
                    "adapter_error",
                    "Adapter must return a list of listing snapshot mappings.",
                )
            )
            continue

        for raw_snapshot in raw_snapshots:
            if len(snapshots) >= limit:
                break
            try:
                snapshot = ListingSnapshot.from_mapping(
                    raw_snapshot,
                    source_id=source_id,
                    source_allowed_for_v1=source["source_allowed_for_v1"],
                    retrieved_at=retrieved_at,
                )
                _validate_snapshot_source(snapshot, source)
            except ValueError as exc:
                source_errors.append(
                    _source_error(source_id, "snapshot_validation_error", str(exc))
                )
                continue
            snapshots.append(snapshot)

    store.add_many(session_id, snapshots)

    return {
        "listing_snapshots": [snapshot.to_dict() for snapshot in snapshots],
        "source_errors": source_errors,
        "skipped_sources": selection["skipped_sources"],
        "result_count": len(snapshots),
        "retrieved_at": retrieved_at,
        "parser_version": PARSER_VERSION,
    }


def delete_listing_snapshots(
    session_id: str,
    *,
    store: ListingSnapshotStore = DEFAULT_LISTING_STORE,
) -> dict[str, Any]:
    """Delete stored listing snapshots associated with a session."""

    if not session_id:
        raise ValueError("session_id is required")
    return {"session_id": session_id, "deleted": store.delete_for_session(session_id)}


def _validate_snapshot_source(snapshot: ListingSnapshot, source: dict[str, Any]) -> None:
    if not snapshot.source_allowed_for_v1:
        raise ValueError("snapshot source_allowed_for_v1 must be true")
    if snapshot.source_id != source["source_id"]:
        raise ValueError("snapshot source_id does not match selected source")
    if not _same_host(snapshot.source_url, source["base_url"]):
        raise ValueError("snapshot source_url host does not match selected source")
    if snapshot.freshness_status not in RANKABLE_FRESHNESS_STATUSES:
        raise ValueError(
            "retrieval snapshots must be fresh_today or needs_verification"
        )


def _source_error(source_id: str | None, error_type: str, message: str) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "error_type": error_type,
        "message": message,
    }


def _required_string(value: dict[str, Any], key: str) -> str:
    raw_value = value.get(key)
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise ValueError(f"{key} is required")
    return raw_value.strip()


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("optional string fields must be strings or null")
    return value.strip() or None


def _string_value(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _string_sequence(value: Any, *, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, list | tuple):
        raise ValueError(f"{field_name} must be a sequence of strings")
    if not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must contain only strings")
    return tuple(value)


def _same_host(left: str, right: str) -> bool:
    left_host = urlparse(left).netloc
    right_host = urlparse(right).netloc
    return bool(left_host and right_host and left_host == right_host)


def _utc_now(now: datetime | None = None) -> str:
    value = now or datetime.now(UTC)
    if value.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

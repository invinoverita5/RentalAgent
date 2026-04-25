"""Session state handling for the Student Rental Agent prototype."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any


STATE_FIELDS = {
    "university",
    "campus_id",
    "budget_max_per_person",
    "budget_target_per_person",
    "move_in_date",
    "roommates_open",
    "preferred_roommate_count",
    "commute_max_minutes",
    "safety_context_priority",
    "student_social_priority",
    "parents_involved",
    "parent_priority",
    "guarantor_needed",
    "lease_length_months",
    "furnished_preference",
}

CONFLICT_FIELDS = {
    "university",
    "campus_id",
    "budget_max_per_person",
    "budget_target_per_person",
    "move_in_date",
    "roommates_open",
    "commute_max_minutes",
    "guarantor_needed",
    "lease_length_months",
}

ENUM_FIELDS = {
    "safety_context_priority": {"low", "medium", "high", None},
    "student_social_priority": {"low", "medium", "high", None},
    "furnished_preference": {"required", "preferred", "not_needed", "unknown", None},
}

NUMERIC_FIELDS = {
    "budget_max_per_person",
    "budget_target_per_person",
    "commute_max_minutes",
    "lease_length_months",
}

BOOLEAN_FIELDS = {
    "roommates_open",
    "parents_involved",
    "guarantor_needed",
}


@dataclass(frozen=True)
class Assumption:
    """An explicit assumption attached to the user's rental-search state."""

    field: str
    assumption: str
    confidence: float

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "Assumption":
        missing = {"field", "assumption", "confidence"} - value.keys()
        if missing:
            missing_list = ", ".join(sorted(missing))
            raise ValueError(f"assumption missing required field(s): {missing_list}")

        confidence = value["confidence"]
        if not isinstance(confidence, int | float) or not 0 <= confidence <= 1:
            raise ValueError("assumption confidence must be a number from 0 to 1")

        return cls(
            field=str(value["field"]),
            assumption=str(value["assumption"]),
            confidence=float(confidence),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "assumption": self.assumption,
            "confidence": self.confidence,
        }


@dataclass
class SessionState:
    """Mutable session-level preferences for one rental search."""

    session_id: str
    university: str | None = None
    campus_id: str | None = None
    budget_max_per_person: float | None = None
    budget_target_per_person: float | None = None
    move_in_date: str | None = None
    roommates_open: bool | None = None
    preferred_roommate_count: str | None = None
    commute_max_minutes: float | None = None
    safety_context_priority: str | None = None
    student_social_priority: str | None = None
    parents_involved: bool | None = None
    parent_priority: str | None = None
    guarantor_needed: bool | None = None
    lease_length_months: float | None = None
    furnished_preference: str | None = None
    assumptions: list[Assumption] = field(default_factory=list)
    updated_at: str = field(default_factory=lambda: _utc_now())

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "university": self.university,
            "campus_id": self.campus_id,
            "budget_max_per_person": self.budget_max_per_person,
            "budget_target_per_person": self.budget_target_per_person,
            "move_in_date": self.move_in_date,
            "roommates_open": self.roommates_open,
            "preferred_roommate_count": self.preferred_roommate_count,
            "commute_max_minutes": self.commute_max_minutes,
            "safety_context_priority": self.safety_context_priority,
            "student_social_priority": self.student_social_priority,
            "parents_involved": self.parents_involved,
            "parent_priority": self.parent_priority,
            "guarantor_needed": self.guarantor_needed,
            "lease_length_months": self.lease_length_months,
            "furnished_preference": self.furnished_preference,
            "assumptions": [assumption.to_dict() for assumption in self.assumptions],
            "updated_at": self.updated_at,
        }


class SessionStateStore:
    """In-memory session store used by the prototype runtime."""

    def __init__(self) -> None:
        self._states: dict[str, SessionState] = {}

    def get(self, session_id: str) -> SessionState | None:
        state = self._states.get(session_id)
        return deepcopy(state) if state else None

    def upsert(self, session_id: str, state: SessionState) -> None:
        if session_id != state.session_id:
            raise ValueError("session_id must match state.session_id")
        self._states[session_id] = deepcopy(state)

    def delete(self, session_id: str) -> bool:
        return self._states.pop(session_id, None) is not None

    def clear(self) -> None:
        self._states.clear()


DEFAULT_STORE = SessionStateStore()


def update_user_state(
    session_id: str,
    updates: dict[str, Any],
    assumptions: list[dict[str, Any]] | None = None,
    *,
    store: SessionStateStore = DEFAULT_STORE,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Create or update session state with validation and conflict reporting."""

    if not session_id:
        raise ValueError("session_id is required")
    if not updates:
        raise ValueError("updates must include at least one field")

    normalized_updates = _validate_updates(updates)
    incoming_assumptions = [
        Assumption.from_mapping(assumption) for assumption in assumptions or []
    ]

    state = store.get(session_id) or SessionState(session_id=session_id)
    changed_fields: list[str] = []
    conflicts: list[str] = []

    for field_name, incoming_value in normalized_updates.items():
        current_value = getattr(state, field_name)
        if _is_conflict(field_name, current_value, incoming_value):
            conflicts.append(
                f"{field_name} already has value {current_value!r}; received {incoming_value!r}"
            )
            continue

        if current_value != incoming_value:
            setattr(state, field_name, incoming_value)
            changed_fields.append(field_name)

    _upsert_assumptions(state, incoming_assumptions + _budget_assumptions(state))

    if changed_fields or incoming_assumptions:
        state.updated_at = _utc_now(now)

    store.upsert(session_id, state)

    return {
        "state": state.to_dict(),
        "changed_fields": changed_fields,
        "missing_critical_fields": _missing_critical_fields(state),
        "conflicts": conflicts,
    }


def delete_user_state(
    session_id: str,
    *,
    store: SessionStateStore = DEFAULT_STORE,
) -> dict[str, Any]:
    """Delete a user's prototype session state and assumptions."""

    if not session_id:
        raise ValueError("session_id is required")

    return {
        "session_id": session_id,
        "deleted": store.delete(session_id),
    }


def _validate_updates(updates: dict[str, Any]) -> dict[str, Any]:
    unknown = set(updates) - STATE_FIELDS
    if unknown:
        unknown_list = ", ".join(sorted(unknown))
        raise ValueError(f"unknown update field(s): {unknown_list}")

    return {
        field_name: _validate_field(field_name, value)
        for field_name, value in updates.items()
    }


def _validate_field(field_name: str, value: Any) -> Any:
    if field_name in ENUM_FIELDS and value not in ENUM_FIELDS[field_name]:
        allowed = ", ".join(
            sorted(str(item) for item in ENUM_FIELDS[field_name] if item)
        )
        raise ValueError(f"{field_name} must be one of: {allowed}, or null")

    if field_name in NUMERIC_FIELDS and value is not None:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError(f"{field_name} must be numeric or null")
        if value < 0:
            raise ValueError(f"{field_name} must be non-negative")
        return float(value)

    if field_name in BOOLEAN_FIELDS and value is not None and not isinstance(value, bool):
        raise ValueError(f"{field_name} must be boolean or null")

    if field_name == "move_in_date" and value is not None:
        if not isinstance(value, str):
            raise ValueError("move_in_date must be an ISO date string or null")
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("move_in_date must be an ISO date string or null") from exc

    if value is not None and field_name not in NUMERIC_FIELDS | BOOLEAN_FIELDS:
        return str(value).strip()

    return value


def _is_conflict(field_name: str, current_value: Any, incoming_value: Any) -> bool:
    return (
        field_name in CONFLICT_FIELDS
        and current_value is not None
        and incoming_value is not None
        and current_value != incoming_value
    )


def _budget_assumptions(state: SessionState) -> list[Assumption]:
    if state.budget_max_per_person is None:
        return []

    confidence = 0.75 if state.roommates_open else 0.6
    return [
        Assumption(
            field="budget_basis",
            assumption="Budget interpreted as monthly per-person rent.",
            confidence=confidence,
        )
    ]


def _upsert_assumptions(state: SessionState, incoming: list[Assumption]) -> None:
    for assumption in incoming:
        match_index = next(
            (
                index
                for index, existing in enumerate(state.assumptions)
                if existing.field == assumption.field
                and existing.assumption == assumption.assumption
            ),
            None,
        )
        if match_index is None:
            state.assumptions.append(assumption)
            continue

        existing = state.assumptions[match_index]
        if assumption.confidence > existing.confidence:
            state.assumptions[match_index] = assumption


def _missing_critical_fields(state: SessionState) -> list[str]:
    missing: list[str] = []
    if not state.university:
        missing.append("university")
    if not state.campus_id:
        missing.append("campus_id")
    if state.budget_max_per_person is None:
        missing.append("budget_max_per_person")
    if state.budget_max_per_person is not None and state.roommates_open is None:
        missing.append("roommates_open")
    return missing


def _utc_now(now: datetime | None = None) -> str:
    value = now or datetime.now(UTC)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

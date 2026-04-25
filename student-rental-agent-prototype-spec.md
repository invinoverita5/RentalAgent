# Student Rental Agent Prototype Spec

## Part I: Product And Engineering Spec

### 1. Product Overview

The Student Rental Agent helps students find off-campus housing near Philadelphia universities without inventing listing facts or overstating safety. The prototype focuses on Drexel University, Temple University, and the University of Pennsylvania.

The agent's job is to:

- Capture the student's constraints and preferences.
- Resolve the relevant campus anchor.
- Retrieve real listings only from allowed public sources.
- Normalize listing price, freshness, and location data.
- Rank listings using clear, caveated trade-offs.
- Explain why a listing may or may not fit the student and, when relevant, their parents.

The model is not the source of truth for listings. Listing facts must come from retrieval, enrichment, and ranking tools. The model routes, asks minimal follow-up questions, and explains tool-backed results.

### 2. MVP Scope

The v1 OpenAI-facing tool set has six tools:

1. `update_user_state`
2. `get_campus_context`
3. `retrieve_listings`
4. `enrich_listings`
5. `rank_listings`
6. `compare_listings`

Internally, these tools may call modular services for campus lookup, source selection, scraping, parsing, snapshotting, freshness checks, normalization, price-per-person calculation, approximate commute, context enrichment, and ranking.

Out of scope for v1:

- Zillow, Apartments.com, Facebook groups, private sublet groups, and login-gated sources.
- Live transit routing.
- Crime scores or safe/unsafe labels.
- Automated landlord outreach.
- Learned ranking from user behavior.
- Separate parent accounts or parent profiles.

### 3. Source Policy

v1 may use only:

- Official university housing or off-campus portals.
- Student housing portals that are public and non-login.
- Property-manager listing pages that are public and non-login.
- Public pages that do not require bypassing access controls.

Every source record must include:

- `source_id`
- `source_name`
- `source_type`
- `base_url`
- `source_allowed_for_v1`
- `requires_login`
- `access_control_notes`
- `robots_or_terms_notes`
- `adapter_status`

Rules:

- `source_allowed_for_v1` must be `true` before a source adapter can run in production mode.
- If a page requires login, paywall access, private group membership, CAPTCHA bypass, or other access control, the adapter must skip it.
- If source policy is unclear, the source can be used only in manual research mode and must not feed ranked recommendations.
- Source errors must be stored and surfaced internally so failures do not become hallucinated results.

### 4. Data Model

#### Session State

```json
{
  "session_id": "string",
  "university": "string|null",
  "campus_id": "string|null",
  "budget_max_per_person": "number|null",
  "budget_target_per_person": "number|null",
  "move_in_date": "string|null",
  "roommates_open": "boolean|null",
  "preferred_roommate_count": "string|null",
  "commute_max_minutes": "number|null",
  "safety_context_priority": "low|medium|high|null",
  "student_social_priority": "low|medium|high|null",
  "parents_involved": "boolean|null",
  "parent_priority": "string|null",
  "guarantor_needed": "boolean|null",
  "lease_length_months": "number|null",
  "furnished_preference": "required|preferred|not_needed|unknown|null",
  "assumptions": "array",
  "updated_at": "string"
}
```

Default budget assumption:

- If a student says "my max is $1,200", interpret this as monthly per-person budget unless contradicted.
- Always show this assumption to the user.

#### Campus Context

```json
{
  "campus_id": "string",
  "university_id": "string",
  "university_name": "string",
  "campus_name": "string",
  "address": "string",
  "lat": "number",
  "lng": "number",
  "anchor_points": "array",
  "student_areas": "array",
  "official_resources": "array",
  "transport_notes": "array",
  "housing_notes": "array",
  "confidence": "number"
}
```

Initial supported campuses:

- Drexel University, University City campus.
- Temple University, Main Campus.
- University of Pennsylvania, University City campus.

Later Philadelphia expansion:

- Thomas Jefferson University.
- Saint Joseph's University.
- La Salle University.
- Villanova University.
- Bryn Mawr College.
- Haverford College.

#### Source Record

```json
{
  "source_id": "string",
  "source_name": "string",
  "source_type": "official_university_portal|student_housing_portal|property_manager",
  "base_url": "string",
  "source_allowed_for_v1": "boolean",
  "requires_login": "boolean",
  "adapter_status": "active|paused|manual_only|blocked",
  "last_health_check_at": "string|null",
  "notes": "string|null"
}
```

#### Listing Snapshot

```json
{
  "snapshot_id": "string",
  "source_id": "string",
  "source_url": "string",
  "source_listing_id": "string|null",
  "raw_title": "string|null",
  "raw_price": "string|null",
  "raw_location": "string|null",
  "raw_html_hash": "string|null",
  "retrieved_at": "string",
  "freshness_status": "fresh_today|seen_within_7_days|needs_verification|stale|removed|unknown",
  "freshness_evidence": "array",
  "parser_version": "string",
  "source_allowed_for_v1": "boolean"
}
```

#### Canonical Listing

```json
{
  "listing_id": "string",
  "source_urls": "array",
  "title": "string|null",
  "address_raw": "string|null",
  "address_normalized": "string|null",
  "lat": "number|null",
  "lng": "number|null",
  "rent_raw": "string|null",
  "rent_total_monthly": "number|null",
  "rent_per_person_monthly": "number|null",
  "price_basis": "total_unit|per_person|per_bedroom|from_price|unknown",
  "utilities_status": "included|not_included|partial|unknown",
  "fees_status": "known|partial|unknown",
  "all_in_estimate_per_person": "number|null",
  "bedrooms": "number|null",
  "bathrooms": "number|null",
  "available_date": "string|null",
  "lease_terms": "array",
  "furnished": "boolean|null",
  "contact": "object|null",
  "dedupe_status": "unique|merged|possible_duplicate|unknown",
  "freshness_status": "fresh_today|seen_within_7_days|needs_verification|stale|removed|unknown",
  "missing_fields": "array",
  "confidence": "number"
}
```

#### Listing Enrichment

```json
{
  "listing_id": "string",
  "walk_minutes_to_campus": "number|null",
  "walk_distance_miles": "number|null",
  "commute_confidence": "number",
  "student_area_fit": "number|null",
  "managed_or_student_source_signal": "boolean|null",
  "parent_explainability_notes": "array",
  "safety_context_notes": "array",
  "limitations": "array"
}
```

No field may be named `safety_score` in v1. Internally, ranking may use a `safety_context_fit` feature derived from allowed proxies, but the user-facing product must describe it as contextual fit, not objective safety.

#### Ranking Result

```json
{
  "ranking_id": "string",
  "session_id": "string",
  "ranking_mode": "student_default|budget_first|commute_first|safety_context_first|parent_balanced",
  "ranked_listings": "array",
  "excluded_listings": "array",
  "ranking_weights": "object",
  "created_at": "string"
}
```

#### Tool Trace

```json
{
  "trace_id": "string",
  "session_id": "string",
  "turn_id": "string",
  "tool_name": "string",
  "input_summary": "object",
  "output_summary": "object",
  "errors": "array",
  "created_at": "string"
}
```

### 5. Internal Scraper And Source-Adapter Architecture

The OpenAI model calls `retrieve_listings`; it does not call scraper internals directly.

Recommended internal modules:

- `source_registry`: Stores allowed source metadata and adapter status.
- `source_selector`: Chooses sources based on campus, source policy, and user constraints.
- `source_adapter`: One adapter per source family or site.
- `page_fetcher`: Fetches public pages with timeouts, rate limits, and user-agent policy.
- `parser`: Extracts raw title, price, location, availability, lease terms, contact method, and detail URLs.
- `freshness_checker`: Rechecks same-day availability where possible.
- `snapshot_store`: Stores raw listing snapshots and parser metadata.
- `source_health`: Tracks failures, parser drift, and blocked sources.

Adapter contract:

```ts
interface ListingSourceAdapter {
  sourceId: string;
  canRun(context: CampusContext, policy: SourcePolicy): Promise<boolean>;
  search(input: ListingSearchInput): Promise<RawListingRef[]>;
  fetchDetails(ref: RawListingRef): Promise<ListingDetailSnapshot>;
  checkFreshness(snapshot: ListingDetailSnapshot): Promise<FreshnessResult>;
}
```

Hard adapter requirements:

- Never bypass login or access controls.
- Never silently fabricate missing listing data.
- Capture source URL for every listing.
- Mark parser confidence and missing fields.
- Return source errors separately from empty search results.

### 6. Runtime Flow

Default order:

```text
User preference extraction
-> campus/context resolution
-> source selection
-> listing retrieval
-> same-day freshness check where possible
-> normalization and deduplication
-> price-per-person and all-in estimate
-> approximate walking commute
-> context proxy enrichment
-> ranking
-> explanation
```

Router behavior:

1. Extract newly stated preferences and call `update_user_state`.
2. If university is known and campus context is missing, call `get_campus_context`.
3. If the user only asks conceptual trade-off advice, answer without retrieving listings and clearly say no real listings have been checked.
4. If the user asks for real options, require campus and enough budget/unit intent before retrieval.
5. Call `retrieve_listings`.
6. Call `enrich_listings` before ranking.
7. Call `rank_listings`.
8. If the user asks to compare two or more listings, call `compare_listings` only after listings have price, location, freshness, and enrichment.

Minimal follow-up policy:

- Ask no more than two questions in one turn.
- Search can proceed without move-in date, but results must be caveated.
- Search cannot proceed without campus or location anchor.
- Search cannot proceed when budget depends on roommate openness and roommate openness is unknown.

### 7. Ranking Rules

Ranking presets:

```json
{
  "student_default": {
    "all_in_cost": 0.28,
    "commute": 0.24,
    "student_area_fit": 0.20,
    "freshness": 0.14,
    "listing_quality": 0.10,
    "parent_explainability": 0.04
  },
  "budget_first": {
    "all_in_cost": 0.42,
    "commute": 0.18,
    "freshness": 0.14,
    "student_area_fit": 0.12,
    "listing_quality": 0.10,
    "parent_explainability": 0.04
  },
  "commute_first": {
    "commute": 0.40,
    "all_in_cost": 0.22,
    "freshness": 0.14,
    "student_area_fit": 0.12,
    "listing_quality": 0.08,
    "parent_explainability": 0.04
  },
  "safety_context_first": {
    "safety_context_fit": 0.30,
    "commute": 0.24,
    "all_in_cost": 0.18,
    "freshness": 0.14,
    "student_area_fit": 0.08,
    "listing_quality": 0.06
  },
  "parent_balanced": {
    "parent_explainability": 0.24,
    "safety_context_fit": 0.22,
    "freshness": 0.18,
    "commute": 0.18,
    "all_in_cost": 0.14,
    "student_area_fit": 0.04
  }
}
```

Hard exclusions:

- Stale or removed listing.
- Source not allowed for v1.
- No source URL.
- No price or unknown price basis.
- No address or usable approximate location.
- No dedupe status.

Allowed but penalized:

- Snapshot seen within 7 days but not rechecked today: label as `needs verification`.
- Utilities unknown: rank using rent-only and apply missing-data penalty.
- Fees unknown: apply missing-data penalty.
- Move-in date unknown: show caveat and do not call listing "ready to contact."

All-in cost behavior:

- Prefer `all_in_estimate_per_person` when available.
- If utilities or fees are unknown, use rent-only with missing-data penalty.
- Always display whether cost is rent-only or all-in estimate.

Safety-context fit may use only:

- Closer campus proximity.
- Shorter walking commute.
- More direct route proxy.
- Managed building or student-oriented source.
- Student-area fit based on campus proximity and housing type.
- University safety resource availability.

Safety-context fit may not use:

- Crime scores.
- Protected-class demographics.
- Claims that an area is safe or unsafe.
- Parent comfort guarantees.

### 8. Anti-Hallucination Rules

Before tools return listing data, the agent may say:

- "I can search for listings using your constraints."
- "I need your budget, campus, or roommate preference before narrowing properly."
- "I can search broadly without your move-in date, but I need it before treating any listing as genuinely viable."
- "I do not have real listings yet."

Before tools return listing data, the agent must not say:

- "Here are the top listings."
- "This building is available."
- "This rent is typical for that exact area."
- "This neighborhood is safe."
- "This commute is 15 minutes."
- "Your parents will be comfortable with this."

Every listing claim must be backed by a tool result:

```json
{
  "claim": "Rent is about $1,100/person",
  "claim_type": "tool_fact",
  "source_tool": "enrich_listings",
  "confidence": 0.82
}
```

Every model inference must be framed as an inference:

```json
{
  "claim": "This may be easier to explain to parents",
  "claim_type": "model_inference",
  "based_on": ["managed_property_source", "fresh_today", "shorter_walk"],
  "confidence": 0.64
}
```

User-facing language:

- Tool fact: "The listing shows..."
- Inference: "This looks stronger for your concern because..."
- Unknown: "I cannot verify this yet."

### 9. Safety-Language Policy

Never say:

- "This area is safe."
- "This area is unsafe."
- "Your parents should not worry."
- "This route is safe at night."

Use:

- "Stronger fit for your safety concern because..."
- "This is not a guarantee of safety."
- "I would treat this as needing extra verification."
- "The route/building/source context looks stronger than the alternatives."

Allowed v1 safety-context language:

```text
This looks stronger for your safety concern because it is closer to campus, has a shorter walk, and comes from a managed/student-oriented source. That is still context, not a guarantee of safety.
```

Disallowed v1 safety-context language:

```text
This is the safest option.
```

### 10. Freshness Policy

Storage freshness:

- Listing snapshots may remain in the prototype database for debugging if retrieved within the last 7 days.
- Snapshots older than 7 days cannot feed recommendations without rechecking.

Shortlist freshness:

- A ranked shortlist should use listings rechecked today where possible.
- Listings not rechecked today may appear only with an inline `needs verification` warning.
- Stale or removed listings must not be ranked as live options.

Freshness statuses:

- `fresh_today`: Rechecked today and still appears viable.
- `seen_within_7_days`: Seen recently but not rechecked today.
- `needs_verification`: Source could not be rechecked today or availability is unclear.
- `stale`: Too old or signs suggest no longer viable.
- `removed`: Listing page removed or no longer present.
- `unknown`: Insufficient evidence; not eligible for final recommendation.

### 11. User-Facing Response Templates

#### Initial Setup Response

```text
I can start with [university/campus]. I am assuming your budget means per person per month.

Before I search, I need one thing: [question].

I can search broadly without your move-in date, but I will need it before treating any listing as genuinely viable.
```

#### Ranked Card

```text
[Rank]. [Listing title] - [short fit label]
Cost: [all-in estimate or rent-only caveat]
Walk to campus: [minutes] estimated
Freshness: [fresh today or needs verification]
Why it fits: [tool-backed facts and caveated inference]
Main trade-off: [trade-off]
Source: [source name/link]
```

#### Needs Verification Inline Warning

```text
Needs verification: I found this in a recent source snapshot, but I could not confirm same-day availability. I would not contact the landlord until this is rechecked.
```

#### Safety-Context Note

```text
Safety context: This looks stronger for your concern because [allowed context proxies]. This is not a guarantee of safety.
```

#### No Results

```text
I did not find rankable listings from the allowed v1 sources with those constraints. I can widen the budget, widen the walk radius, include more property-manager sources, or keep the same constraints and retry later.
```

#### Comparison

```text
Best fit for you: [listing]
Best parent-balanced fit: [listing]

The real trade-off is [short explanation]. I would verify [missing fields] before treating either as ready to contact.
```

### 12. Privacy And Deletion Controls

Prototype storage may include:

- Session preferences.
- Campus context.
- Listing snapshots.
- Tool traces.
- Source errors.

Do not store:

- Unnecessary personal identifiers.
- Parent contact details unless explicitly needed later.
- Application materials.
- Messages to landlords in v1.

Deletion controls required in the spec:

- Delete session state by `session_id`.
- Delete user assumptions and preference history.
- Delete listing snapshots associated with a session.
- Keep aggregate source health metrics only if they cannot identify the user.

## Part II: OpenAI-Facing Tool Schemas

### 1. `update_user_state`

```json
{
  "name": "update_user_state",
  "description": "Updates session-level rental-search state, including hard constraints, soft preferences, parent/stakeholder preferences, and explicit assumptions.",
  "input_schema": {
    "type": "object",
    "required": ["session_id", "updates"],
    "properties": {
      "session_id": { "type": "string" },
      "updates": {
        "type": "object",
        "properties": {
          "university": { "type": ["string", "null"] },
          "campus_id": { "type": ["string", "null"] },
          "budget_max_per_person": { "type": ["number", "null"] },
          "budget_target_per_person": { "type": ["number", "null"] },
          "move_in_date": { "type": ["string", "null"], "description": "ISO date or null" },
          "roommates_open": { "type": ["boolean", "null"] },
          "preferred_roommate_count": { "type": ["string", "null"] },
          "commute_max_minutes": { "type": ["number", "null"] },
          "safety_context_priority": { "type": ["string", "null"], "enum": ["low", "medium", "high", null] },
          "student_social_priority": { "type": ["string", "null"], "enum": ["low", "medium", "high", null] },
          "parents_involved": { "type": ["boolean", "null"] },
          "parent_priority": { "type": ["string", "null"] },
          "guarantor_needed": { "type": ["boolean", "null"] },
          "lease_length_months": { "type": ["number", "null"] },
          "furnished_preference": { "type": ["string", "null"], "enum": ["required", "preferred", "not_needed", "unknown", null] }
        }
      },
      "assumptions": {
        "type": "array",
        "items": {
          "type": "object",
          "required": ["field", "assumption", "confidence"],
          "properties": {
            "field": { "type": "string" },
            "assumption": { "type": "string" },
            "confidence": { "type": "number" }
          }
        }
      }
    }
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "state": { "type": "object" },
      "changed_fields": { "type": "array", "items": { "type": "string" } },
      "missing_critical_fields": { "type": "array", "items": { "type": "string" } },
      "conflicts": { "type": "array", "items": { "type": "string" } }
    }
  },
  "must_not_be_called_when": [
    "The user has not provided or implied any new preference, constraint, stakeholder preference, or correction."
  ]
}
```

### 2. `get_campus_context`

```json
{
  "name": "get_campus_context",
  "description": "Resolves a Philadelphia university/campus and returns campus anchors, student-area context, official resources, transport notes, and housing caveats.",
  "input_schema": {
    "type": "object",
    "required": ["university_name"],
    "properties": {
      "university_name": { "type": "string" },
      "campus_hint": { "type": ["string", "null"] },
      "city_hint": { "type": ["string", "null"], "default": "Philadelphia" },
      "max_commute_minutes": { "type": ["number", "null"] },
      "context_types": {
        "type": "array",
        "items": {
          "type": "string",
          "enum": ["campus_anchor", "student_areas", "official_resources", "transport", "housing_notes"]
        }
      }
    }
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "university_id": { "type": "string" },
      "university_name": { "type": "string" },
      "campuses": { "type": "array", "items": { "type": "object" } },
      "selected_campus_id": { "type": ["string", "null"] },
      "student_areas": { "type": "array", "items": { "type": "object" } },
      "official_resources": { "type": "array", "items": { "type": "object" } },
      "transport_notes": { "type": "array", "items": { "type": "string" } },
      "housing_notes": { "type": "array", "items": { "type": "string" } },
      "recommended_initial_search_radius_miles": { "type": "number" },
      "confidence": { "type": "number" },
      "needs_user_confirmation": { "type": "boolean" }
    }
  },
  "must_not_be_called_when": [
    "Campus has already been resolved with high confidence and the user has not changed university or campus."
  ]
}
```

### 3. `retrieve_listings`

```json
{
  "name": "retrieve_listings",
  "description": "Selects allowed v1 sources, retrieves public non-login listings, extracts basic details, checks same-day freshness where possible, and stores listing snapshots.",
  "input_schema": {
    "type": "object",
    "required": ["session_id", "campus_id", "search_constraints", "source_policy", "limit"],
    "properties": {
      "session_id": { "type": "string" },
      "campus_id": { "type": "string" },
      "search_constraints": {
        "type": "object",
        "properties": {
          "budget_max_per_person": { "type": ["number", "null"] },
          "roommates_open": { "type": ["boolean", "null"] },
          "bedrooms": { "type": ["string", "null"] },
          "move_in_date": { "type": ["string", "null"] },
          "housing_types": {
            "type": "array",
            "items": {
              "type": "string",
              "enum": ["studio", "one_bed", "shared_apartment", "private_room", "student_housing", "house_share"]
            }
          },
          "target_areas": { "type": "array", "items": { "type": "string" } }
        }
      },
      "source_policy": {
        "type": "object",
        "properties": {
          "allowed_source_types": {
            "type": "array",
            "items": {
              "type": "string",
              "enum": ["official_university_portal", "student_housing_portal", "property_manager"]
            }
          },
          "non_login_public_only": { "type": "boolean" },
          "require_source_allowed_for_v1": { "type": "boolean" },
          "avoid_sources": { "type": "array", "items": { "type": "string" } }
        }
      },
      "limit": { "type": "number" }
    }
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "listing_snapshots": { "type": "array", "items": { "type": "object" } },
      "source_errors": { "type": "array", "items": { "type": "object" } },
      "skipped_sources": { "type": "array", "items": { "type": "object" } },
      "result_count": { "type": "number" },
      "retrieved_at": { "type": "string" }
    }
  },
  "must_not_be_called_when": [
    "Campus is unknown.",
    "The user has not asked for real listings or listing refresh.",
    "Budget and roommate/unit intent are too ambiguous to form a responsible search."
  ]
}
```

### 4. `enrich_listings`

```json
{
  "name": "enrich_listings",
  "description": "Normalizes and deduplicates retrieved listings, calculates per-person and all-in cost estimates, estimates walking commute, and adds allowed context proxies.",
  "input_schema": {
    "type": "object",
    "required": ["session_id", "campus_id", "listing_snapshots", "enrichment_options"],
    "properties": {
      "session_id": { "type": "string" },
      "campus_id": { "type": "string" },
      "listing_snapshots": { "type": "array", "items": { "type": "object" } },
      "enrichment_options": {
        "type": "object",
        "properties": {
          "dedupe": { "type": "boolean" },
          "calculate_price_per_person": { "type": "boolean" },
          "estimate_all_in_cost": { "type": "boolean" },
          "calculate_approx_walk_commute": { "type": "boolean" },
          "include_safety_context_proxies": { "type": "boolean" },
          "include_parent_explainability": { "type": "boolean" }
        }
      }
    }
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "canonical_listings": { "type": "array", "items": { "type": "object" } },
      "duplicate_groups": { "type": "array", "items": { "type": "object" } },
      "enrichment_errors": { "type": "array", "items": { "type": "object" } },
      "limitations": { "type": "array", "items": { "type": "string" } }
    }
  },
  "must_not_be_called_when": [
    "No listing snapshots exist.",
    "The user is not asking for real listings or listing-specific advice."
  ]
}
```

### 5. `rank_listings`

```json
{
  "name": "rank_listings",
  "description": "Applies hard filters, fixed v1 ranking presets, missing-data penalties, and returns ranked listing recommendations with caveated explanations.",
  "input_schema": {
    "type": "object",
    "required": ["session_id", "listings", "user_state", "ranking_mode", "top_n"],
    "properties": {
      "session_id": { "type": "string" },
      "listings": { "type": "array", "items": { "type": "object" } },
      "user_state": { "type": "object" },
      "ranking_mode": {
        "type": "string",
        "enum": ["student_default", "budget_first", "commute_first", "safety_context_first", "parent_balanced"]
      },
      "top_n": { "type": "number" },
      "allow_stretch_budget": { "type": "boolean" }
    }
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "ranked_listings": { "type": "array", "items": { "type": "object" } },
      "excluded_listings": { "type": "array", "items": { "type": "object" } },
      "ranking_weights": { "type": "object" },
      "missing_data_penalties": { "type": "array", "items": { "type": "object" } },
      "confidence": { "type": "number" }
    }
  },
  "must_not_be_called_when": [
    "Listings have not been retrieved.",
    "Listings have not been enriched.",
    "Listings lack source URL, price basis, freshness status, dedupe status, or usable location.",
    "Freshness has not been checked."
  ]
}
```

### 6. `compare_listings`

```json
{
  "name": "compare_listings",
  "description": "Compares selected enriched listings across cost, commute, freshness, student fit, parent explainability, lease clarity, and caveated safety-context fit.",
  "input_schema": {
    "type": "object",
    "required": ["session_id", "listing_ids", "comparison_dimensions", "user_state"],
    "properties": {
      "session_id": { "type": "string" },
      "listing_ids": { "type": "array", "items": { "type": "string" } },
      "comparison_dimensions": {
        "type": "array",
        "items": {
          "type": "string",
          "enum": ["cost", "commute", "freshness", "student_fit", "parent_explainability", "lease", "safety_context_fit", "overall"]
        }
      },
      "user_state": { "type": "object" }
    }
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "comparison_rows": { "type": "array", "items": { "type": "object" } },
      "best_for_student": { "type": ["string", "null"] },
      "best_parent_balanced": { "type": ["string", "null"] },
      "main_tradeoffs": { "type": "array", "items": { "type": "string" } },
      "blocking_unknowns": { "type": "array", "items": { "type": "string" } },
      "confidence": { "type": "number" }
    }
  },
  "must_not_be_called_when": [
    "Fewer than two listings are selected.",
    "Any selected listing is stale or removed.",
    "Selected listings lack comparable price, location, or freshness data."
  ]
}
```

## Part III: Implementation Tickets

### Ticket 1: Session State Store

Build `update_user_state` with:

- Session creation and update.
- Preference conflict detection.
- Budget default assumption for per-person monthly rent.
- Parent preference layer inside the same session.
- Deletion endpoint for session state.

Acceptance criteria:

- Updates return changed fields and missing critical fields.
- Conflicting updates are reported instead of silently overwritten.
- Deleting a session removes state and assumptions.

### Ticket 2: Campus Context For Drexel, Temple, And Penn

Build `get_campus_context` with:

- Canonical campus records.
- Campus coordinates and anchor points.
- Student-area context.
- Official housing resource links.
- Campus ambiguity handling.

Acceptance criteria:

- Drexel, Temple, and Penn resolve without confirmation when no ambiguity exists.
- Ambiguous inputs return campuses and `needs_user_confirmation: true`.
- Unsupported Philadelphia schools return a clear unsupported-campus response.

### Ticket 3: Source Registry And V1 Source Policy

Build source registry with:

- `source_allowed_for_v1`.
- Source type.
- Login/access-control flags.
- Adapter health status.
- Skip reasons.

Acceptance criteria:

- Disallowed sources are skipped before fetch.
- Login-required sources never run.
- Source errors are returned separately from zero-result searches.

### Ticket 4: Retrieval Pipeline

Build `retrieve_listings` with:

- Source selection.
- Public-page fetch.
- Basic parsing.
- Detail-page extraction where allowed.
- Same-day freshness check where possible.
- Snapshot storage.

Acceptance criteria:

- Every listing snapshot has source URL, source ID, retrieval timestamp, parser version, and freshness status.
- Source failures are stored and surfaced.
- No listing from a disallowed source can appear in output.

### Ticket 5: Normalization And Enrichment Pipeline

Build `enrich_listings` with:

- Address normalization.
- Deduplication.
- Price basis parsing.
- Per-person rent calculation.
- All-in estimate when utilities/fees are available.
- Approximate walking distance/time.
- Context proxy enrichment.

Acceptance criteria:

- Unknown price basis blocks ranking.
- Utilities/fees unknown adds missing-data penalty.
- No field named `safety_score` is produced.
- Approximate commute is labeled approximate.

### Ticket 6: Ranking Engine

Build `rank_listings` with:

- Fixed v1 ranking presets.
- Hard exclusions.
- Missing-data penalties.
- Inline verification warnings.
- Ranked cards data.

Acceptance criteria:

- Stale and removed listings are excluded.
- Non-rechecked recent listings are labeled `needs verification`.
- Ranked output includes ranking weights, main trade-off, and confidence.
- Safety-context language uses allowed proxies only.

### Ticket 7: Comparison Tool

Build `compare_listings` with:

- Selected listing validation.
- Comparison rows.
- Best-for-student and parent-balanced recommendations.
- Blocking unknowns.

Acceptance criteria:

- Fewer than two listings fails with a clear missing-selection response.
- Stale/removed selected listings block comparison.
- Output separates facts from caveated inferences.

### Ticket 8: Response Renderer

Build response templates for:

- Initial setup.
- Ranked shortlist.
- Needs verification warnings.
- No results.
- Comparison.

Acceptance criteria:

- Ranked cards show source URL, freshness, cost basis, commute estimate, and trade-off.
- Safety language never says safe or unsafe.
- Move-in-date caveat appears when move-in date is unknown.

### Ticket 9: Privacy And Debug Deletion

Build deletion controls for:

- Session state.
- Assumptions.
- Session-linked listing snapshots.
- Tool traces.

Acceptance criteria:

- Deletion removes user-specific prototype debugging data.
- Aggregate source health can remain only if not user-identifying.

## Testing Plan

### Unit Tests

- Preference extraction and state updates.
- Budget assumption handling.
- Campus alias resolution.
- Source policy filtering.
- Price-basis parsing.
- Per-person rent calculation.
- Missing-data penalty calculation.
- Safety-language lint rules.

### Integration Tests

- Drexel initial search setup.
- Temple budget-first search.
- Penn parent-balanced search.
- No results from allowed sources.
- Source adapter failure.
- Listing stale or removed.
- Listing seen within 7 days but not rechecked today.

### Golden Conversation Tests

Test these messages:

- "I need somewhere near Drexel."
- "Show me cheap places under $1,200."
- "My parents care about safety."
- "Compare these two."
- "Is this too far?"
- "Can I afford this?"

Each golden test must verify:

- Correct tool order.
- No invented listing facts.
- Campus resolved before search.
- Freshness checked before ranking.
- Safety language is caveated.
- Missing move-in date is caveated but does not block broad search.

### Source Adapter Tests

- Snapshot parser fixtures for every source.
- Parser drift detection when expected fields disappear.
- Source health check.
- Public-only policy enforcement.

### Manual QA

- Click every source URL in top-ranked results.
- Verify rent basis shown in UI matches source.
- Verify "needs verification" label when same-day recheck fails.
- Verify stale/removed listings do not rank as live options.
- Verify no response says an area is safe or unsafe.

## Spec Lock Summary

This prototype starts narrow: Philadelphia only, three universities, public non-login sources, six OpenAI-facing tools, approximate walking commute, no crime scores, no safety labels, and freshness-first listing trust.

The architecture remains modular so later versions can split `retrieve_listings` and `enrich_listings` into the original larger tool chain once the first source and ranking loop works.

# AI-DIGIPIN Address Intelligence

> API-first infrastructure layer that transforms unstructured Indian addresses
> into validated, structured, confidence-scored, and DIGIPIN-linked
> **Delivery Points** for last-mile logistics, e-commerce, and food-delivery
> platforms.

This is not a courier or map app. **The API is the product.** The included
frontend is a demo/admin console for exercising and inspecting the API — any
integrating platform is expected to call the endpoints directly.

---

## Table of contents

1. [Problem](#1-problem)
2. [Solution](#2-solution)
3. [Architecture](#3-architecture)
4. [Data flow](#4-data-flow)
5. [API reference](#5-api-reference)
6. [Integration example](#6-integration-example)
7. [Setup](#7-setup)
8. [Testing](#8-testing)
9. [Security](#9-security)
10. [Limitations](#10-limitations)
11. [Production roadmap](#11-production-roadmap)
12. [What changed from v1](#12-what-changed-from-v1-changelog)

---

## 1. Problem

Last-mile delivery in India faces two compounding problems:

1. **Unstructured addresses.** Addresses are landmark-heavy and inconsistent
   ("near Durga Temple, opposite the blue gate") rather than standardized
   street/number formats, forcing couriers into probabilistic, human-judgment
   searching instead of deterministic lookup.
2. **Vertical blindness.** GPS is a 2D system. In dense multi-story buildings
   it gets a courier to the building's footprint but says nothing about which
   floor or unit to go to — the "last 20 meters" problem.

A third, B2B-specific problem sits on top of both: **no platform-grade way to
know how good an address actually is** before dispatching a courier against
it, or to distinguish "this will probably fail" from "this is fine" in a way
an integrating system can act on programmatically.

## 2. Solution

Convert a raw address into a **Delivery Point**: a DIGIPIN-anchored,
quality-scored, risk-graded, verification-tracked object that a delivery
platform's own systems can consume through a clean API, without ever seeing
this project's UI.

```
Raw Address
  → NLP parsing              (extract structured fields from free text)
  → Normalization            (canonicalize, recover missed fields, clean artifacts)
  → Quality scoring          (0–100, how much structured data do we have)
  → Validation               (garbage/ambiguity detection — never guess)
  → Geocoding                (provider-abstracted; Nominatim in dev)
  → DIGIPIN encode/decode    (deterministic 4m×4m grid cell)
  → Delivery Point assembly  (2D location + vertical data, kept separate)
  → Risk scoring             (LOW/MEDIUM/HIGH/CRITICAL, rule-based, explainable)
  → Verification tracking    (per-component state, never auto-verified)
  → Courier-ready output
```

## 3. Architecture

### 3.1 Original system (v1) — what it did well and where it fell short

The original `ai-digipin-smart-courier` repo got the hard, novel part
right: `digipin_eng9ine.py` correctly implements the published DIGIPIN grid
spec with a clean encode/decode round-trip, and `nlp_parser.py` reliably
extracts floor/unit/landmark from a well-formed address. Both are carried
into this version **completely unchanged** — see
[§12](#12-what-changed-from-v1-changelog).

What it didn't have was any notion of *pipeline quality control*. It was a
straight-line function chain (`parse → geocode → encode → fuse`) that always
produced an output, with no way to say "this input was too weak to trust" or
"this location is ambiguous, please confirm." Concretely, testing against the
project's own listed demo scenarios during the initial repo inspection
surfaced:

- A bare house number like `B-402` (no "Flat"/"House" keyword prefix) was
  silently dropped, and the cleaned address string was left with dangling
  `", , "` artifacts from the stripped-out floor/landmark substrings.
- Nonsense input (`"asdkfj laksjdf laksjdlfk"`) scored an identical
  `confidence: 0.4` to a real-but-sparse address like `"Sector 62, Noida"` —
  there was no way to tell them apart programmatically.
- Nominatim was called with `limit: 1` and the top result taken
  unconditionally — genuinely ambiguous addresses (e.g. "Sector 62" exists in
  multiple UP cities) were resolved to an arbitrary guess with no signal that
  a guess had even been made.
- A single `confidence` float conflated "did parsing succeed," "is this
  address geocodable," and "will this delivery work" into one number with no
  way to separate them.

### 3.2 New architecture

```
backend/
├── main.py                    FastAPI app assembly, CORS, startup warnings, health check
├── config.py                  Env-driven settings (no hardcoded secrets)
├── logging_config.py          Structured JSON logging, PII-safe address redaction
├── api/
│   ├── deps.py                 API-key auth, tenant context, in-memory rate limiter
│   └── v1/
│       ├── address.py           POST /parse, /validate, /resolve
│       └── digipin.py           GET /{code}, POST /decode
├── schemas/                    Pydantic v2 request/response models (framework layer only)
│   ├── common.py                 Shared enums (RiskLevel, VerificationState, ...)
│   ├── address.py
│   └── digipin.py
├── core/                        Framework-free business logic (testable without FastAPI)
│   ├── digipin_engine.py         UNCHANGED from v1 — grid encode/decode
│   ├── nlp_parser.py             UNCHANGED from v1 — regex address extraction
│   ├── vertical_fusion.py        UNCHANGED from v1 — instruction text builder
│   ├── normalization.py          NEW — canonicalizes parser output, recovers gaps
│   ├── quality.py                NEW — 0–100 completeness score + reasons
│   ├── validation.py             NEW — garbage/ambiguity detection, never auto-guesses
│   ├── risk.py                   NEW — rule-based LOW/MEDIUM/HIGH/CRITICAL scoring
│   ├── verification.py           NEW — per-component verification state machine
│   ├── delivery_point.py         NEW — first-class DeliveryPoint object
│   ├── pipeline.py               NEW — orchestrates all of the above
│   └── geocoding/
│       ├── base.py                 Provider-agnostic interface + error types
│       └── nominatim.py            Nominatim implementation of that interface
├── tests/                        pytest suite, one file per module + API tests
├── requirements.txt
└── .env.example
frontend/
├── index.html                  B2B admin console: Address → Quality → Validation →
│                                Location → DIGIPIN → Delivery Point → Vertical →
│                                Risk → Verification → Instructions → Map
└── app.js
```

**Design principles applied:**

- **`core/` has zero framework dependency.** Every business-logic module
  (`normalization.py` through `pipeline.py`) imports only stdlib and other
  `core/` modules — no `fastapi`, no `pydantic`. This is what let the entire
  pipeline be unit-tested and demonstrated end-to-end even in a sandbox with
  no network access to install packages (see [§8](#8-testing)). It also
  means the pipeline is reusable outside an HTTP context (a batch job, a
  CLI, a queue worker) with no changes.
- **Nothing that worked was rewritten.** `digipin_engine.py`, `nlp_parser.py`,
  and `vertical_fusion.py` are byte-for-byte identical to the original repo,
  down to the `__main__` self-test blocks — the only changes were import
  paths, to reflect their new location inside the `core/` package.
- **Provider abstraction, not a provider swap.** `core/geocoding/base.py`
  defines a `GeocodingProvider` protocol; `nominatim.py` is one
  implementation of it. Adding Google/Mapbox/HERE later means adding one new
  file and changing one line in `config.py` — `api/v1/address.py` never
  needs to know which provider is behind it.
- **Quality, risk, and verification are three different questions,** not one
  overloaded confidence float: quality asks "how much data do we have,"
  validation asks "did geocoding resolve cleanly," risk asks "how likely is
  this delivery to fail," and verification asks "has a human/system actually
  confirmed this." Collapsing these was the core weakness of v1.
- **No database, no auth framework, no ML model.** Per the brief: nothing is
  persisted (a `deliveries` table keyed by DIGIPIN remains a documented next
  step, not built), auth is a deliberately simple static API-key/tenant map,
  and every scoring function is a transparent, rule-based point system —
  never a fabricated percentage or an opaque model.

## 4. Data flow

```
POST /api/v1/address/resolve  { "address": "..." }
        │
        ▼
core.nlp_parser.parse_address()        → ParsedAddress (unchanged v1 logic)
        │
        ▼
core.normalization.normalize()         → NormalizedAddress (per-field FieldValue + source)
        │
        ▼
core.quality.score_address()           → QualityResult (0–100, label, reasons)
        │
        ▼
core.validation.validate_pre_geocode() → may REJECT here (garbage input, never geocoded)
        │
        ▼
core.geocoding.nominatim.geocode()     → List[GeocodeCandidate] (up to 5, ranked)
        │
        ▼
core.validation.validate_geocode_candidates()
        │           → may return NEEDS_CONFIRMATION (ambiguous candidates, caller must pick)
        ▼
core.digipin_engine.encode() / decode()   → DIGIPIN + BoundingBox (unchanged v1 logic)
        │
        ▼
core.risk.compute_risk()               → RiskResult (LOW/MEDIUM/HIGH/CRITICAL + reasons)
        │
        ▼
core.verification.build_verification_status()  → per-component UNVERIFIED/PARTIALLY_VERIFIED/VERIFIED
        │
        ▼
core.vertical_fusion.build_delivery_instructions()  → courier-facing text (unchanged v1 logic)
        │
        ▼
core.delivery_point.DeliveryPoint      → assembled, returned as JSON
```

If validation rejects the input or flags it as ambiguous, the pipeline stops
**before** geocoding a garbage string or guessing between ambiguous
candidates — the API returns a `422` with the quality/validation detail
instead of a fabricated `DeliveryPoint`.

## 5. API reference

Interactive OpenAPI docs are auto-generated at `http://localhost:8000/docs`
once the backend is running.

### `POST /api/v1/address/parse`

NLP + normalization + quality only — no geocoding call. Useful for tuning
extraction, or for a caller who wants to see what fields would be extracted
before spending geocoding budget.

```json
// Request
{ "address": "Flat 302, 3rd Floor, Near Durga Temple, Sector 62, Noida, 201301" }

// Response (200)
{
  "parsed_address": {
    "raw_address": "...",
    "house_no": { "value": null, "confidence": 0.0, "source": "not_provided" },
    "unit_no": { "value": "302", "confidence": 0.9, "source": "nlp_parsed" },
    "floor_level": { "value": "3", "confidence": 0.85, "source": "nlp_parsed" },
    "landmark": { "value": "Durga Temple", "confidence": 0.7, "source": "nlp_parsed" },
    "pincode": { "value": "201301", "confidence": 0.95, "source": "nlp_parsed" },
    "locality_text": { "value": "Sector 62, Noida", "confidence": 0.6, "source": "nlp_parsed" },
    "missing_fields": [],
    "warnings": []
  },
  "quality": { "score": 100, "label": "complete", "reasons": ["All structured fields present."] }
}
```

### `POST /api/v1/address/validate`

Parse + quality + full validation (including a geocoding-based ambiguity
check), but stops short of building a DeliveryPoint or DIGIPIN. Lets a
caller check "is this good enough to resolve" before committing.

```json
// Request
{ "address": "Sector 62" }

// Response (200) — ambiguous
{
  "parsed_address": { "...": "..." },
  "quality": { "score": 30, "label": "minimal", "reasons": ["..."] },
  "validation": {
    "decision": "needs_confirmation",
    "issues": ["2 candidate locations found with similar relevance; cannot auto-select without ambiguity."],
    "candidates": [
      { "latitude": 28.61, "longitude": 77.20, "importance": 0.42, "display_name": "Sector 62, Noida, UP" },
      { "latitude": 26.85, "longitude": 80.94, "importance": 0.40, "display_name": "Sector 62, Lucknow, UP" }
    ]
  }
}
```

### `POST /api/v1/address/resolve`

The full pipeline. Single call an integrating platform makes to turn a raw
address into a courier-ready Delivery Point.

```json
// Request
{
  "address": "Flat 302, 3rd Floor, Near Durga Temple, Sector 62, Noida, 201301",
  "access_notes": "Ring the bell twice",
  "confirmed_fields": []
}

// Response (200)
{
  "parsed_address": { "...": "..." },
  "quality": { "score": 100, "label": "complete", "reasons": ["..."] },
  "validation": { "decision": "proceed", "issues": [] },
  "delivery_point": {
    "delivery_point_id": "dp_a1b2c3d4e5f60718",
    "location": {
      "digipin": "39J-438-TJC7",
      "latitude": 28.6139,
      "longitude": 77.2090,
      "bounding_box": { "min_lat": 28.6138..., "max_lat": 28.6139..., "min_lon": 77.2089..., "max_lon": 77.2090... }
    },
    "vertical": {
      "house_no": null,
      "unit_no": "302",
      "floor_level": "3",
      "building_hint": "Sector 62, Noida",
      "requires_lift_confirmation": false
    },
    "landmark": "Durga Temple",
    "access_notes": "Ring the bell twice",
    "quality": { "score": 100, "label": "complete", "reasons": [...] },
    "validation": { "decision": "proceed", "issues": [] },
    "risk": { "level": "LOW", "points": 0, "reasons": ["No risk factors identified."] },
    "verification": {
      "components": {
        "address": { "state": "PARTIALLY_VERIFIED", "source": "nlp_parsed" },
        "location": { "state": "PARTIALLY_VERIFIED", "source": "nlp_parsed" },
        "building": { "state": "PARTIALLY_VERIFIED", "source": "nlp_parsed" },
        "entrance": { "state": "UNVERIFIED", "source": null },
        "floor": { "state": "PARTIALLY_VERIFIED", "source": "nlp_parsed" },
        "unit": { "state": "PARTIALLY_VERIFIED", "source": "nlp_parsed" }
      },
      "overall": "PARTIALLY_VERIFIED"
    },
    "delivery_instructions": "Navigate to the highlighted DIGIPIN cell. The building is near Durga Temple. Go to unit 302 on the 3rd floor. Ring the bell twice."
  }
}
```

**Ambiguous or invalid input → `422`**, with structured detail instead of a
guess:

```json
{
  "detail": {
    "message": "Address could not be automatically resolved.",
    "parsed_address": { "...": "..." },
    "quality": { "score": 30, "label": "minimal", "reasons": [...] },
    "validation": {
      "decision": "needs_confirmation",
      "issues": ["..."],
      "candidates": [ { "...": "..." } ]
    }
  }
}
```

To resolve an ambiguity, re-call `/resolve` with `select_candidate_index`
set to the chosen candidate's position in that `candidates` array.

**Other request fields:**

| Field | Purpose |
|---|---|
| `floor_level_override` / `unit_no_override` | Supply vertical data from merchant/order systems, overriding NLP extraction |
| `confirmed_fields` | Subset of `address, location, building, entrance, floor, unit` the caller attests has been explicitly confirmed — advances those to `VERIFIED`. Never inferred automatically. |
| `select_candidate_index` | Resolves a prior ambiguous result deterministically |

### `GET /api/v1/digipin/{code}` and `POST /api/v1/digipin/decode`

Reverse lookup: DIGIPIN → bounding box + center. Useful when a courier scans
or types a DIGIPIN directly.

```
GET /api/v1/digipin/39J-438-TJC7

{
  "digipin": "39J-438-TJC7",
  "bounding_box": { "min_lat": ..., "max_lat": ..., "min_lon": ..., "max_lon": ... },
  "center": { "latitude": 28.6139, "longitude": 77.2090 }
}
```

Invalid codes (wrong length, invalid symbol) return `422`.

### `GET /api/health`

Liveness check: `{"status": "ok"}`.

## 6. Integration example

A delivery platform's own backend, calling the API server-to-server:

```python
import httpx

API_KEY = "sk_live_your_tenant_key"
BASE_URL = "https://address-intelligence.yourcompany.com"

def resolve_delivery_point(raw_address: str, access_notes: str | None = None) -> dict:
    response = httpx.post(
        f"{BASE_URL}/api/v1/address/resolve",
        json={"address": raw_address, "access_notes": access_notes},
        headers={"X-API-Key": API_KEY},
        timeout=15.0,
    )
    if response.status_code == 422:
        detail = response.json()["detail"]
        if detail["validation"]["decision"] == "needs_confirmation":
            # Surface detail["validation"]["candidates"] to the customer /
            # ops team for manual selection, then re-call with
            # select_candidate_index.
            raise NeedsCustomerConfirmation(detail["validation"]["candidates"])
        raise AddressRejected(detail["message"])
    response.raise_for_status()
    return response.json()["delivery_point"]

dp = resolve_delivery_point("Flat 302, 3rd Floor, Near Durga Temple, Sector 62, Noida, 201301")
print(dp["location"]["digipin"], dp["risk"]["level"])
```

```bash
# Same call via curl
curl -X POST https://address-intelligence.yourcompany.com/api/v1/address/resolve \
  -H "Content-Type: application/json" \
  -H "X-API-Key: sk_live_your_tenant_key" \
  -d '{"address": "Flat 302, 3rd Floor, Near Durga Temple, Sector 62, Noida, 201301"}'
```

## 7. Setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                # edit as needed; empty API_KEYS = auth disabled for local dev

uvicorn main:app --reload --port 8000
```

Then open `frontend/index.html` directly in a browser (it calls
`http://localhost:8000` — no build step, no separate frontend server
needed), or visit `http://localhost:8000/docs` for the interactive API
explorer.

## 8. Testing

```bash
cd backend
pytest                    # full suite
pytest tests/test_api.py -v   # API-level tests only (needs fastapi/httpx installed)
pytest --cov=core         # with coverage, if pytest-cov is installed
```

Test files, one per module:

| File | Covers |
|---|---|
| `test_digipin_engine.py` | Encode/decode round-trip across multiple cities, boundary values, invalid input, cell size sanity |
| `test_nlp_parser.py` | Field extraction, warnings on missing floor/unit, garbage input handling |
| `test_normalization.py` | Bare house-number recovery, PIN extraction, dangling-comma cleanup, locality-hint detection |
| `test_quality.py` | Scoring thresholds, garbage-vs-sparse-address separation |
| `test_validation.py` | Pre-geocode rejection, ambiguity detection, low-relevance flagging |
| `test_risk.py` | Risk-level thresholds, reason transparency |
| `test_verification.py` | State transitions, "entrance is never inferred" rule, overall-status logic |
| `test_vertical_fusion.py` | Sanity coverage of the unchanged v1 module |
| `test_delivery_point.py` | End-to-end pipeline assembly, lift-confirmation threshold, ID uniqueness |
| `test_api.py` | All 5 HTTP endpoints, including 422 paths for ambiguous/garbage input, API-key auth |

**A note on how this was verified:** the sandbox this project was built in
had no network access, so `fastapi`/`pydantic`/`httpx`/`pytest` couldn't be
installed there. Because `core/` has zero framework dependency, all business
logic (`test_digipin_engine.py` through `test_delivery_point.py` — 49 test
functions) was verified by direct execution in that sandbox, and the full
pipeline was run end-to-end against all 8 required demo scenarios (complete
apartment, landmark-only, missing floor, missing flat, ambiguous, invalid,
campus, commercial) with correct behavior confirmed for each. `test_api.py`
was written and reasoned through carefully but requires `pip install -r
requirements.txt` to actually execute — run it yourself to confirm the HTTP
layer before deploying.

## 9. Security

- **API keys**: static `X-API-Key` header → tenant ID, configured via the
  `API_KEYS` env var (`tenant_id:key,tenant_id:key`). No keys configured =
  auth disabled with a startup warning logged — appropriate for local dev,
  never for anything reachable outside localhost.
- **No hardcoded secrets** anywhere in the codebase; `config.py` reads
  everything from environment variables with safe (never silently
  production-unsafe) defaults.
- **CORS**: wide open (`*`) by default for local development; set
  `CORS_ALLOW_ORIGINS` to your actual frontend origin(s) before deploying.
  A startup warning fires if it's left wide open.
- **Rate limiting**: a simple in-memory per-tenant sliding window
  (`RATE_LIMIT_RPM`, default 60/min). This is explicitly a *structural
  placeholder* — it resets on restart and doesn't coordinate across multiple
  server instances. Swap for Redis-backed limiting or an API-gateway policy
  before running more than one instance (see [§11](#11-production-roadmap)).
- **Logging**: structured JSON logs via `logging_config.py`. Raw address
  text is truncated by default (`LOG_FULL_ADDRESS_TEXT=false`) since full
  addresses are personal data — only enable full logging for local
  debugging.
- **No PII persistence**: nothing is written to disk or a database; every
  `DeliveryPoint` is built fresh per request and returned to the caller.

## 10. Limitations

1. **Nominatim rate limits.** The public endpoint is capped (~1 req/sec) and
   its usage policy prohibits heavy automated use. Self-host Nominatim or
   switch providers (Google/Mapbox/HERE/MapmyIndia) for production — the
   swap only touches `core/geocoding/`, per the provider abstraction.
2. **No persistence.** There's no `deliveries` table yet, so `access_notes`
   don't accumulate per-building across repeat deliveries — every `/resolve`
   call starts from zero. This was true of v1 too; still the documented next
   step, not built here per the "no unnecessary databases" instruction.
3. **Rate limiting is single-instance.** The in-memory limiter in
   `api/deps.py` doesn't coordinate across multiple server processes — fine
   for a single instance, not for horizontal scaling as-is.
4. **Floor/vertical detection is text-pattern based.** It won't catch every
   phrasing (regional-language mixing, "penthouse," non-numeric floor
   references). The `missing_fields`/`warnings` output is designed to
   surface exactly when this happens so the caller can prompt for manual
   confirmation — the floor rail in the UI supports this today.
5. **The demo/admin console frontend has no build step and no auth UI** —
   it's a thin client for exercising the API, not a production operations
   console. A real ops dashboard (multi-tenant login, delivery history,
   bulk resolution) is out of scope here.
6. **Ambiguity margin and risk-point thresholds are fixed constants**
   (`validation.py`, `risk.py`), tuned by inspection against the demo
   scenarios rather than production traffic. Expect to retune these once
   real resolution outcomes are available.

## 11. Production roadmap

Roughly in priority order:

1. **Swap Nominatim for a commercial geocoding provider** behind the
   existing `GeocodingProvider` interface, and add response caching to cut
   redundant lookups for repeat addresses.
2. **Add a `deliveries` table** (Postgres) keyed by DIGIPIN, so
   `access_notes` and verification state accumulate per-building across
   repeat deliveries instead of resetting every call.
3. **Move rate limiting to a shared store** (Redis) or push it to an API
   gateway, so it works correctly across multiple running instances.
4. **Replace the static API-key map with a proper key-management system**
   (issuance, rotation, per-tenant usage dashboards) once there are real
   paying tenants to manage.
5. **Structured request tracing** — attach a `request_id` through
   parse → geocode → resolve so a support engineer can pull the full trace
   for one customer complaint.
6. **Feedback loop**: let integrating platforms report actual delivery
   outcomes (success/RTO) back against a `delivery_point_id`, to eventually
   validate — or correct — the risk-scoring thresholds against real data
   instead of demo-scenario tuning.
7. **A real B2B admin console**: tenant login, delivery-point search history,
   bulk address upload/resolution, and an ops view for addresses stuck in
   `needs_confirmation`.

## 12. What changed from v1 (changelog)

| Area | v1 (`ai-digipin-smart-courier`) | v2 (this repo) |
|---|---|---|
| DIGIPIN engine | `backend/digipin_engine.py` | `backend/core/digipin_engine.py` — **byte-identical**, only relocated |
| NLP parser | `backend/nlp_parser.py` | `backend/core/nlp_parser.py` — **byte-identical**, only relocated |
| Instruction builder | `backend/vertical_fusion.py` | `backend/core/vertical_fusion.py` — **byte-identical**, only relocated |
| API routes | `/api/resolve`, `/api/decode`, `/api/parse` | Versioned `/api/v1/address/{parse,validate,resolve}`, `/api/v1/digipin/{code,decode}` |
| Confidence model | One blended `confidence` float | Separate `quality` (0–100), `validation.decision`, `risk.level`, `verification.state` |
| Ambiguity | Silently took Nominatim's top-1 result | Multi-candidate detection; returns `needs_confirmation` + candidates instead of guessing |
| Bare house numbers (e.g. `B-402`) | Dropped; left dangling `", ,"` artifacts in the cleaned address | Recovered by `normalization.py`; artifacts cleaned |
| Geocoding | Hardcoded Nominatim call in `main.py` | Provider-abstracted (`core/geocoding/`), Nominatim is one interchangeable implementation |
| Auth | None | API-key + tenant context (`api/deps.py`), off by default in dev with a startup warning |
| Rate limiting | None | In-memory per-tenant limiter (documented as a Redis-swap placeholder) |
| Logging | Default FastAPI/uvicorn logging | Structured JSON logs, address text redacted by default |
| Tests | None wired into pytest (manual `__main__` self-tests only) | Full `pytest` suite, 10 files, including HTTP-level API tests |
| Frontend | Single-purpose map demo | B2B admin console following the full pipeline stage-by-stage |

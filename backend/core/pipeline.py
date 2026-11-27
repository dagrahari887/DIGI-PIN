"""
pipeline.py
-----------
Orchestrates the full address -> DeliveryPoint pipeline described in
context.md's original data-flow diagram, extended with the quality /
validation / risk / verification stages:

    raw address
        -> nlp_parser.parse_address()
        -> normalization.normalize()
        -> quality.score_address()
        -> validation.validate_pre_geocode()   [may reject here]
        -> geocoding provider .geocode()
        -> validation.validate_geocode_candidates()  [may need_confirmation]
        -> digipin_engine.encode() / decode()
        -> risk.compute_risk()
        -> verification.build_verification_status()
        -> vertical_fusion.build_delivery_instructions()
        -> delivery_point.DeliveryPoint

This module has zero FastAPI/Pydantic dependency -- it only depends on
other core/ modules plus a `GeocodingProvider`-shaped object, so it can be
exercised directly in tests (including this file's own `__main__` demo)
without a running HTTP server.
"""

from dataclasses import dataclass
from typing import List, Optional

from .nlp_parser import parse_address
from .normalization import normalize, NormalizedAddress
from .quality import score_address
from .validation import validate_pre_geocode, validate_geocode_candidates, ValidationResult
from .digipin_engine import encode, decode, DigipinError
from .risk import compute_risk
from .verification import build_verification_status
from .vertical_fusion import build_delivery_instructions
from .delivery_point import DeliveryPoint, new_delivery_point_id
from .geocoding.base import GeocodingProvider, GeocodeError, GeocodeNoResults


@dataclass
class PipelineResult:
    normalized: NormalizedAddress
    quality: object
    validation: ValidationResult
    delivery_point: Optional[DeliveryPoint]
    geocode_error: Optional[str] = None


async def run_pipeline(
    raw_address: str,
    provider: GeocodingProvider,
    floor_level_override: Optional[str] = None,
    unit_no_override: Optional[str] = None,
    access_notes: Optional[str] = None,
    confirmed_fields: Optional[List[str]] = None,
    select_candidate_index: Optional[int] = None,
) -> PipelineResult:
    parsed = parse_address(raw_address)
    normalized = normalize(parsed)
    quality = score_address(normalized)

    pre_validation = validate_pre_geocode(normalized, quality)
    if pre_validation.decision == "reject":
        return PipelineResult(
            normalized=normalized, quality=quality, validation=pre_validation, delivery_point=None
        )

    query = normalized.locality_text.value or raw_address
    try:
        candidates = await provider.geocode(query, limit=5)
    except GeocodeNoResults as exc:
        validation = ValidationResult(decision="reject", issues=[str(exc)])
        return PipelineResult(normalized=normalized, quality=quality, validation=validation, delivery_point=None)
    except GeocodeError as exc:
        validation = ValidationResult(decision="reject", issues=[f"Geocoding failed: {exc}"])
        return PipelineResult(
            normalized=normalized, quality=quality, validation=validation,
            delivery_point=None, geocode_error=str(exc),
        )

    geo_validation = validate_geocode_candidates(candidates)

    if geo_validation.decision == "needs_confirmation" and select_candidate_index is None:
        return PipelineResult(
            normalized=normalized, quality=quality, validation=geo_validation, delivery_point=None
        )

    chosen_index = select_candidate_index if select_candidate_index is not None else 0
    if chosen_index >= len(candidates):
        chosen_index = 0
    chosen = candidates[chosen_index]

    # If the caller resolved an ambiguity by picking a candidate, downgrade
    # the decision to "proceed" for the final response -- the ambiguity has
    # now been explicitly settled by the caller, not guessed by us.
    final_validation = ValidationResult(
        decision="proceed",
        issues=geo_validation.issues if select_candidate_index is None else
               geo_validation.issues + ["Ambiguity resolved by explicit candidate selection."],
    )

    try:
        digipin_code = encode(chosen.latitude, chosen.longitude)
        box = decode(digipin_code)
    except DigipinError as exc:
        validation = ValidationResult(decision="reject", issues=[str(exc)])
        return PipelineResult(normalized=normalized, quality=quality, validation=validation, delivery_point=None)

    floor_level = floor_level_override or (normalized.floor_level.value if normalized.floor_level else None)
    unit_no = unit_no_override or (normalized.unit_no.value if normalized.unit_no else None)
    house_no = normalized.house_no.value if normalized.house_no else None
    landmark = normalized.landmark.value if normalized.landmark else None

    risk = compute_risk(
        quality_score=quality.score,
        validation_decision=final_validation.decision,
        validation_issues=final_validation.issues,
        has_unit_or_house=bool(unit_no or house_no),
        has_floor=bool(floor_level),
        has_landmark=bool(landmark),
        geocode_importance=chosen.importance,
    )

    verification = build_verification_status(
        has_location=True,
        has_building_signal=bool(landmark or house_no),
        has_floor=bool(floor_level),
        has_unit=bool(unit_no),
        confirmed_fields=confirmed_fields,
    )

    instructions = build_delivery_instructions(
        floor_level=floor_level,
        unit_no=unit_no,
        landmark=landmark,
        access_notes=access_notes,
    )

    requires_lift = bool(floor_level and str(floor_level).isdigit() and int(floor_level) >= 4)

    dp = DeliveryPoint(
        delivery_point_id=new_delivery_point_id(),
        digipin=digipin_code,
        latitude=round(box.center[0], 7),
        longitude=round(box.center[1], 7),
        bounding_box=box.as_dict(),
        house_no=house_no,
        unit_no=unit_no,
        floor_level=floor_level,
        building_hint=normalized.locality_text.value,
        landmark=landmark,
        access_notes=access_notes,
        quality=quality,
        validation=final_validation,
        risk=risk,
        verification=verification,
        delivery_instructions=instructions,
        requires_lift_confirmation=requires_lift,
    )

    return PipelineResult(normalized=normalized, quality=quality, validation=final_validation, delivery_point=dp)


if __name__ == "__main__":
    import asyncio
    import json
    from .geocoding.base import GeocodeCandidate

    class _FakeProvider:
        """Deterministic fake provider for offline demo/testing."""

        async def geocode(self, query: str, limit: int = 5):
            return [GeocodeCandidate(28.6139, 77.2090, 0.82, f"{query} (fake match)")]

    async def _demo():
        result = await run_pipeline(
            "Flat 302, 3rd Floor, Near Durga Temple, Sector 62, Noida, 201301",
            provider=_FakeProvider(),
            access_notes="Ring the bell twice",
        )
        print(json.dumps(result.delivery_point.to_dict(), indent=2))

    asyncio.run(_demo())

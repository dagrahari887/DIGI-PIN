"""
api/v1/address.py
------------------
POST /api/v1/address/parse     -- NLP + normalization + quality only, no geocoding
POST /api/v1/address/validate  -- parse + quality + full validation (incl. geocoding ambiguity check)
POST /api/v1/address/resolve   -- full pipeline: parse -> geocode -> DIGIPIN -> DeliveryPoint
"""

from fastapi import APIRouter, Depends, HTTPException, Request

from api.deps import TenantContext, enforce_rate_limit, get_tenant
from core.digipin_engine import DigipinError
from core.geocoding.nominatim import NominatimProvider
from core.nlp_parser import parse_address
from core.normalization import normalize
from core.pipeline import run_pipeline
from core.quality import score_address
from core.validation import validate_pre_geocode, validate_geocode_candidates, ValidationResult
from core.geocoding.base import GeocodeError, GeocodeNoResults
from logging_config import get_logger, redact_address
from schemas.address import (
    ParseRequest,
    ParseResponse,
    ResolveRequest,
    ResolveResponse,
    ValidateRequest,
    ValidateResponse,
)

router = APIRouter(prefix="/api/v1/address", tags=["address"])
logger = get_logger("api.v1.address")

_provider = NominatimProvider()  # module-level singleton; swap via config.settings.geocoding_provider


def _normalized_to_parsed_address_dict(raw_address: str, normalized, parsed_warnings):
    return {
        "raw_address": raw_address,
        "house_no": normalized.house_no.as_dict(),
        "unit_no": normalized.unit_no.as_dict(),
        "floor_level": normalized.floor_level.as_dict(),
        "landmark": normalized.landmark.as_dict(),
        "pincode": normalized.pincode.as_dict(),
        "locality_text": normalized.locality_text.as_dict(),
        "missing_fields": normalized.missing_fields,
        "warnings": parsed_warnings,
    }


@router.post("/parse", response_model=ParseResponse)
async def parse_only(
    payload: ParseRequest,
    tenant: TenantContext = Depends(get_tenant),
):
    """Debugging/inspection endpoint: run only the NLP + normalization +
    quality stages, without hitting the geocoder. Useful for tuning
    extraction without spending Nominatim rate-limit budget."""
    logger.info("parse request", extra={"extra_fields": {"tenant": tenant.tenant_id, "address": redact_address(payload.address)}})

    parsed = parse_address(payload.address)
    normalized = normalize(parsed)
    quality = score_address(normalized)

    return ParseResponse(
        parsed_address=_normalized_to_parsed_address_dict(payload.address, normalized, parsed.warnings),
        quality=quality.as_dict(),
    )


@router.post("/validate", response_model=ValidateResponse)
async def validate_only(
    payload: ValidateRequest,
    tenant: TenantContext = Depends(get_tenant),
):
    """Runs parsing + quality + full validation (including a geocoding
    ambiguity check) WITHOUT producing a DeliveryPoint or DIGIPIN. Lets a
    caller check "is this address good enough to resolve" before
    committing to the full pipeline."""
    logger.info("validate request", extra={"extra_fields": {"tenant": tenant.tenant_id, "address": redact_address(payload.address)}})

    parsed = parse_address(payload.address)
    normalized = normalize(parsed)
    quality = score_address(normalized)

    pre = validate_pre_geocode(normalized, quality)
    if pre.decision == "reject":
        return ValidateResponse(
            parsed_address=_normalized_to_parsed_address_dict(payload.address, normalized, parsed.warnings),
            quality=quality.as_dict(),
            validation=pre.as_dict(),
        )

    query = normalized.locality_text.value or payload.address
    try:
        candidates = await _provider.geocode(query, limit=5)
        validation = validate_geocode_candidates(candidates)
    except GeocodeNoResults as exc:
        validation = ValidationResult(decision="reject", issues=[str(exc)])
    except GeocodeError as exc:
        validation = ValidationResult(decision="reject", issues=[f"Geocoding failed: {exc}"])

    return ValidateResponse(
        parsed_address=_normalized_to_parsed_address_dict(payload.address, normalized, parsed.warnings),
        quality=quality.as_dict(),
        validation=validation.as_dict(),
    )


@router.post("/resolve", response_model=ResolveResponse)
async def resolve_address(
    payload: ResolveRequest,
    request: Request,
    tenant: TenantContext = Depends(get_tenant),
):
    """Full pipeline: parse -> normalize -> quality -> validate -> geocode
    -> DIGIPIN -> risk -> verification -> DeliveryPoint. This is the single
    call an integrating platform makes to turn a raw address into a
    courier-ready Delivery Point."""
    await enforce_rate_limit(request, tenant)
    logger.info("resolve request", extra={"extra_fields": {"tenant": tenant.tenant_id, "address": redact_address(payload.address)}})

    try:
        result = await run_pipeline(
            raw_address=payload.address,
            provider=_provider,
            floor_level_override=payload.floor_level_override,
            unit_no_override=payload.unit_no_override,
            access_notes=payload.access_notes,
            confirmed_fields=payload.confirmed_fields,
            select_candidate_index=payload.select_candidate_index,
        )
    except DigipinError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    parsed_address_dict = _normalized_to_parsed_address_dict(
        payload.address, result.normalized, []
    )

    if result.delivery_point is None:
        # validation stopped the pipeline: reject or needs_confirmation
        status_code = 422
        raise HTTPException(
            status_code=status_code,
            detail={
                "message": "Address could not be automatically resolved.",
                "parsed_address": parsed_address_dict,
                "quality": result.quality.as_dict(),
                "validation": result.validation.as_dict(),
            },
        )

    return ResolveResponse(
        parsed_address=parsed_address_dict,
        quality=result.quality.as_dict(),
        validation=result.validation.as_dict(),
        delivery_point=result.delivery_point.to_dict(),
    )

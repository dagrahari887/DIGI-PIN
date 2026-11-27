"""
Request/response schemas for POST /api/v1/address/{parse,validate,resolve}.
Pydantic v2 models -- kept entirely separate from core/ so the business
logic in core/ has zero framework dependency and can be unit-tested
without FastAPI or Pydantic installed.
"""

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from .common import QualityLabel, RiskLevel, ValidationDecision, VerificationState


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

class ParseRequest(BaseModel):
    address: str = Field(..., min_length=1, max_length=500, description="Raw, unstructured Indian address.")

    @field_validator("address")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("address must not be blank")
        return v


class ValidateRequest(ParseRequest):
    pass


class ResolveRequest(ParseRequest):
    floor_level_override: Optional[str] = Field(
        None, description="Floor level supplied by the caller (e.g. merchant/order system), overrides NLP extraction."
    )
    unit_no_override: Optional[str] = Field(
        None, description="Unit/flat number supplied by the caller, overrides NLP extraction."
    )
    access_notes: Optional[str] = Field(
        None, max_length=500, description="Free-text delivery notes, e.g. 'ring bell twice'."
    )
    confirmed_fields: List[str] = Field(
        default_factory=list,
        description="Subset of {address, location, building, entrance, floor, unit} the caller "
        "attests has been explicitly confirmed (by customer, merchant data, or courier) -- "
        "advances those components to VERIFIED. Never inferred automatically.",
    )
    select_candidate_index: Optional[int] = Field(
        None,
        ge=0,
        description="When a prior /resolve call returned needs_confirmation with multiple "
        "candidates, pass the chosen candidate's index here to resolve deterministically.",
    )


# ---------------------------------------------------------------------------
# Shared response fragments
# ---------------------------------------------------------------------------

class FieldValueSchema(BaseModel):
    value: Optional[str]
    confidence: float
    source: str


class ParsedAddressSchema(BaseModel):
    raw_address: str
    house_no: FieldValueSchema
    unit_no: FieldValueSchema
    floor_level: FieldValueSchema
    landmark: FieldValueSchema
    pincode: FieldValueSchema
    locality_text: FieldValueSchema
    missing_fields: List[str]
    warnings: List[str]


class QualitySchema(BaseModel):
    score: int
    label: QualityLabel
    reasons: List[str]


class GeocodeCandidateSchema(BaseModel):
    latitude: float
    longitude: float
    importance: float
    display_name: str


class ValidationSchema(BaseModel):
    decision: ValidationDecision
    issues: List[str]
    candidates: Optional[List[GeocodeCandidateSchema]] = None


class RiskSchema(BaseModel):
    level: RiskLevel
    points: int
    reasons: List[str]


class ComponentVerificationSchema(BaseModel):
    state: VerificationState
    source: Optional[str]


class VerificationSchema(BaseModel):
    components: dict  # component name -> ComponentVerificationSchema-shaped dict
    overall: VerificationState


class LocationSchema(BaseModel):
    digipin: str
    latitude: float
    longitude: float
    bounding_box: dict


class VerticalSchema(BaseModel):
    house_no: Optional[str]
    unit_no: Optional[str]
    floor_level: Optional[str]
    building_hint: Optional[str]
    requires_lift_confirmation: bool


class DeliveryPointSchema(BaseModel):
    delivery_point_id: str
    location: LocationSchema
    vertical: VerticalSchema
    landmark: Optional[str]
    access_notes: Optional[str]
    quality: QualitySchema
    validation: ValidationSchema
    risk: RiskSchema
    verification: VerificationSchema
    delivery_instructions: str


# ---------------------------------------------------------------------------
# Endpoint responses
# ---------------------------------------------------------------------------

class ParseResponse(BaseModel):
    parsed_address: ParsedAddressSchema
    quality: QualitySchema


class ValidateResponse(BaseModel):
    parsed_address: ParsedAddressSchema
    quality: QualitySchema
    validation: ValidationSchema


class ResolveResponse(BaseModel):
    parsed_address: ParsedAddressSchema
    quality: QualitySchema
    validation: ValidationSchema
    delivery_point: Optional[DeliveryPointSchema] = None


class ErrorResponse(BaseModel):
    error: str
    detail: str
    request_id: Optional[str] = None

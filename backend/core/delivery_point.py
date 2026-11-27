"""
delivery_point.py
------------------
The `DeliveryPoint` is the platform's first-class output object: a
DIGIPIN-anchored, confidence-scored, risk-scored, verification-tracked
record that any delivery/logistics platform can consume directly.

It deliberately keeps 2D and vertical data in clearly separate fields
(`location` vs `vertical`) rather than flattening everything into one
dict -- the spec is explicit that DIGIPIN/coordinates are a *2D* footprint
and floor/unit is *vertical* metadata layered on top, never something GPS
or DIGIPIN detects on its own.

No persistence layer: per the "no unnecessary databases" instruction,
this is an in-memory object constructed fresh per request and returned to
the caller. A `deliveries` table keyed by DIGIPIN (to accumulate
access_notes across repeat deliveries to the same building) remains a
documented next step in the README, not built here.
"""

import uuid
from dataclasses import dataclass, field
from typing import Optional

from .digipin_engine import BoundingBox
from .normalization import NormalizedAddress
from .quality import QualityResult
from .validation import ValidationResult
from .risk import RiskResult
from .verification import VerificationStatus


@dataclass
class DeliveryPoint:
    delivery_point_id: str
    digipin: str
    latitude: float
    longitude: float
    bounding_box: dict

    house_no: Optional[str]
    unit_no: Optional[str]
    floor_level: Optional[str]
    building_hint: Optional[str]  # locality text fragment, not a resolved building name
    landmark: Optional[str]
    access_notes: Optional[str]

    quality: QualityResult
    validation: ValidationResult
    risk: RiskResult
    verification: VerificationStatus

    delivery_instructions: str
    requires_lift_confirmation: bool

    def to_dict(self):
        return {
            "delivery_point_id": self.delivery_point_id,
            "location": {
                "digipin": self.digipin,
                "latitude": self.latitude,
                "longitude": self.longitude,
                "bounding_box": self.bounding_box,
            },
            "vertical": {
                "house_no": self.house_no,
                "unit_no": self.unit_no,
                "floor_level": self.floor_level,
                "building_hint": self.building_hint,
                "requires_lift_confirmation": self.requires_lift_confirmation,
            },
            "landmark": self.landmark,
            "access_notes": self.access_notes,
            "quality": self.quality.as_dict(),
            "validation": self.validation.as_dict(),
            "risk": self.risk.as_dict(),
            "verification": {
                "components": self.verification.as_dict(),
                "overall": self.verification.overall(),
            },
            "delivery_instructions": self.delivery_instructions,
        }


def new_delivery_point_id() -> str:
    return f"dp_{uuid.uuid4().hex[:16]}"

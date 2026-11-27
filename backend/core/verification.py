"""
verification.py
----------------
Tracks verification state independently for each of the six components
the product spec calls out: address, location, building, entrance, floor,
unit. States are UNVERIFIED / PARTIALLY_VERIFIED / VERIFIED.

Critical rule this module enforces: NLP extraction or geocoding success
is NEVER, by itself, treated as verification. A field parsed from raw
text is a *parse*, not a *confirmation* -- verification only advances when
an explicit confirming actor (customer, merchant/order system, or courier
on-ground) attests to it. This is what keeps the platform from claiming
"GPS/DIGIPIN automatically detects floors", which the spec explicitly
prohibits.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

UNVERIFIED = "UNVERIFIED"
PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
VERIFIED = "VERIFIED"

COMPONENTS = ["address", "location", "building", "entrance", "floor", "unit"]

# Actors whose confirmation is allowed to advance a component to VERIFIED.
CONFIRMING_SOURCES = {"customer_confirmed", "merchant_supplied", "courier_confirmed"}


@dataclass
class ComponentState:
    state: str = UNVERIFIED
    source: Optional[str] = None

    def as_dict(self):
        return {"state": self.state, "source": self.source}


@dataclass
class VerificationStatus:
    components: Dict[str, ComponentState] = field(default_factory=dict)

    def as_dict(self):
        return {k: v.as_dict() for k, v in self.components.items()}

    def overall(self) -> str:
        states = [c.state for c in self.components.values()]
        if all(s == VERIFIED for s in states):
            return VERIFIED
        if any(s in (VERIFIED, PARTIALLY_VERIFIED) for s in states):
            return PARTIALLY_VERIFIED
        return UNVERIFIED


def build_verification_status(
    has_location: bool,
    has_building_signal: bool,
    has_floor: bool,
    has_unit: bool,
    confirmed_fields: Optional[List[str]] = None,
) -> VerificationStatus:
    """
    Build initial verification state right after resolve. Everything
    starts UNVERIFIED (or PARTIALLY_VERIFIED if raw data merely *exists*
    but hasn't been confirmed by anyone) unless the caller explicitly
    lists a field in `confirmed_fields` -- e.g. because the customer
    confirmed it via an app prompt, or an order-management system
    supplied it directly.
    """
    confirmed_fields = set(confirmed_fields or [])
    status = VerificationStatus()

    def make(component: str, exists: bool) -> ComponentState:
        if component in confirmed_fields:
            return ComponentState(state=VERIFIED, source="customer_confirmed")
        if exists:
            # Data exists (was parsed/geocoded) but nobody has confirmed it.
            return ComponentState(state=PARTIALLY_VERIFIED, source="nlp_parsed")
        return ComponentState(state=UNVERIFIED, source=None)

    status.components["address"] = make("address", has_location or has_building_signal)
    status.components["location"] = make("location", has_location)
    status.components["building"] = make("building", has_building_signal)
    status.components["entrance"] = make("entrance", False)  # never inferred
    status.components["floor"] = make("floor", has_floor)
    status.components["unit"] = make("unit", has_unit)

    return status


if __name__ == "__main__":
    import json

    status = build_verification_status(
        has_location=True,
        has_building_signal=True,
        has_floor=True,
        has_unit=False,
        confirmed_fields=["floor"],
    )
    print(json.dumps(status.as_dict(), indent=2))
    print("Overall:", status.overall())
    assert status.components["floor"].state == VERIFIED
    assert status.components["unit"].state == UNVERIFIED
    assert status.components["entrance"].state == UNVERIFIED
    print("verification.py self-test OK")

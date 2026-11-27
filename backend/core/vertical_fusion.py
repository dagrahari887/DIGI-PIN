"""
vertical_fusion.py
-------------------
Solves the "vertical blindness" problem: a DIGIPIN bounding box locates a
building's 4m x 4m footprint on the ground, but says nothing about which
floor or unit a courier needs to reach once they're standing there.

This module fuses that 2D grid cell with vertical metadata (floor level,
unit number, and free-text access notes like "lift on the left, ring
bell twice") into a single navigation payload that a courier app can
consume directly.
"""

from dataclasses import dataclass, asdict
from typing import Optional

from .digipin_engine import BoundingBox, encode, decode

# Floors above this are flagged so the UI can suggest confirming lift
# access rather than assuming stairs are viable.
HIGH_FLOOR_THRESHOLD = 4


@dataclass
class NavigationPayload:
    digipin: str
    latitude: float
    longitude: float
    bounding_box: dict
    floor_level: Optional[str]
    unit_no: Optional[str]
    landmark: Optional[str]
    access_notes: Optional[str]
    delivery_instructions: str
    requires_lift_confirmation: bool

    def to_dict(self):
        return asdict(self)


def _describe_floor(floor_level: Optional[str]) -> str:
    if floor_level is None:
        return "ground level (unconfirmed)"
    if floor_level == "0":
        return "the ground floor"
    suffix = "th"
    if floor_level.isdigit():
        n = int(floor_level)
        if n % 10 == 1 and n != 11:
            suffix = "st"
        elif n % 10 == 2 and n != 12:
            suffix = "nd"
        elif n % 10 == 3 and n != 13:
            suffix = "rd"
    return f"the {floor_level}{suffix} floor"


def build_delivery_instructions(
    floor_level: Optional[str],
    unit_no: Optional[str],
    landmark: Optional[str],
    access_notes: Optional[str],
) -> str:
    """Compose a single human-readable instruction line for the courier."""
    parts = ["Navigate to the highlighted DIGIPIN cell."]

    if landmark:
        parts.append(f"The building is near {landmark}.")

    floor_phrase = _describe_floor(floor_level)
    if unit_no:
        parts.append(f"Go to unit {unit_no} on {floor_phrase}.")
    else:
        parts.append(f"Proceed to {floor_phrase}.")

    if floor_level and floor_level.isdigit() and int(floor_level) >= HIGH_FLOOR_THRESHOLD:
        parts.append("This is a high floor -- confirm lift availability before dispatch.")

    if access_notes:
        parts.append(access_notes.strip().rstrip(".") + ".")

    return " ".join(parts)


def fuse(
    digipin: str,
    box: BoundingBox,
    floor_level: Optional[str] = None,
    unit_no: Optional[str] = None,
    landmark: Optional[str] = None,
    access_notes: Optional[str] = None,
) -> NavigationPayload:
    """
    Combine a DIGIPIN grid cell with vertical/unit metadata into the
    final payload consumed by the map dashboard and, eventually, a
    courier-facing mobile app.
    """
    center_lat, center_lon = box.center

    requires_lift = bool(
        floor_level and floor_level.isdigit() and int(floor_level) >= HIGH_FLOOR_THRESHOLD
    )

    instructions = build_delivery_instructions(
        floor_level=floor_level,
        unit_no=unit_no,
        landmark=landmark,
        access_notes=access_notes,
    )

    return NavigationPayload(
        digipin=digipin,
        latitude=round(center_lat, 7),
        longitude=round(center_lon, 7),
        bounding_box=box.as_dict(),
        floor_level=floor_level,
        unit_no=unit_no,
        landmark=landmark,
        access_notes=access_notes,
        delivery_instructions=instructions,
        requires_lift_confirmation=requires_lift,
    )


if __name__ == "__main__":
    # Self-test entry point. Run as a module from backend/, e.g.:
    #   python3 -m core.vertical_fusion
    import json

    code = encode(28.6139, 77.2090)
    cell = decode(code)
    payload = fuse(
        digipin=code,
        box=cell,
        floor_level="7",
        unit_no="302",
        landmark="Durga Temple",
        access_notes="Ring the bell twice, dog on premises",
    )
    print(json.dumps(payload.to_dict(), indent=2))

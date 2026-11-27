"""
normalization.py
-----------------
Takes the raw output of `nlp_parser.parse_address()` and canonicalizes it
into a structured `NormalizedAddress`: one `FieldValue` per address
component, each carrying its own value, source, and a per-field confidence
score -- rather than a single blended confidence float for the whole
address.

This module does NOT change or wrap `nlp_parser.py` -- it consumes its
output and adds a second pass that:

1. Recovers a bare house/unit number the regex parser's keyword-anchored
   unit pattern misses, e.g. "B-402" or "A-12" with no "Flat"/"House"
   prefix word.
2. Extracts a 6-digit Indian PIN code, if present.
3. Cleans up dangling comma/whitespace artifacts left behind when the
   parser strips floor/landmark substrings out of the middle of a string
   (e.g. "B-402, , , Rajouri Garden, Delhi" -> "B-402, Rajouri Garden, Delhi").
4. Produces an explicit `missing_fields` list so downstream quality/risk
   scoring doesn't have to re-derive it from None checks scattered around.

Every field is tagged with a `source` so the platform can always answer
"where did this value come from" -- required for the vertical-fusion /
verification split (2D vs vertical data must never be conflated).
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from .nlp_parser import ParsedAddress

# ---------------------------------------------------------------------------
# Field provenance
# ---------------------------------------------------------------------------

SOURCE_NLP = "nlp_parsed"
SOURCE_CUSTOMER = "customer_confirmed"
SOURCE_MERCHANT = "merchant_supplied"
SOURCE_COURIER = "courier_confirmed"
SOURCE_OVERRIDE = "api_override"
SOURCE_NONE = "not_provided"

# A bare house/unit number pattern NOT anchored to a keyword, e.g.
# "B-402", "A-12", "12/4", "H.No. 45" already partially covered elsewhere.
# This deliberately requires a letter+digit or digit+slash+digit shape so it
# doesn't accidentally swallow PIN codes or floor numbers.
_BARE_UNIT_PATTERN = re.compile(
    r"\b([A-Za-z]{1,3}[-/]\d{1,4}[A-Za-z]?|\d{1,4}[-/][A-Za-z0-9]{1,4})\b"
)

_PINCODE_PATTERN = re.compile(r"\b(\d{6})\b")

# Light gazetteer of common Indian address-structure tokens, used only to
# decide whether leftover text looks like a plausible locality reference at
# all (see validation.py for how this feeds the "unparseable text" check).
LOCALITY_HINT_WORDS = {
    "nagar", "colony", "sector", "road", "marg", "chowk", "gali", "phase",
    "extension", "layout", "block", "society", "apartment", "apartments",
    "tower", "towers", "enclave", "vihar", "puram", "pur", "ganj", "bazar",
    "park", "garden", "gardens", "cross", "main", "lane", "street", "circle",
    "campus", "estate", "complex", "chs", "chowk", "township", "city",
}


@dataclass
class FieldValue:
    value: Optional[str] = None
    confidence: float = 0.0
    source: str = SOURCE_NONE

    def as_dict(self):
        return {"value": self.value, "confidence": round(self.confidence, 2), "source": self.source}

    def __bool__(self):
        return self.value is not None and self.value != ""


@dataclass
class NormalizedAddress:
    house_no: FieldValue = field(default_factory=FieldValue)
    unit_no: FieldValue = field(default_factory=FieldValue)
    floor_level: FieldValue = field(default_factory=FieldValue)
    landmark: FieldValue = field(default_factory=FieldValue)
    pincode: FieldValue = field(default_factory=FieldValue)
    locality_text: FieldValue = field(default_factory=FieldValue)
    access_notes: FieldValue = field(default_factory=FieldValue)
    missing_fields: list = field(default_factory=list)
    has_locality_hint: bool = False

    def as_dict(self):
        return {
            "house_no": self.house_no.as_dict(),
            "unit_no": self.unit_no.as_dict(),
            "floor_level": self.floor_level.as_dict(),
            "landmark": self.landmark.as_dict(),
            "pincode": self.pincode.as_dict(),
            "locality_text": self.locality_text.as_dict(),
            "access_notes": self.access_notes.as_dict(),
            "missing_fields": self.missing_fields,
            "has_locality_hint": self.has_locality_hint,
        }


def _recover_bare_house_no(raw_text: str, existing_unit: Optional[str]) -> Optional[str]:
    if existing_unit:
        return None  # nlp_parser already found a keyword-anchored unit; don't double-count
    match = _BARE_UNIT_PATTERN.search(raw_text)
    if match:
        return match.group(1).upper()
    return None


def _extract_pincode(text: str) -> Optional[str]:
    match = _PINCODE_PATTERN.search(text)
    return match.group(1) if match else None


def _tidy_locality_text(text: str) -> str:
    """Collapse dangling ', , ' artifacts and stray leading/trailing commas
    left over after nlp_parser strips matched substrings out of the middle
    of the address."""
    cleaned = re.sub(r"(,\s*){2,}", ", ", text)
    cleaned = re.sub(r"^\s*,\s*|\s*,\s*$", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


def _has_locality_hint(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in LOCALITY_HINT_WORDS)


def normalize(parsed: ParsedAddress) -> NormalizedAddress:
    """
    Build a NormalizedAddress from a ParsedAddress. Pure function, no I/O.
    """
    result = NormalizedAddress()

    # Unit / house number: prefer the NLP-extracted keyword-anchored value;
    # fall back to a bare-pattern recovery pass over the raw address.
    if parsed.unit_no:
        result.unit_no = FieldValue(value=parsed.unit_no, confidence=0.9, source=SOURCE_NLP)
    else:
        bare = _recover_bare_house_no(parsed.raw_address, parsed.unit_no)
        if bare:
            result.house_no = FieldValue(value=bare, confidence=0.55, source=SOURCE_NLP)

    if parsed.floor_level is not None:
        result.floor_level = FieldValue(value=parsed.floor_level, confidence=0.85, source=SOURCE_NLP)

    if parsed.landmark:
        result.landmark = FieldValue(value=parsed.landmark, confidence=0.7, source=SOURCE_NLP)

    pincode = _extract_pincode(parsed.raw_address)
    if pincode:
        result.pincode = FieldValue(value=pincode, confidence=0.95, source=SOURCE_NLP)

    tidied = _tidy_locality_text(parsed.cleaned_street_address)
    result.locality_text = FieldValue(
        value=tidied or None,
        confidence=0.6 if tidied else 0.0,
        source=SOURCE_NLP if tidied else SOURCE_NONE,
    )
    result.has_locality_hint = _has_locality_hint(tidied)

    missing = []
    if not result.unit_no and not result.house_no:
        missing.append("unit_or_house_no")
    if not result.floor_level:
        missing.append("floor_level")
    if not result.landmark:
        missing.append("landmark")
    if not result.pincode:
        missing.append("pincode")
    result.missing_fields = missing

    return result


if __name__ == "__main__":
    import json
    from .nlp_parser import parse_address

    samples = [
        "Flat 302, 3rd Floor, Near Durga Temple, Sector 62, Noida, 201301",
        "B-402, Ground Floor, Near Metro Station, Rajouri Garden, Delhi",
        "asdkfj laksjdf laksjdlfk",
    ]
    for s in samples:
        n = normalize(parse_address(s))
        print(s, "->")
        print(json.dumps(n.as_dict(), indent=2))
        print()

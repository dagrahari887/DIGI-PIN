"""
nlp_parser.py
-------------
Extracts structured entities from messy, human-written Indian addresses:

    "Flat 302, 3rd Floor, Near Durga Temple, Sector 62, Noida"
        -> floor_level: "3"
        -> unit_no: "302"
        -> landmark: "Durga Temple"
        -> cleaned_street_address: "Sector 62, Noida"

Approach: a regex-enhanced rule-based extractor. This is deliberately
dependency-light (no spaCy model download required) so it runs anywhere,
but it is structured so a spaCy NER pass could be dropped in later as an
additional signal (see `_spacy_landmark_boost`, which no-ops if spaCy /
a model isn't installed).

A confidence score is produced from how many of the four fields were
successfully extracted and how "clean" the remaining text looks.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Vocabulary tables used by the rule-based extractor
# ---------------------------------------------------------------------------

_FLOOR_WORDS = {
    "ground": "0", "g": "0",
    "first": "1", "second": "2", "third": "3", "fourth": "4",
    "fifth": "5", "sixth": "6", "seventh": "7", "eighth": "8",
    "ninth": "9", "tenth": "10",
}

# Matches things like "3rd Floor", "Floor 3", "Ground Floor", "2nd flr"
_FLOOR_PATTERNS = [
    re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s*floor\b", re.IGNORECASE),
    re.compile(r"\bfloor\s*[-:]?\s*(\d{1,2})\b", re.IGNORECASE),
    re.compile(
        r"\b(" + "|".join(_FLOOR_WORDS.keys()) + r")\s*floor\b", re.IGNORECASE
    ),
    re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s*flr\b", re.IGNORECASE),
]

# Matches "Flat 302", "Flat No. 302", "House No 12", "Apt 5B", "Unit 9"
_UNIT_PATTERNS = [
    re.compile(
        r"\b(?:flat|apartment|apt|house|unit|room)\s*(?:no\.?)?\s*[-:]?\s*"
        r"([a-zA-Z0-9]{1,6})\b",
        re.IGNORECASE,
    ),
]

# Matches "Near X", "Opposite X", "Behind X", "Beside X" up to the next comma
_LANDMARK_PATTERNS = [
    re.compile(
        r"\b(?:near|nr\.?|opp\.?|opposite|behind|beside|next to|adjacent to)\s+"
        r"([^,]+)",
        re.IGNORECASE,
    ),
]

_NOISE_TOKENS = re.compile(
    r"\s*,\s*|\s{2,}"
)


@dataclass
class ParsedAddress:
    raw_address: str
    floor_level: Optional[str] = None
    unit_no: Optional[str] = None
    landmark: Optional[str] = None
    cleaned_street_address: str = ""
    confidence: float = 0.0
    warnings: list = field(default_factory=list)

    def to_dict(self):
        return {
            "raw_address": self.raw_address,
            "floor_level": self.floor_level,
            "unit_no": self.unit_no,
            "landmark": self.landmark,
            "cleaned_street_address": self.cleaned_street_address,
            "confidence": round(self.confidence, 2),
            "warnings": self.warnings,
        }


def _extract_floor(text: str) -> Optional[str]:
    for pattern in _FLOOR_PATTERNS:
        match = pattern.search(text)
        if match:
            value = match.group(1).lower()
            return _FLOOR_WORDS.get(value, value)
    return None


def _extract_unit(text: str) -> Optional[str]:
    for pattern in _UNIT_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1).upper()
    return None


def _extract_landmark(text: str) -> Optional[str]:
    for pattern in _LANDMARK_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1).strip().rstrip(".")
    return None


def _spacy_landmark_boost(text: str, current_landmark: Optional[str]) -> Optional[str]:
    """
    Optional secondary pass: if spaCy and an English model are available,
    use named-entity recognition (ORG / FAC / LOC labels) to sanity-check
    or recover a landmark the regex pass missed. This function fails
    silently (returns the input unchanged) if spaCy isn't installed, so
    the parser has zero hard dependency on it.
    """
    if current_landmark:
        return current_landmark
    try:
        import spacy  # noqa: F401
    except ImportError:
        return current_landmark

    try:
        nlp = _spacy_landmark_boost._nlp_cache  # type: ignore[attr-defined]
    except AttributeError:
        try:
            import spacy
            nlp = spacy.load("en_core_web_sm")
        except Exception:
            nlp = None
        _spacy_landmark_boost._nlp_cache = nlp  # type: ignore[attr-defined]

    if nlp is None:
        return current_landmark

    doc = nlp(text)
    for ent in doc.ents:
        if ent.label_ in ("ORG", "FAC", "LOC"):
            return ent.text
    return current_landmark


def _strip_matched_spans(text: str, extracted_values: list) -> str:
    """Remove the substrings that were consumed by floor/unit/landmark
    extraction so what's left is the 'clean' locality/street portion."""
    cleaned = text
    for value in extracted_values:
        if not value:
            continue
        cleaned = re.sub(re.escape(value), "", cleaned, flags=re.IGNORECASE)

    # Remove leading connector words and floor/unit keywords left dangling
    cleaned = re.sub(
        r"\b(near|nr\.?|opp\.?|opposite|behind|beside|next to|adjacent to|"
        r"flat|apartment|apt|house|unit|room|no\.?|floor|flr)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    # Remove ordinal leftovers like "3rd" that had their floor number stripped
    cleaned = re.sub(r"\b\d{1,2}(?:st|nd|rd|th)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = _NOISE_TOKENS.sub(", ", cleaned).strip(" ,")
    return cleaned


def parse_address(raw_address: str) -> ParsedAddress:
    """
    Main entry point. Parses a raw, unstructured address string and
    returns a ParsedAddress with extracted entities and a confidence score.
    """
    text = raw_address.strip()
    result = ParsedAddress(raw_address=raw_address)

    if not text:
        result.warnings.append("Empty address string provided.")
        return result

    floor = _extract_floor(text)
    unit = _extract_unit(text)
    landmark = _extract_landmark(text)
    landmark = _spacy_landmark_boost(text, landmark)

    result.floor_level = floor
    result.unit_no = unit
    result.landmark = landmark

    # Build the raw substrings actually matched (not just the captured
    # group) so we can strip them cleanly from the remainder.
    consumed_spans = []
    for pattern in _FLOOR_PATTERNS + _UNIT_PATTERNS + _LANDMARK_PATTERNS:
        match = pattern.search(text)
        if match:
            consumed_spans.append(match.group(0))

    result.cleaned_street_address = _strip_matched_spans(text, consumed_spans)

    if not result.cleaned_street_address:
        result.cleaned_street_address = text
        result.warnings.append(
            "Could not confidently separate locality text; using full "
            "address for geocoding."
        )

    # --- Confidence scoring -------------------------------------------------
    # Start from how many of the three optional entities were found (each
    # worth up to ~0.2), plus a baseline for having *some* cleaned address
    # left over to geocode against (0.4).
    score = 0.4 if result.cleaned_street_address else 0.0
    score += 0.2 if floor else 0.0
    score += 0.2 if unit else 0.0
    score += 0.2 if landmark else 0.0

    if floor is None:
        result.warnings.append(
            "No floor level detected; vertical navigation will default to "
            "ground level unless the user selects one manually."
        )
    if unit is None:
        result.warnings.append("No flat/unit number detected.")

    result.confidence = min(score, 1.0)
    return result


if __name__ == "__main__":
    import json

    sample = "Flat 302, 3rd Floor, Near Durga Temple, Sector 62, Noida"
    parsed = parse_address(sample)
    print(json.dumps(parsed.to_dict(), indent=2))

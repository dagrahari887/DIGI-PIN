"""
quality.py
----------
Produces an address-quality score (0-100) with human-readable reasons,
based on which structured fields survived normalization. This is
deliberately separate from:

  - `confidence` (per-field, how sure the NLP/geocoder is about a value)
  - `risk`        (categorical, how likely the delivery is to fail --
                    computed in risk.py, and factors in geocoding + validation
                    outcomes that quality.py has no visibility into)

Quality only asks: "how much structured information do we have to work
with?" It does not know yet whether that information geocodes cleanly or
resolves to an ambiguous location -- that's `validation.py`'s job, which
runs after this.

Weights are fixed constants, not learned/fabricated -- this keeps the
score fully explainable, which matters for a B2B API where a customer
support team needs to be able to answer "why did this address score 45?"
"""

from dataclasses import dataclass, field

from .normalization import NormalizedAddress

# Field weights sum to 100. Locality text carries the most weight because
# without *something* geocodable, nothing downstream works at all.
_WEIGHTS = {
    "locality_text": 30,
    "pincode": 15,
    "landmark": 10,
    "house_or_unit": 25,
    "floor_level": 20,
}

COMPLETE_THRESHOLD = 80
INCOMPLETE_THRESHOLD = 45  # below this: "minimal"


@dataclass
class QualityResult:
    score: int
    label: str  # "complete" | "incomplete" | "minimal"
    reasons: list = field(default_factory=list)

    def as_dict(self):
        return {"score": self.score, "label": self.label, "reasons": self.reasons}


def score_address(normalized: NormalizedAddress) -> QualityResult:
    points = 0
    reasons = []

    if normalized.locality_text and normalized.has_locality_hint:
        points += _WEIGHTS["locality_text"]
    elif normalized.locality_text:
        # There's leftover text, but it doesn't look like a real locality
        # reference (no recognizable street/area/city-structure word) --
        # award partial credit only. This is what keeps garbage input like
        # "asdkfj laksjdf laksjdlfk" from scoring the same as a real but
        # sparse address.
        points += _WEIGHTS["locality_text"] // 3
        reasons.append(
            "Remaining address text doesn't contain a recognizable locality, "
            "street, or area reference."
        )
    else:
        reasons.append("No usable street/locality text after parsing.")

    if normalized.pincode:
        points += _WEIGHTS["pincode"]
    else:
        reasons.append("No 6-digit PIN code detected.")

    if normalized.landmark:
        points += _WEIGHTS["landmark"]
    else:
        reasons.append("No landmark detected.")

    if normalized.unit_no or normalized.house_no:
        points += _WEIGHTS["house_or_unit"]
    else:
        reasons.append("No flat/unit/house number detected.")

    if normalized.floor_level:
        points += _WEIGHTS["floor_level"]
    else:
        reasons.append("No floor level detected.")

    score = min(points, 100)

    if score >= COMPLETE_THRESHOLD:
        label = "complete"
    elif score >= INCOMPLETE_THRESHOLD:
        label = "incomplete"
    else:
        label = "minimal"

    if not reasons:
        reasons.append("All structured fields present.")

    return QualityResult(score=score, label=label, reasons=reasons)


if __name__ == "__main__":
    import json
    from .nlp_parser import parse_address
    from .normalization import normalize

    samples = [
        "Flat 302, 3rd Floor, Near Durga Temple, Sector 62, Noida, 201301",
        "Sector 62, Noida",
        "asdkfj laksjdf laksjdlfk",
    ]
    for s in samples:
        result = score_address(normalize(parse_address(s)))
        print(s, "->", json.dumps(result.as_dict(), indent=2))

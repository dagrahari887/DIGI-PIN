"""
risk.py
-------
Computes a categorical delivery-risk level: LOW / MEDIUM / HIGH / CRITICAL.

This is a transparent, rule-based point system -- not a model, and not a
fabricated percentage. Every point added is tied to a concrete, named
reason so a courier ops team can see exactly why an address was flagged,
which matters far more operationally than a black-box score would.

Risk is deliberately downstream of (and different from) quality and
validation: quality asks "how much data do we have", validation asks
"did geocoding resolve cleanly", and risk asks "how likely is this
delivery to go wrong" by combining both plus vertical-data completeness.
"""

from dataclasses import dataclass, field
from typing import List, Optional

LOW, MEDIUM, HIGH, CRITICAL = "LOW", "MEDIUM", "HIGH", "CRITICAL"


@dataclass
class RiskResult:
    level: str
    points: int
    reasons: list = field(default_factory=list)

    def as_dict(self):
        return {"level": self.level, "points": self.points, "reasons": self.reasons}


def _level_from_points(points: int) -> str:
    if points <= 1:
        return LOW
    if points <= 4:
        return MEDIUM
    if points <= 7:
        return HIGH
    return CRITICAL


def compute_risk(
    quality_score: int,
    validation_decision: str,
    validation_issues: List[str],
    has_unit_or_house: bool,
    has_floor: bool,
    has_landmark: bool,
    geocode_importance: Optional[float],
) -> RiskResult:
    points = 0
    reasons = []

    if validation_decision == "needs_confirmation":
        points += 3
        reasons.append("Location is ambiguous and unconfirmed.")
    elif validation_decision == "reject":
        points += 5
        reasons.append("Address text could not be geocoded at all.")

    if not has_unit_or_house:
        points += 2
        reasons.append("No flat/unit/house number identified.")

    if not has_floor:
        points += 1
        reasons.append("No floor level identified.")

    if not has_landmark:
        points += 1
        reasons.append("No landmark identified to aid on-ground navigation.")

    if geocode_importance is not None and geocode_importance < 0.3:
        points += 2
        reasons.append("Geocoding match relevance is low (broad/generic location).")

    if quality_score < 40:
        points += 2
        reasons.append("Overall address quality score is low.")

    level = _level_from_points(points)
    if not reasons:
        reasons.append("No risk factors identified.")

    return RiskResult(level=level, points=points, reasons=reasons)


if __name__ == "__main__":
    r = compute_risk(
        quality_score=30,
        validation_decision="needs_confirmation",
        validation_issues=["ambiguous"],
        has_unit_or_house=False,
        has_floor=False,
        has_landmark=False,
        geocode_importance=0.2,
    )
    print(r.as_dict())
    assert r.level in (HIGH, CRITICAL)

    r2 = compute_risk(
        quality_score=95,
        validation_decision="proceed",
        validation_issues=[],
        has_unit_or_house=True,
        has_floor=True,
        has_landmark=True,
        geocode_importance=0.8,
    )
    print(r2.as_dict())
    assert r2.level == LOW
    print("risk.py self-test OK")

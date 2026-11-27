"""
validation.py
--------------
Decides, given a NormalizedAddress + quality score + (optionally) a set of
geocoding candidates, whether the platform can proceed automatically or
must ask for human confirmation.

This directly implements requirement #3 from the product spec: "Never
silently choose an arbitrary ambiguous location." The old pipeline called
Nominatim with `limit: 1` and used whatever came back -- there was no way
for it to even detect ambiguity. Here, the caller passes in *multiple*
candidates (see core/geocoding), and this module decides whether they're
close enough in relevance to be genuinely ambiguous.

Three decisions are possible:
  - "proceed"            : safe to auto-resolve to the top candidate
  - "needs_confirmation"  : return candidates/questions instead of guessing
  - "reject"              : input too degraded to attempt geocoding at all
"""

from dataclasses import dataclass, field
from typing import List, Optional

from .normalization import NormalizedAddress
from .quality import QualityResult
from .geocoding.base import GeocodeCandidate

# If the top two geocoding candidates' importance scores are within this
# margin of each other, treat the match as ambiguous rather than picking #1.
AMBIGUITY_IMPORTANCE_MARGIN = 0.08

# Below this quality score, don't even attempt geocoding -- the text is too
# degraded to plausibly resolve to a real place.
MIN_QUALITY_TO_GEOCODE = 15

# Below this Nominatim importance, the single match found is treated as too
# weak/generic (e.g. it matched only a district or state) to trust alone.
LOW_IMPORTANCE_THRESHOLD = 0.25


@dataclass
class ValidationResult:
    decision: str  # "proceed" | "needs_confirmation" | "reject"
    issues: list = field(default_factory=list)
    candidates: Optional[List[dict]] = None

    def as_dict(self):
        d = {"decision": self.decision, "issues": self.issues}
        if self.candidates is not None:
            d["candidates"] = self.candidates
        return d


def validate_pre_geocode(normalized: NormalizedAddress, quality: QualityResult) -> ValidationResult:
    """
    Run before any geocoding call. Catches inputs not worth sending to a
    (rate-limited, paid-in-production) geocoding provider at all.
    """
    issues = []

    if not normalized.locality_text:
        issues.append("No address text remained after parsing.")
        return ValidationResult(decision="reject", issues=issues)

    if not normalized.has_locality_hint and quality.score < MIN_QUALITY_TO_GEOCODE:
        issues.append(
            "Address text does not contain a recognizable locality/street "
            "reference and overall quality is too low to geocode reliably."
        )
        return ValidationResult(decision="reject", issues=issues)

    if not normalized.has_locality_hint:
        issues.append(
            "Address text has no recognizable locality/street marker; "
            "geocoding result should be treated with caution."
        )

    return ValidationResult(decision="proceed", issues=issues)


def validate_geocode_candidates(candidates: List[GeocodeCandidate]) -> ValidationResult:
    """
    Run after a successful geocoding call. Decides whether the result set
    is a clean single match, an ambiguous cluster, or a weak single match.
    """
    issues = []

    if len(candidates) == 1:
        top = candidates[0]
        if top.importance < LOW_IMPORTANCE_THRESHOLD:
            issues.append(
                "Only match found is a broad/generic location (low relevance "
                "score); this may be a locality-level match rather than an "
                "exact address."
            )
        return ValidationResult(decision="proceed", issues=issues)

    top, second = candidates[0], candidates[1]
    if (top.importance - second.importance) < AMBIGUITY_IMPORTANCE_MARGIN:
        issues.append(
            f"{len(candidates)} candidate locations found with similar "
            "relevance; cannot auto-select without ambiguity."
        )
        return ValidationResult(
            decision="needs_confirmation",
            issues=issues,
            candidates=[c.as_dict() for c in candidates[:5]],
        )

    if top.importance < LOW_IMPORTANCE_THRESHOLD:
        issues.append(
            "Best match is a broad/generic location (low relevance score); "
            "this may be a locality-level match rather than an exact address."
        )

    return ValidationResult(decision="proceed", issues=issues)


if __name__ == "__main__":
    from .geocoding.base import GeocodeCandidate

    close_candidates = [
        GeocodeCandidate(28.61, 77.20, 0.42, "Sector 62, Noida, UP"),
        GeocodeCandidate(26.85, 80.94, 0.40, "Sector 62, Lucknow, UP"),
    ]
    result = validate_geocode_candidates(close_candidates)
    print(result.as_dict())
    assert result.decision == "needs_confirmation"

    clear_candidates = [
        GeocodeCandidate(28.61, 77.20, 0.85, "Durga Temple, Sector 62, Noida"),
        GeocodeCandidate(26.85, 80.94, 0.30, "Something else entirely"),
    ]
    result2 = validate_geocode_candidates(clear_candidates)
    print(result2.as_dict())
    assert result2.decision == "proceed"
    print("validation.py self-test OK")

from core.nlp_parser import parse_address
from core.normalization import normalize
from core.quality import score_address
from core.validation import validate_pre_geocode, validate_geocode_candidates
from core.geocoding.base import GeocodeCandidate


def test_pre_geocode_rejects_garbage():
    normalized = normalize(parse_address("asdkfj laksjdf laksjdlfk"))
    quality = score_address(normalized)
    result = validate_pre_geocode(normalized, quality)
    assert result.decision == "reject"


def test_pre_geocode_proceeds_for_real_address():
    normalized = normalize(parse_address("Sector 62, Noida"))
    quality = score_address(normalized)
    result = validate_pre_geocode(normalized, quality)
    assert result.decision == "proceed"


def test_ambiguous_candidates_need_confirmation():
    candidates = [
        GeocodeCandidate(28.61, 77.20, 0.42, "Sector 62, Noida, UP"),
        GeocodeCandidate(26.85, 80.94, 0.40, "Sector 62, Lucknow, UP"),
    ]
    result = validate_geocode_candidates(candidates)
    assert result.decision == "needs_confirmation"
    assert len(result.candidates) == 2


def test_clear_winner_proceeds_without_confirmation():
    candidates = [
        GeocodeCandidate(28.61, 77.20, 0.85, "Durga Temple, Sector 62, Noida"),
        GeocodeCandidate(26.85, 80.94, 0.30, "Something else"),
    ]
    result = validate_geocode_candidates(candidates)
    assert result.decision == "proceed"


def test_single_low_importance_match_flagged_but_proceeds():
    candidates = [GeocodeCandidate(28.61, 77.20, 0.15, "Uttar Pradesh")]
    result = validate_geocode_candidates(candidates)
    assert result.decision == "proceed"
    assert result.issues  # flagged as low-relevance, but not blocked

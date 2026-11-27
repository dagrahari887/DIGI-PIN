from core.nlp_parser import parse_address
from core.normalization import normalize
from core.quality import score_address


def _score(address: str):
    return score_address(normalize(parse_address(address)))


def test_complete_address_scores_high():
    r = _score("Flat 302, 3rd Floor, Near Durga Temple, Sector 62, Noida, 201301")
    assert r.score >= 80
    assert r.label == "complete"


def test_sparse_valid_address_scores_moderate_low():
    r = _score("Sector 62, Noida")
    assert 0 < r.score < 50
    assert r.label == "minimal"


def test_garbage_scores_lower_than_sparse_valid_address():
    garbage = _score("asdkfj laksjdf laksjdlfk")
    sparse = _score("Sector 62, Noida")
    assert garbage.score < sparse.score


def test_missing_fields_produce_reasons():
    r = _score("Sector 62, Noida")
    assert any("floor" in reason.lower() for reason in r.reasons)
    assert any("unit" in reason.lower() or "house" in reason.lower() for reason in r.reasons)

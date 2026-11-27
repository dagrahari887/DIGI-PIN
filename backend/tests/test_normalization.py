from core.nlp_parser import parse_address
from core.normalization import normalize


def test_recovers_bare_house_number_when_no_keyword_unit():
    n = normalize(parse_address("B-402, Ground Floor, Near Metro Station, Rajouri Garden, Delhi"))
    assert n.house_no.value == "B-402"
    assert n.unit_no.value is None  # keyword pattern still didn't match; that's expected


def test_does_not_double_count_when_keyword_unit_present():
    n = normalize(parse_address("Flat 302, 3rd Floor, Sector 62, Noida"))
    assert n.unit_no.value == "302"
    assert n.house_no.value is None


def test_extracts_pincode():
    n = normalize(parse_address("Sector 62, Noida, 201301"))
    assert n.pincode.value == "201301"


def test_no_pincode_present():
    n = normalize(parse_address("Sector 62, Noida"))
    assert n.pincode.value is None
    assert "pincode" in n.missing_fields


def test_dangling_comma_artifacts_are_cleaned():
    n = normalize(parse_address("B-402, Ground Floor, Near Metro Station, Rajouri Garden, Delhi"))
    assert ", ," not in n.locality_text.value
    assert not n.locality_text.value.startswith(",")


def test_garbage_text_has_no_locality_hint():
    n = normalize(parse_address("asdkfj laksjdf laksjdlfk"))
    assert n.has_locality_hint is False


def test_real_locality_text_has_hint():
    n = normalize(parse_address("Sector 62, Noida"))
    assert n.has_locality_hint is True

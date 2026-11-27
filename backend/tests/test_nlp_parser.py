from core.nlp_parser import parse_address


def test_full_address_extracts_all_fields():
    result = parse_address("Flat 302, 3rd Floor, Near Durga Temple, Sector 62, Noida")
    assert result.floor_level == "3"
    assert result.unit_no == "302"
    assert result.landmark == "Durga Temple"
    assert "Sector 62" in result.cleaned_street_address
    assert result.confidence == 1.0


def test_empty_address_returns_warning():
    result = parse_address("")
    assert result.warnings
    assert result.confidence == 0.0


def test_missing_floor_produces_warning():
    result = parse_address("Flat 302, Sector 62, Noida")
    assert result.floor_level is None
    assert any("floor" in w.lower() for w in result.warnings)


def test_missing_unit_produces_warning():
    result = parse_address("3rd Floor, Sector 62, Noida")
    assert result.unit_no is None
    assert any("flat/unit" in w.lower() for w in result.warnings)


def test_ground_floor_word_form():
    result = parse_address("Ground Floor, Rajouri Garden, Delhi")
    assert result.floor_level == "0"


def test_garbage_text_still_returns_a_result_not_a_crash():
    result = parse_address("asdkfj laksjdf laksjdlfk")
    assert result.floor_level is None
    assert result.unit_no is None
    assert result.landmark is None
    assert result.cleaned_street_address  # falls back to full text

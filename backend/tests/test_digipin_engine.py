import pytest

from core.digipin_engine import encode, decode, DigipinError, MIN_LAT, MAX_LAT, MIN_LON, MAX_LON


def test_encode_decode_round_trip_new_delhi():
    lat, lon = 28.6139, 77.2090
    code = encode(lat, lon)
    box = decode(code)
    assert box.min_lat <= lat <= box.max_lat
    assert box.min_lon <= lon <= box.max_lon


def test_encode_decode_round_trip_multiple_cities():
    cities = [
        (19.0760, 72.8777),  # Mumbai
        (12.9716, 77.5946),  # Bengaluru
        (22.5726, 88.3639),  # Kolkata
        (13.0827, 80.2707),  # Chennai
        (26.9124, 75.7873),  # Jaipur
    ]
    for lat, lon in cities:
        code = encode(lat, lon)
        box = decode(code)
        assert box.min_lat <= lat <= box.max_lat
        assert box.min_lon <= lon <= box.max_lon


def test_code_format():
    code = encode(28.6139, 77.2090)
    assert len(code) == 12  # 10 chars + 2 dashes
    assert code[3] == "-" and code[7] == "-"


def test_encode_out_of_bounds_latitude_raises():
    with pytest.raises(DigipinError):
        encode(MAX_LAT + 5, 77.0)
    with pytest.raises(DigipinError):
        encode(MIN_LAT - 5, 77.0)


def test_encode_out_of_bounds_longitude_raises():
    with pytest.raises(DigipinError):
        encode(28.0, MAX_LON + 5)
    with pytest.raises(DigipinError):
        encode(28.0, MIN_LON - 5)


def test_encode_at_exact_boundary_does_not_raise():
    # boundary values are inclusive
    encode(MIN_LAT, MIN_LON)
    encode(MAX_LAT, MAX_LON)


def test_decode_wrong_length_raises():
    with pytest.raises(DigipinError):
        decode("39J-438")


def test_decode_invalid_symbol_raises():
    with pytest.raises(DigipinError):
        decode("39J-438-TJQ0")  # '0' and 'Q' aren't in the DIGIPIN alphabet


def test_decode_accepts_undashed_and_lowercase():
    code = encode(28.6139, 77.2090)
    raw = code.replace("-", "").lower()
    box_from_raw = decode(raw)
    box_from_formatted = decode(code)
    assert box_from_raw.as_dict() == box_from_formatted.as_dict()


def test_cell_size_is_approximately_four_meters():
    code = encode(28.6139, 77.2090)
    box = decode(code)
    lat_span_m = (box.max_lat - box.min_lat) * 111_320
    assert 2.5 <= lat_span_m <= 5.0

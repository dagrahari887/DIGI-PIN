from core.digipin_engine import encode, decode
from core.vertical_fusion import fuse, build_delivery_instructions, HIGH_FLOOR_THRESHOLD


def test_fuse_produces_navigation_payload():
    code = encode(28.6139, 77.2090)
    box = decode(code)
    payload = fuse(digipin=code, box=box, floor_level="3", unit_no="302", landmark="Durga Temple")
    assert payload.digipin == code
    assert "3rd floor" in payload.delivery_instructions
    assert payload.requires_lift_confirmation is False


def test_high_floor_flags_lift_confirmation():
    code = encode(28.6139, 77.2090)
    box = decode(code)
    payload = fuse(digipin=code, box=box, floor_level=str(HIGH_FLOOR_THRESHOLD))
    assert payload.requires_lift_confirmation is True
    assert "lift" in payload.delivery_instructions.lower()


def test_instructions_include_access_notes():
    text = build_delivery_instructions(floor_level="2", unit_no="10", landmark=None, access_notes="Ring twice")
    assert "Ring twice" in text

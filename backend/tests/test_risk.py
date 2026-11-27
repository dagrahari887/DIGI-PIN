from core.risk import compute_risk, LOW, MEDIUM, HIGH, CRITICAL


def test_ideal_address_is_low_risk():
    r = compute_risk(
        quality_score=95, validation_decision="proceed", validation_issues=[],
        has_unit_or_house=True, has_floor=True, has_landmark=True, geocode_importance=0.8,
    )
    assert r.level == LOW


def test_missing_vertical_data_raises_risk():
    r_full = compute_risk(
        quality_score=90, validation_decision="proceed", validation_issues=[],
        has_unit_or_house=True, has_floor=True, has_landmark=True, geocode_importance=0.8,
    )
    r_missing_floor = compute_risk(
        quality_score=90, validation_decision="proceed", validation_issues=[],
        has_unit_or_house=True, has_floor=False, has_landmark=True, geocode_importance=0.8,
    )
    assert r_missing_floor.points > r_full.points


def test_ambiguous_and_sparse_address_is_high_or_critical():
    r = compute_risk(
        quality_score=25, validation_decision="needs_confirmation", validation_issues=["ambiguous"],
        has_unit_or_house=False, has_floor=False, has_landmark=False, geocode_importance=0.2,
    )
    assert r.level in (HIGH, CRITICAL)


def test_every_risk_reason_is_concrete_not_generic():
    r = compute_risk(
        quality_score=20, validation_decision="reject", validation_issues=["bad"],
        has_unit_or_house=False, has_floor=False, has_landmark=False, geocode_importance=None,
    )
    assert all(isinstance(reason, str) and len(reason) > 5 for reason in r.reasons)

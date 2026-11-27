from core.verification import build_verification_status, UNVERIFIED, PARTIALLY_VERIFIED, VERIFIED


def test_parsed_but_unconfirmed_fields_are_partially_verified():
    status = build_verification_status(
        has_location=True, has_building_signal=True, has_floor=True, has_unit=True,
    )
    assert status.components["floor"].state == PARTIALLY_VERIFIED
    assert status.components["unit"].state == PARTIALLY_VERIFIED


def test_explicit_confirmation_advances_to_verified():
    status = build_verification_status(
        has_location=True, has_building_signal=True, has_floor=True, has_unit=False,
        confirmed_fields=["floor"],
    )
    assert status.components["floor"].state == VERIFIED
    assert status.components["floor"].source == "customer_confirmed"


def test_entrance_is_never_inferred():
    status = build_verification_status(
        has_location=True, has_building_signal=True, has_floor=True, has_unit=True,
    )
    assert status.components["entrance"].state == UNVERIFIED


def test_missing_field_stays_unverified():
    status = build_verification_status(
        has_location=True, has_building_signal=False, has_floor=False, has_unit=False,
    )
    assert status.components["unit"].state == UNVERIFIED
    assert status.components["floor"].state == UNVERIFIED


def test_overall_status_reflects_worst_component():
    status = build_verification_status(
        has_location=True, has_building_signal=True, has_floor=True, has_unit=False,
        confirmed_fields=["floor", "location", "building", "address"],
    )
    # unit and entrance are still unverified -> overall can't be VERIFIED
    assert status.overall() == PARTIALLY_VERIFIED


def test_overall_verified_only_when_everything_confirmed():
    status = build_verification_status(
        has_location=True, has_building_signal=True, has_floor=True, has_unit=True,
        confirmed_fields=["address", "location", "building", "entrance", "floor", "unit"],
    )
    assert status.overall() == VERIFIED

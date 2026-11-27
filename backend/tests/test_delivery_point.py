import asyncio

from core.pipeline import run_pipeline
from core.geocoding.base import GeocodeCandidate


class _FakeProvider:
    async def geocode(self, query, limit=5):
        return [GeocodeCandidate(28.6139, 77.2090, 0.8, f"{query} (fake)")]


def test_delivery_point_has_separated_2d_and_vertical_data():
    result = asyncio.run(
        run_pipeline("Flat 302, 3rd Floor, Near Durga Temple, Sector 62, Noida, 201301", provider=_FakeProvider())
    )
    dp = result.delivery_point.to_dict()
    assert "location" in dp and "vertical" in dp
    assert "digipin" in dp["location"]
    assert dp["vertical"]["floor_level"] == "3"
    assert dp["vertical"]["unit_no"] == "302"


def test_high_floor_requires_lift_confirmation():
    result = asyncio.run(
        run_pipeline(
            "Flat 302, 7th Floor, Near Durga Temple, Sector 62, Noida, 201301",
            provider=_FakeProvider(),
        )
    )
    dp = result.delivery_point.to_dict()
    assert dp["vertical"]["requires_lift_confirmation"] is True


def test_low_floor_does_not_require_lift_confirmation():
    result = asyncio.run(
        run_pipeline(
            "Flat 302, 1st Floor, Near Durga Temple, Sector 62, Noida, 201301",
            provider=_FakeProvider(),
        )
    )
    dp = result.delivery_point.to_dict()
    assert dp["vertical"]["requires_lift_confirmation"] is False


def test_delivery_point_has_unique_ids_across_calls():
    r1 = asyncio.run(run_pipeline("Sector 62, Noida, 201301", provider=_FakeProvider()))
    r2 = asyncio.run(run_pipeline("Sector 62, Noida, 201301", provider=_FakeProvider()))
    assert r1.delivery_point.delivery_point_id != r2.delivery_point.delivery_point_id

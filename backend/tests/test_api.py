"""
test_api.py
-----------
Exercises the actual HTTP endpoints via FastAPI's TestClient. The
geocoding provider is monkeypatched to a deterministic fake so these
tests never make a real network call and never hit Nominatim's rate
limit -- run with `pytest tests/test_api.py`.

NOTE: requires `fastapi`, `httpx`, and `pydantic` to be installed
(`pip install -r requirements.txt`). This sandbox had no network access
to install them, so this file's logic was written and reasoned through
carefully but not executed live -- run it yourself with
`pytest tests/test_api.py -v` after installing requirements to confirm.
"""

import pytest
from fastapi.testclient import TestClient

import api.v1.address as address_module
from core.geocoding.base import GeocodeCandidate, GeocodeNoResults
from main import app

client = TestClient(app)


class _FakeProvider:
    """Deterministic fake geocoder so tests don't hit the network."""

    def __init__(self, mode="normal"):
        self.mode = mode

    async def geocode(self, query, limit=5):
        if self.mode == "noresult":
            raise GeocodeNoResults(f"No match for '{query}'.")
        if self.mode == "ambiguous":
            return [
                GeocodeCandidate(28.61, 77.20, 0.42, f"{query} (Noida)"),
                GeocodeCandidate(26.85, 80.94, 0.40, f"{query} (Lucknow)"),
            ]
        return [GeocodeCandidate(28.6139, 77.2090, 0.8, f"{query} (match)")]


@pytest.fixture(autouse=True)
def _patch_provider(monkeypatch):
    monkeypatch.setattr(address_module, "_provider", _FakeProvider())
    yield


def test_health_endpoint():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_parse_endpoint_no_network_needed():
    resp = client.post(
        "/api/v1/address/parse",
        json={"address": "Flat 302, 3rd Floor, Near Durga Temple, Sector 62, Noida"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["parsed_address"]["unit_no"]["value"] == "302"
    assert body["parsed_address"]["floor_level"]["value"] == "3"
    assert body["quality"]["score"] > 0


def test_resolve_endpoint_happy_path():
    resp = client.post(
        "/api/v1/address/resolve",
        json={"address": "Flat 302, 3rd Floor, Near Durga Temple, Sector 62, Noida, 201301"},
    )
    assert resp.status_code == 200
    body = resp.json()
    dp = body["delivery_point"]
    assert dp is not None
    assert len(dp["location"]["digipin"].replace("-", "")) == 10
    assert dp["risk"]["level"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")


def test_resolve_endpoint_ambiguous_returns_422_with_candidates(monkeypatch):
    monkeypatch.setattr(address_module, "_provider", _FakeProvider(mode="ambiguous"))
    resp = client.post("/api/v1/address/resolve", json={"address": "Sector 62"})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["validation"]["decision"] == "needs_confirmation"
    assert len(detail["validation"]["candidates"]) == 2


def test_resolve_endpoint_no_geocode_match_returns_422(monkeypatch):
    monkeypatch.setattr(address_module, "_provider", _FakeProvider(mode="noresult"))
    resp = client.post(
        "/api/v1/address/resolve",
        json={"address": "Sector 62, Noida, 201301"},
    )
    assert resp.status_code == 422


def test_resolve_endpoint_rejects_garbage_before_geocoding():
    resp = client.post("/api/v1/address/resolve", json={"address": "asdkfj laksjdf laksjdlfk"})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["validation"]["decision"] == "reject"


def test_resolve_with_ambiguity_resolved_via_candidate_selection(monkeypatch):
    monkeypatch.setattr(address_module, "_provider", _FakeProvider(mode="ambiguous"))
    resp = client.post(
        "/api/v1/address/resolve",
        json={"address": "Sector 62", "select_candidate_index": 0},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["delivery_point"] is not None
    assert "Ambiguity resolved by explicit candidate selection." in body["validation"]["issues"]


def test_resolve_blank_address_returns_422_validation_error():
    resp = client.post("/api/v1/address/resolve", json={"address": "   "})
    assert resp.status_code == 422


def test_digipin_decode_round_trip():
    resolve_resp = client.post(
        "/api/v1/address/resolve",
        json={"address": "Flat 302, 3rd Floor, Sector 62, Noida, 201301"},
    )
    digipin = resolve_resp.json()["delivery_point"]["location"]["digipin"]

    decode_resp = client.get(f"/api/v1/digipin/{digipin}")
    assert decode_resp.status_code == 200
    body = decode_resp.json()
    assert body["digipin"] == digipin
    assert "min_lat" in body["bounding_box"]


def test_digipin_decode_invalid_code_returns_422():
    resp = client.get("/api/v1/digipin/INVALID000")
    assert resp.status_code == 422


def test_high_floor_flags_lift_confirmation_via_api():
    resp = client.post(
        "/api/v1/address/resolve",
        json={"address": "Flat 302, 7th Floor, Sector 62, Noida, 201301"},
    )
    assert resp.status_code == 200
    assert resp.json()["delivery_point"]["vertical"]["requires_lift_confirmation"] is True


def test_confirmed_fields_advance_verification_state():
    resp = client.post(
        "/api/v1/address/resolve",
        json={
            "address": "Flat 302, 3rd Floor, Sector 62, Noida, 201301",
            "confirmed_fields": ["floor", "unit"],
        },
    )
    assert resp.status_code == 200
    components = resp.json()["delivery_point"]["verification"]["components"]
    assert components["floor"]["state"] == "VERIFIED"
    assert components["unit"]["state"] == "VERIFIED"


def test_api_key_required_when_configured(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "api_keys_raw", "acme:secret123")
    resp = client.post("/api/v1/address/parse", json={"address": "Sector 62, Noida"})
    assert resp.status_code == 401

    resp2 = client.post(
        "/api/v1/address/parse",
        json={"address": "Sector 62, Noida"},
        headers={"X-API-Key": "secret123"},
    )
    assert resp2.status_code == 200

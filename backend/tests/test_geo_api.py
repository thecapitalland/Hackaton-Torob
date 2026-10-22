"""Update #1 tests: Neshan client + geo fallback endpoints + cafe chain."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# --------------------------------------------------------------------------
# unit: neshan client (offline - no key)
# --------------------------------------------------------------------------


def test_neshan_without_key_returns_none(monkeypatch):
    from app.services import neshan

    monkeypatch.delenv("NESHAN_API_KEY", raising=False)
    monkeypatch.delenv("NESHAN_KEY", raising=False)
    assert neshan.reverse_geocode(35.7, 51.4) is None
    assert neshan.direction(35.7, 51.4, 35.69, 51.41) is None
    assert neshan.nearby_cafes(35.7, 51.4) is None
    # and it must not have attempted any request (no cache entries)
    assert not neshan._cache


def test_neshan_disabled_after_invalid_key(monkeypatch):
    from app.services import neshan

    monkeypatch.setenv("NESHAN_API_KEY", "bad-key")
    neshan._clear_cache()
    neshan._invalid_key_until = 0.0

    def fake_get(path, params=None, headers=None, timeout=None):
        class R:
            status_code = neshan.INVALID_KEY_HTTP

            def json(self):
                return {}

        return R()

    original = neshan._client.get
    neshan._client.get = fake_get
    try:
        assert neshan.reverse_geocode(35.7, 51.4) is None
        assert not neshan._is_available()  # marked unavailable for a while
    finally:
        neshan._client.get = original
        neshan._invalid_key_until = 0.0


def test_decode_polyline():
    # the canonical example from the Google polyline encoding docs
    from app.services.neshan import decode_polyline

    assert decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@") == [
        [38.5, -120.2],
        [40.7, -120.95],
        [43.252, -126.453],
    ]


# --------------------------------------------------------------------------
# API endpoints
# --------------------------------------------------------------------------


@pytest.fixture()
def api_client(monkeypatch):
    monkeypatch.delenv("NESHAN_API_KEY", raising=False)
    monkeypatch.delenv("NESHAN_KEY", raising=False)
    from fastapi.testclient import TestClient

    from app import main as main_app

    with TestClient(main_app.app) as client:
        yield client


def test_health_alias(api_client):
    response = api_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["catalog_rows"]["shops"] > 0


def test_geo_reverse_fallback_nearest_neighbourhood(api_client):
    # Ferdowsi square coordinates -> the «فردوسی» centroid is the closest one
    response = api_client.get("/api/geo/reverse", params={"lat": 35.701, "lon": 51.4187})
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "fallback"
    assert body["neighbourhood"] in {"فردوسی", "میدان فردوسی"}
    assert "تخمینی" in body["formatted_address"]


def test_geo_routes_estimate_fallback(api_client):
    response = api_client.post(
        "/api/geo/routes",
        json={
            "origin": {"lat": 35.701, "lon": 51.4187},
            "destinations": [{"lat": 35.695, "lon": 51.412}, {"lat": 35.804, "lon": 51.433}],
        },
    )
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 2
    for route in results:
        assert route["estimated"] is True
        assert route["source"] == "estimate"
        assert route["distance_m"] > 0
        assert route["duration_min"] >= 1
        assert route["polyline"] is None


def test_geo_routes_caps_at_ten(api_client):
    destinations = [{"lat": 35.7 + i / 1000.0, "lon": 51.4 + i / 1000.0} for i in range(15)]
    response = api_client.post(
        "/api/geo/routes",
        json={"origin": {"lat": 35.701, "lon": 51.4187}, "destinations": destinations},
    )
    assert response.status_code == 200
    assert len(response.json()["results"]) == 10


# --------------------------------------------------------------------------
# cafe chain: local fallback always works and is labelled
# --------------------------------------------------------------------------


def test_cafes_local_fallback(api_client, monkeypatch):
    from app.tools import cafes

    monkeypatch.setattr(cafes.neshan, "nearby_cafes", lambda *a, **kw: None)
    monkeypatch.setattr(cafes.overpass, "cafes_near", lambda *a, **kw: None)
    payload = cafes.nearby(35.6952, 51.4125)
    assert payload["source"] == "local"
    assert payload["cafes"], "static cafe list must never be empty"
    assert payload["cafes"][0]["label"] == cafes.LOCAL_LABEL
    assert payload["cafes"][0]["mock"] is True


def test_cafes_chain_prefers_neshan(monkeypatch):
    from app.tools import cafes

    def fake_neshan(lat, lon, radius_m=500):
        return [{"name": "کافه نشان", "lat": lat, "lon": lon, "source": "neshan"}]

    def fail_overpass(*args, **kwargs):
        raise AssertionError("Overpass must not be reached while Neshan answers")

    monkeypatch.setattr(cafes.neshan, "nearby_cafes", fake_neshan)
    monkeypatch.setattr(cafes.overpass, "cafes_near", fail_overpass)
    payload = cafes.nearby(35.69, 51.41)
    assert payload["source"] == "neshan"
    assert payload["cafes"][0]["label"] == cafes.NESHAN_LABEL


def test_cafes_endpoint_contract(api_client, monkeypatch):
    monkeypatch.setenv("NESHAN_API_KEY", "")  # no key
    response = api_client.get("/api/cafes/nearby", params={"lat": 35.6952, "lon": 51.4125})
    assert response.status_code == 200
    body = response.json()
    assert body["source"] in {"neshan", "osm", "local"}
    for cafe in body["cafes"]:
        assert cafe["name"]
        assert "lat" in cafe and "lon" in cafe

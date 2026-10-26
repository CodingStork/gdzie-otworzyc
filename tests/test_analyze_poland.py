import h3
import pytest

from backend.app.analysis import service
from backend.app.db import reset_connection
from tests.conftest import CENTER, disk

WARSAW, KRAKOW, GDANSK = CENTER, (50.06, 19.94), (54.35, 18.65)


@pytest.fixture
def poland_client(make_client):
    pop = {}
    for city in (WARSAW, KRAKOW, GDANSK):
        pop.update({c: 1000.0 for c in disk(city, k=4)})
    pois = [("grocery", *WARSAW), ("grocery", *KRAKOW)]
    return make_client(pop=pop, pois=pois)


def _cities_hit(hexes):
    """Które z trzech miast mają heksagony w wyniku (heksagon res 6 blisko miasta)."""
    hit = set()
    for row in hexes:
        lat, lng = h3.cell_to_latlng(row[0])
        for name, (clat, clng) in (("W", WARSAW), ("K", KRAKOW), ("G", GDANSK)):
            if abs(lat - clat) < 0.2 and abs(lng - clng) < 0.3:
                hit.add(name)
    return hit


def test_poland_scope_uses_res6_and_covers_distant_places(poland_client):
    j = poland_client.get("/api/analyze", params=dict(type="grocery", demand="pop_total", scope="poland")).json()
    assert j["res"] == 6
    assert _cities_hit(j["hexes"]) == {"W", "K", "G"}
    assert 1 <= len(j["top"]) <= 5
    # separacja top-5: co najmniej 20 km
    tops = j["top"]
    for i, a in enumerate(tops):
        for b in tops[i + 1:]:
            assert abs(a["lat"] - b["lat"]) + abs(a["lng"] - b["lng"]) > 0.15


def test_poland_scope_ignores_lat_lng_outside_poland(poland_client):
    r = poland_client.get("/api/analyze", params=dict(type="grocery", demand="pop_total", scope="poland", lat=10, lng=10))
    assert r.status_code == 200 and r.json()["res"] == 6


def test_poland_scope_with_permits_demand(make_client):
    pop = {c: 1000.0 for c in disk(WARSAW, k=3)}
    client = make_client(pop=pop, permits=[(*WARSAW, "2026-09-01", "sf", 6)])
    j = client.get("/api/analyze", params=dict(type="paving", demand="new_sf", scope="poland")).json()
    assert j["res"] == 6 and sum(r[4] for r in j["hexes"]) == pytest.approx(6)
    assert j["permits_period"]["to"] == "2026-09"


@pytest.fixture
def counted(monkeypatch):
    calls = []
    original = service.run_analysis

    def wrapper(con, p):
        calls.append(p)
        return original(con, p)

    monkeypatch.setattr(service, "run_analysis", wrapper)
    return calls


def test_second_identical_call_hits_cache(poland_client, counted):
    params = dict(type="grocery", demand="pop_total", scope="poland")
    first = poland_client.get("/api/analyze", params=params).json()
    second = poland_client.get("/api/analyze", params=params).json()
    assert first == second and len(counted) == 1


def test_cache_key_rounds_parameters(api_client, counted):
    base = dict(type="beauty", demand="pop_f", lat=52.23, lng=21.01, radius_km=3)
    api_client.get("/api/analyze", params=base)
    api_client.get("/api/analyze", params=dict(base, lat=52.2301, lng=21.0102))          # ta sama kratka ~100 m
    assert len(counted) == 1
    api_client.get("/api/analyze", params=dict(base, radius_km=4))                        # inny promień
    api_client.get("/api/analyze", params=dict(base, type="cafe"))                        # inny typ
    assert len(counted) == 3


def test_reset_connection_clears_cache(api_client, counted):
    params = dict(type="beauty", demand="pop_f", lat=52.23, lng=21.01, radius_km=3)
    api_client.get("/api/analyze", params=params)
    reset_connection()
    api_client.get("/api/analyze", params=params)
    assert len(counted) == 2


def test_errors_are_not_cached(tmp_path, monkeypatch, counted):
    from fastapi.testclient import TestClient
    from backend.app import config
    from backend.app.main import app
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "nie_ma.duckdb")
    reset_connection()
    client = TestClient(app)
    params = dict(type="beauty", demand="pop_f", lat=52.23, lng=21.01, radius_km=3)
    assert client.get("/api/analyze", params=params).status_code == 503
    assert client.get("/api/analyze", params=params).status_code == 503

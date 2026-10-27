"""Testy GET /api/surface: mapa okolicy wybranego miejsca (warstwy, siatka, top-5, brzegi danych)."""
import time

import pytest

from tests.conftest import CENTER, disk

LAT, LNG = CENTER


def _pop(k=12, value=1000.0):
    return {c: value for c in disk(k=k)}


# fryzjer przy środku i jeden daleko na północnym zachodzie (≈ 2,2 km)
POIS = [("hairdresser", LAT, LNG), ("hairdresser", LAT + 0.02, LNG - 0.03), ("cafe", LAT, LNG + 0.005)]


@pytest.fixture
def client(make_client):
    return make_client(pop=_pop(), pois=POIS,
                       permits=[(LAT, LNG, "2026-09-01", "sf", 5), (LAT + 0.01, LNG, "2026-08-01", "sf", 3)])


def surface(client, **kw):
    params = dict(type="hairdresser", demand="pop_total", lat=LAT, lng=LNG, radius_km=3, reach_km=0.5)
    params.update(kw)
    return client.get("/api/surface", params={k: v for k, v in params.items() if v is not None})


def test_surface_layers_by_mode(client):
    assert surface(client).json()["layers"] == ["open", "demand"]
    assert surface(client, demand="").json()["layers"] == ["competition"]
    assert surface(client, type="").json()["layers"] == ["demand"]
    r = surface(client, type="", demand="")
    assert r.status_code == 422


def test_surface_grid_shape(client):
    j = surface(client).json()
    g = j["grid"]
    assert g["west"] < LNG < g["east"] and g["south"] < LAT < g["north"]
    for layer in j["layers"]:
        v = j["values"][layer]
        assert len(v) == g["nx"] * g["ny"]
        assert v[0] is None and v[-1] is None                  # rogi kwadratu są poza okręgiem
        assert max(x for x in v if x is not None) > 0
    assert j["values"]["open"][g["ny"] // 2 * g["nx"] + g["nx"] // 2] is not None


def test_surface_open_higher_far_from_competitor(client):
    """Przy tym samym popycie „Gdzie otworzyć” jest większe tam, gdzie nie ma konkurenta."""
    j = surface(client, radius_km=3, reach_km=0.5).json()
    g = j["grid"]

    def at(layer, dlat, dlng):
        row = round((g["north"] - (LAT + dlat)) / (g["north"] - g["south"]) * g["ny"] - 0.5)
        col = round(((LNG + dlng) - g["west"]) / (g["east"] - g["west"]) * g["nx"] - 0.5)
        return j["values"][layer][row * g["nx"] + col]

    near_comp, far = at("open", 0, 0), at("open", -0.015, 0.0)  # po drugiej stronie, bez firm w pobliżu
    assert at("demand", 0, 0) == pytest.approx(at("demand", -0.015, 0.0), rel=0.15)
    assert far > near_comp


def test_surface_top_in_circle(client):
    j = surface(client).json()
    for layer in j["layers"]:
        top = j["top"][layer]
        assert 0 < len(top) <= 5
        assert all(t["name"] and t["value"] > 0 for t in top)
        # w okręgu 3 km wokół środka
        assert all(abs(t["lat"] - LAT) < 0.03 and abs(t["lng"] - LNG) < 0.05 for t in top)
        assert [t["value"] for t in top] == sorted((t["value"] for t in top), reverse=True)


def test_surface_sea_edge(make_client):
    """Okrąg w połowie nad morzem (brak danych) → 200, wartości tylko tam, gdzie jest popyt."""
    pop = {c: 1000.0 for c in disk(center=(54.50, 18.55), k=6)}          # ląd tylko wokół punktu
    client = make_client(pop=pop, pois=[("cafe", 54.5, 18.55)])
    r = surface(client, type="", lat=54.55, lng=18.55, radius_km=30, reach_km=1)
    assert r.status_code == 200
    j = r.json()
    assert j["top"]["demand"] and all(t["value"] > 0 for t in j["top"]["demand"])
    assert any(x == 0 for x in j["values"]["demand"] if x is not None)  # morze daleko od lądu = 0


def test_surface_no_competitors_gives_finite_values(client):
    j = surface(client, type="beauty").json()                           # brak firm tego typu
    assert j["warnings"] and all(x is None or x >= 0 for x in j["values"]["open"])
    assert j["top"]["open"]


def test_surface_permits_min_reach(client):
    j = surface(client, type="", demand="new_sf", reach_km=0.3).json()
    assert j["reach_km"] == 1.0 and j["permits_period"]["to"] == "2026-09"
    assert any("obrębu" in n for n in j["notes"])


def test_surface_large_reach_fast(client):
    t0 = time.time()
    r = surface(client, radius_km=30, reach_km=20)
    assert r.status_code == 200 and time.time() - t0 < 5


def test_surface_validation(client):
    assert surface(client, lat=10).status_code == 422                   # poza Polską
    assert surface(client, radius_km=0.5).status_code == 422
    assert surface(client, radius_km=31).status_code == 422
    assert "1–30" in surface(client, radius_km=31).json()["detail"]
    assert surface(client, reach_km=0.01).status_code == 422
    assert surface(client, type="xxx").status_code == 422
    assert surface(client, demand="xxx").status_code == 422
    assert surface(client, months=5).status_code == 422
    assert surface(client, lng=None).status_code == 422
    assert client.get("/api/view", params={}).status_code in (404, 405)


def test_surface_cache_same_key(client):
    a = surface(client).json()
    b = surface(client, lat=LAT + 0.00001).json()                       # to samo po zaokrągleniu
    assert a == b

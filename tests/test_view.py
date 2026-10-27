"""Testy GET /api/view: heatmapa dla widocznego fragmentu mapy (tryby, poziomy szczegółowości, zasięg-okrąg)."""
import h3
import numpy as np
import pytest

from backend.app.analysis import service
from backend.app.analysis.kernel import to_metric
from tests.conftest import CENTER, disk

LAT, LNG = CENTER
CITY_BBOX = "20.97,52.20,21.05,52.26"          # ~6 × 7 km wokół środka siatki testowej
POLAND_BBOX = "14.1,49.0,24.2,54.9"


def _pop(k=12, value=1000.0):
    return {c: value for c in disk(k=k)}


def _pois():
    # kilka fryzjerów wokół środka (0,0045° szerokości ≈ 500 m)
    return [("hairdresser", LAT, LNG), ("hairdresser", LAT + 0.0045, LNG), ("hairdresser", LAT - 0.01, LNG + 0.01),
            ("hairdresser", LAT + 0.015, LNG - 0.012), ("cafe", LAT, LNG + 0.005)]


@pytest.fixture
def client(make_client):
    return make_client(pop=_pop(), pois=_pois(),
                       permits=[(LAT, LNG, "2026-09-01", "sf", 5), (LAT + 0.01, LNG, "2026-08-01", "sf", 3)])


def view(client, **kw):
    params = dict(type="hairdresser", demand="pop_total", bbox=CITY_BBOX, zoom=13, bandwidth_km=0.5)
    params.update(kw)
    return client.get("/api/view", params={k: v for k, v in params.items() if v is not None})


def test_view_full_mode(client):
    r = view(client)
    assert r.status_code == 200
    j = r.json()
    assert j["display_res"] == 9 and j["mode"] == "full" and j["top_metric"] == "score"
    assert j["hexes"] and all(len(row) == 7 for row in j["hexes"])
    assert all(h3.get_resolution(row[0]) == 9 for row in j["hexes"])
    assert all(0 <= row[4] <= 100 and 0 <= row[5] <= 100 and 0 <= row[6] <= 100 for row in j["hexes"])
    assert len(j["legend"]["score"]) == 6 and set(j["legend"]) == {"score", "D", "S"}
    assert j["top"] and all(t["name"] for t in j["top"]) and len(j["top"]) <= 5
    assert j["radius_km"] == 0.5


def test_view_lod_parent_cells(client):
    j = view(client, zoom=10).json()
    assert j["display_res"] == 8 and j["compute_res"] >= 8
    assert j["hexes"] and all(h3.get_resolution(row[0]) == 8 for row in j["hexes"])


def test_view_modes(client):
    comp = view(client, demand="").json()
    assert comp["mode"] == "competition" and set(comp["legend"]) == {"S"} and comp["top_metric"] == "S"
    assert comp["hexes"] and all(row[1] is None and row[2] is None and row[3] > 0 for row in comp["hexes"])
    dem = view(client, type="").json()
    assert dem["mode"] == "demand" and set(dem["legend"]) == {"D"} and dem["top_metric"] == "D"
    assert dem["hexes"] and all(row[1] is None and row[3] is None and row[2] > 0 for row in dem["hexes"])


def test_view_requires_one(client):
    r = view(client, type="", demand="")
    assert r.status_code == 422 and r.json()["detail"] == "Wybierz typ działalności albo czynnik popytu"


@pytest.mark.parametrize("override, message", [
    (dict(bbox="1,2,3"), "Nieprawidłowy bbox"),
    (dict(bbox="20,52,19,53"), "Nieprawidłowy bbox"),
    (dict(zoom=2), "zoom"),
    (dict(bandwidth_km=0.05), "bandwidth"),
    (dict(bandwidth_km=25), "bandwidth"),
    (dict(months=18), "Okres"),
    (dict(type="xxx"), "Nieznany typ"),
    (dict(demand="xxx"), "Nieznany czynnik"),
])
def test_view_validation(client, override, message):
    r = view(client, **override)
    assert r.status_code == 422 and message in str(r.json()["detail"])


def test_view_disk_counts_exact(make_client):
    """D to dokładna suma ludności komórek, których środek leży w okręgu zasięgu; S — liczba firm w okręgu."""
    pop = {c: float(i + 1) for i, c in enumerate(disk(k=8))}
    client = make_client(pop=pop, pois=[("hairdresser", LAT + 0.0045, LNG)])   # ~500 m na północ od środka
    center = h3.latlng_to_cell(LAT, LNG, 9)
    j = view(client, bbox="21.0,52.22,21.02,52.24", bandwidth_km=1).json()
    row = next(r for r in j["hexes"] if r[0] == center)

    ll = np.array([h3.cell_to_latlng(c) for c in pop])
    xy = to_metric(ll[:, 0], ll[:, 1])
    c_xy = xy[list(pop).index(center)]
    expected = sum(v for v, p in zip(pop.values(), xy) if np.hypot(*(p - c_xy)) <= 1000)
    assert row[2] == pytest.approx(expected) and row[3] == 1
    assert row[1] == pytest.approx(expected / 2, rel=1e-3)          # D / (S + 1)


def test_view_empty_area(client):
    j = view(client, bbox="18.0,55.0,18.5,55.3").json()          # Bałtyk
    assert j["hexes"] == [] and j["top"] == [] and j["legend"] == {}


def test_view_country_small_radius_note(client):
    j = view(client, bbox=POLAND_BBOX, zoom=6, bandwidth_km=0.1).json()
    assert j["display_res"] == 5 and j["compute_res"] < 9
    assert any("najmniejszy liczony zasięg" in n for n in j["notes"])
    assert j["hexes"] and all(h3.get_resolution(row[0]) == 5 for row in j["hexes"])


def test_view_permits_min_radius(client):
    j = view(client, type="", demand="new_sf", bandwidth_km=0.3).json()
    assert j["radius_km"] == 1.0 and any("obrębu" in n for n in j["notes"])
    assert j["permits_period"]["to"] == "2026-09" and j["hexes"]


def test_view_permits_missing_warning(make_client):
    client = make_client(pop=_pop(k=3))
    j = view(client, type="", demand="new_sf").json()
    assert j["hexes"] == [] and any("pozwolenia" in w.lower() or "pozwole" in w.lower() for w in j["warnings"])


def test_view_poor_type_warning(client):
    j = view(client, type="nails", demand="pop_f").json()
    assert any("niepełne" in w for w in j["warnings"])


def test_view_no_competitors_warning(client):
    j = view(client, type="tattoo").json()
    assert any("konkurencji" in w for w in j["warnings"]) and j["hexes"]


def test_view_cache_hit_on_small_pan(client, monkeypatch):
    calls = []
    real = service._compute_core
    monkeypatch.setattr(service, "_compute_core", lambda con, p: calls.append(p) or real(con, p))
    service._cached_core.cache_clear()
    a = view(client, bbox="20.981,52.201,21.041,52.261").json()
    b = view(client, bbox="20.991,52.211,21.051,52.261").json()      # przesunięcie o 0,01° → ten sam przyciągnięty bbox
    assert len(calls) == 1
    assert a["hexes"] == b["hexes"]

"""Testy GET /api/point: dokładne liczby w okręgu zasięgu wokół klikniętego punktu."""
import h3
import pytest

from backend.app.analysis.service import _haversine_km
from tests.conftest import CENTER, disk

LAT, LNG = CENTER
POP = {c: 1000.0 for c in disk(k=12)}
# 0,0027° szerokości ≈ 300 m; 0,018° ≈ 2 km
POIS = [("hairdresser", LAT + 0.0027, LNG), ("hairdresser", LAT + 0.018, LNG), ("cafe", LAT, LNG + 0.001)]


def point(client, **kw):
    params = dict(lat=LAT, lng=LNG, type="hairdresser", demand="pop_total", reach_km=1)
    params.update(kw)
    return client.get("/api/point", params={k: v for k, v in params.items() if v is not None})


@pytest.fixture
def client(make_client):
    return make_client(pop=POP, pois=POIS, permits=[(LAT, LNG, "2026-09-01", "sf", 5), (LAT + 0.2, LNG, "2026-09-01", "sf", 7)])


def test_point_counts(client):
    j = point(client).json()
    expected = sum(v for c, v in POP.items() if _haversine_km(LAT, LNG, *h3.cell_to_latlng(c)) <= 1.0)
    assert j["radius_km"] == 1 and j["demand"] == pytest.approx(expected)
    assert j["demand_name"] == "Mieszkańcy" and j["type_name"] == "Fryzjer"
    assert j["competitors"] == 1                                   # drugi fryzjer jest 2 km stąd
    assert len(j["nearest"]) == 1 and j["nearest"][0]["distance_m"] == pytest.approx(300, abs=5)
    assert j["nearest"][0]["name"].startswith("Firma")


def test_point_expected_matches_surface(client):
    """„Otwierając tu, zdobyłbyś…” z /api/point zgadza się z mapą (/api/surface) w tym samym miejscu."""
    j = point(client, reach_km=0.5).json()
    s = client.get("/api/surface", params=dict(type="hairdresser", demand="pop_total", lat=LAT, lng=LNG,
                                               radius_km=2, reach_km=0.5)).json()
    g = s["grid"]
    row = int((g["north"] - LAT) / (g["north"] - g["south"]) * g["ny"])
    col = int((LNG - g["west"]) / (g["east"] - g["west"]) * g["nx"])
    near = [s["values"]["open"][r * g["nx"] + c] for r in (row - 1, row, row + 1) for c in (col - 1, col, col + 1)]
    assert j["expected"] > 0 and min(near) * 0.9 <= j["expected"] <= max(near) * 1.1
    assert "score" not in j


def test_point_expected_only_with_type_and_demand(client):
    assert point(client, demand="").json()["expected"] is None
    assert point(client, type="").json()["expected"] is None


def test_point_cells_in_reach(client):
    j = point(client, reach_km=1).json()
    assert j["cells"] and len(j["cells"]) < 60
    assert all(h3.get_resolution(c) == 9 and pop == 1000.0 for c, pop in j["cells"])
    assert all(_haversine_km(LAT, LNG, *h3.cell_to_latlng(c)) <= 1.0 + 1e-6 for c, _ in j["cells"])
    assert point(client, reach_km=5).json()["cells"] == []         # za duży zasięg — nie rysujemy komórek


def test_point_nearest_lists_up_to_five_sorted(make_client):
    pois = [("hairdresser", LAT + 0.001 * k, LNG) for k in range(1, 9)]
    j = point(make_client(pop=POP, pois=pois), reach_km=2).json()
    d = [n["distance_m"] for n in j["nearest"]]
    assert j["competitors"] == 8 and len(d) == 5 and d == sorted(d)


def test_point_empty(client):
    j = point(client, lat=54.6, lng=18.2).json()                   # Bałtyk
    assert j["demand"] == 0 and j["competitors"] == 0 and j["expected"] == 0 and j["nearest"] == [] and j["cells"] == []


def test_point_modes(client):
    only_type = point(client, demand="").json()
    assert only_type["demand"] is None and only_type["expected"] is None and only_type["competitors"] == 1
    only_demand = point(client, type="").json()
    assert only_demand["competitors"] is None and only_demand["expected"] is None and only_demand["nearest"] == []
    assert only_demand["demand"] > 0


def test_point_permits_min_radius_and_period(client):
    j = point(client, type="", demand="new_sf", reach_km=0.3).json()
    assert j["radius_km"] == 1.0 and j["demand"] == 5 and j["permits_period"]["to"] == "2026-09"
    assert any("obrębu" in n for n in j["notes"])


def test_point_validation(client):
    assert point(client, lat=10).status_code == 422                # poza Polską
    assert point(client, type="", demand="").status_code == 422
    assert point(client, reach_km=0.01).status_code == 422
    assert point(client, type="xxx").status_code == 422
    assert point(client, lat=None).status_code == 422


def test_point_small_radius_counts_own_cell(client):
    """Okrąg 0,1 km zwykle nie obejmuje środka żadnej komórki — komórka klikniętego punktu liczy się zawsze (jak w heatmapie)."""
    center_cell = h3.latlng_to_cell(LAT, LNG, 9)
    c_lat, c_lng = h3.cell_to_latlng(center_cell)
    for dlat, dlng in [(0.0011, 0), (-0.0011, 0), (0, 0.0018), (0, -0.0018)]:
        lat, lng = c_lat + dlat, c_lng + dlng
        if h3.latlng_to_cell(lat, lng, 9) == center_cell and _haversine_km(lat, lng, c_lat, c_lng) > 0.105:
            break
    else:
        pytest.fail("nie znaleziono punktu w komórce, ale dalej niż 0,1 km od jej środka")
    j = point(client, lat=lat, lng=lng, type="", reach_km=0.1).json()
    assert j["demand"] == pytest.approx(1000.0)      # tylko własna komórka (pop 1000)

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


# ---------------------------------------------------------------- luki w danych (v3.3) ----

CITY = (51.10, 17.03)


@pytest.fixture
def gap_client(make_client):
    """Miasteczko bez salonów (CENTER) i miasto ze 100 salonami (Wrocław); luki policzone."""
    pop = {c: 1000.0 for c in disk(CENTER, k=12)} | {c: 1000.0 for c in disk(CITY, k=12)}
    # salony co ok. 0,9 km w całym mieście (każdy punkt ma ich w 2 km kilkanaście), bez pustych obrzeży
    pois = [("beauty", CITY[0] + (i % 10 - 4.5) * 0.008, CITY[1] + (i // 10 - 4.5) * 0.012) for i in range(100)]
    return make_client(pop=pop, pois=pois, gaps=True)


def test_surface_gap_mask_in_town_without_firms(gap_client):
    j = surface(gap_client, type="beauty", demand="pop_f", reach_km=1.5).json()
    values, gap = j["values"]["open"], j["gap"]["open"]
    assert len(gap) == len(values)
    assert all((g is None) == (v is None) for g, v in zip(gap, values))     # poza okręgiem None w obu
    assert {g for g in gap if g is not None} == {1}                         # całe miasteczko to luka
    assert j["top"]["open"] == []                                           # i nic z niego nie trafia do najlepszych miejsc
    assert max(v for v in values if v is not None) > 0                      # mgła nadal pokazuje pełne E


def test_surface_gap_absent_in_city_with_firms(gap_client):
    j = surface(gap_client, type="beauty", demand="pop_f", reach_km=1.5, lat=CITY[0], lng=CITY[1], radius_km=1).json()
    assert 1 not in set(j["gap"]["open"]) and j["top"]["open"]


def test_surface_open_value_unchanged_by_gap_logic(client):
    """Kolor mgły to nadal pełne E (taki sam jak bez luk) — luki wpływają tylko na kreskowanie i top-5."""
    j = surface(client).json()
    assert set(j["gap"]["open"]) <= {0, None} and j["top"]["open"]


def test_surface_other_layers_have_no_gap(client):
    assert "gap" not in surface(client, type="").json()
    assert "gap" not in surface(client, demand="").json()


# ---- v3.4: prostokąt zaznaczony przez użytkownika (area=rect) ----

def rect_surface(client, **kw):
    params = dict(type="hairdresser", demand="pop_total", reach_km=0.5, area="rect",
                  west=LNG - 0.03, south=LAT - 0.02, east=LNG + 0.03, north=LAT + 0.02)
    params.update(kw)
    return client.get("/api/surface", params={k: v for k, v in params.items() if v is not None})


def test_surface_rect_summary_has_size_and_denser_grid(client):
    rect = rect_surface(client).json()
    view = rect_surface(client, area=None).json()               # bez area: widok mapy (zachowanie z v3.2)
    assert rect["summary"]["shape"] == "rect" and view["summary"]["shape"] == "view"
    assert abs(rect["summary"]["width_km"] - 0.06 * 111.32 * 0.6) < 1.5 and rect["summary"]["height_km"] > 4
    assert rect["grid"]["nx"] > view["grid"]["nx"]              # divisions 90 zamiast 60
    values = rect["values"]["open"]
    assert values[0] is None and max(x for x in values if x is not None) > 0     # poza prostokątem null


def test_surface_rect_limits(client):
    assert rect_surface(client, east=LNG + 1).status_code == 422                 # bok > 60 km
    tiny = rect_surface(client, west=LNG - 0.002, east=LNG + 0.002, south=LAT - 0.002, north=LAT + 0.002)
    assert tiny.status_code == 422 and "najmniej" in tiny.json()["detail"]       # bok < 0,6 km
    assert rect_surface(client, area="x").status_code == 422
    # widok mapy nie ma dolnego limitu (zachowanie sprzed v3.4)
    assert rect_surface(client, area=None, west=LNG - 0.002, east=LNG + 0.002, south=LAT - 0.002, north=LAT + 0.002).status_code == 200


def test_surface_rect_and_view_cached_separately(client):
    assert rect_surface(client).json()["summary"]["shape"] == "rect"
    assert rect_surface(client, area=None).json()["summary"]["shape"] == "view"

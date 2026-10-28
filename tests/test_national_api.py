"""Testy GET /api/national (gotowa mapa Polski) oraz trybu „widoczny obszar” w /api/surface."""
import pytest

from backend.app.analysis.national import choose_resolution
from tests.conftest import CENTER, disk

LAT, LNG = CENTER
POIS = [("beauty", LAT, LNG), ("beauty", LAT + 0.02, LNG - 0.03), ("hairdresser", LAT, LNG + 0.005)]
PERMITS = [(LAT, LNG, "2026-09-01", "sf", 5), (LAT + 0.01, LNG, "2026-08-01", "sf", 3), (LAT, LNG, "2025-03-01", "sf", 1)]
PLACES = [("Śródmieście", "suburb", LAT, LNG)]
VIEW = dict(west=LNG - 0.2, south=LAT - 0.12, east=LNG + 0.2, north=LAT + 0.12)


@pytest.fixture
def client(make_client):
    return make_client(pop={c: 1000.0 for c in disk(k=12)}, pois=POIS, permits=PERMITS, places=PLACES, national=True)


def national(client, **kw):
    params = dict(type="beauty", demand="pop_f", px=1000, **VIEW)
    params.update(kw)
    return client.get("/api/national", params={k: v for k, v in params.items() if v is not None})


def test_national_shape(client):
    j = national(client).json()
    g = j["grid"]
    assert j["layers"] == ["open", "demand"] and j["mode"] == "national" and j["reach_km"] == 1.5
    assert g["nx"] * g["ny"] == len(j["values"]["open"]) and g["west"] < g["east"] and g["south"] < g["north"]
    for layer in j["layers"]:
        assert max(x for x in j["values"][layer] if x is not None) > 0
        assert j["scale"][layer]["hi"] >= j["scale"][layer]["lo"] > 0
        top = j["top"][layer]
        assert 0 < len(top) <= 5 and [t["value"] for t in top] == sorted((t["value"] for t in top), reverse=True)
        assert all(t["name"] for t in top)
    assert any("1,5 km" in n and "Przybliż" in n for n in j["notes"])
    assert j["top"]["open"][0]["name"] == "Śródmieście"


def test_national_layers_by_mode(client):
    assert national(client, demand="").json()["layers"] == ["competition"]
    assert national(client, type="").json()["layers"] == ["demand"]
    permits = national(client, type="", demand="new_sf").json()
    assert permits["layers"] == ["demand", "trend"] and permits["reach_km"] == 10.0
    assert permits["permits_period"]["to"] == "2026-09"
    assert national(client, type="", demand="").status_code == 422


def test_national_scale_is_fixed_regardless_of_view(client):
    """Stała skala kolorów dla całego kraju: ta sama niezależnie od kadru (inaczej kolory „pływałyby” przy przesuwaniu)."""
    wide = national(client).json()
    narrow = national(client, west=LNG - 0.02, south=LAT - 0.01, east=LNG + 0.02, north=LAT + 0.01).json()
    assert wide["scale"] == narrow["scale"]
    assert wide["grid"] != narrow["grid"]


def test_national_value_independent_of_resolution_choice(client):
    """Oddalenie bierze maksimum z dzieci: największa wartość w kadrze nie maleje przy grubszej rozdzielczości."""
    fine = national(client, px=4000).json()
    coarse = national(client, px=200).json()
    best = lambda j: max(x for x in j["values"]["open"] if x is not None)
    assert fine["resolution"] >= coarse["resolution"]
    assert best(coarse) >= best(fine) * 0.999


def test_choose_resolution_by_pixels():
    assert choose_resolution(800, 600, 1000) == 6           # cała Polska w 1000 px: ~0,8 km/px → grube komórki
    assert choose_resolution(30, 20, 1000) == 8             # miasto: najdrobniejsze
    assert choose_resolution(30, 20, 200) >= choose_resolution(30, 20, 4000)
    assert choose_resolution(900, 900, 4000) in (5, 6, 7, 8)


def test_national_missing_layer_gives_note(client):
    """Czynnik spoza zalecanych dla branży albo bez gotowej warstwy → tylko dostępne warstwy + notatka o trybie na żywo."""
    j = national(client, type="hairdresser", demand="pop_ge65").json()          # „Gdzie otworzyć” tylko na żywo
    assert j["layers"] == ["demand"] and any("na żywo" in n for n in j["notes"])
    j = national(client, type="diy", demand="pop_f").json()                      # zasięg 15 km nie ma gotowej warstwy popytu
    assert j["layers"] == [] and j["values"] == {} and any("na żywo" in n for n in j["notes"])


def test_national_warning_for_medium_quality(client):
    assert national(client, type="nails", demand="pop_f").json()["warnings"]
    assert national(client).json()["warnings"] == []


def test_national_validation(client):
    assert national(client, type="xxx").status_code == 422
    assert national(client, demand="xxx").status_code == 422
    assert national(client, west=LNG + 1).status_code == 422                      # west > east
    assert national(client, px=0).status_code == 422
    assert national(client, px=10).status_code == 200                              # px poza zakresem jest przycinane
    assert national(client, px=99999).status_code == 200
    assert national(client, north=None).status_code == 422
    assert national(client, type="paving").status_code == 422                     # usunięty z katalogu


def test_national_cache_rounds_view(client):
    a = national(client).json()
    b = national(client, west=VIEW["west"] + 1e-6, px=1010).json()
    assert a == b


def test_national_missing_tables_is_503(make_client):
    client = make_client(pop={c: 1000.0 for c in disk(k=2)}, pois=POIS)           # bez kroku national
    r = national(client)
    assert r.status_code == 503 and "national" in r.json()["detail"]


# ---- /api/surface w trybie widocznego obszaru ----

def view_surface(client, **kw):
    params = dict(type="beauty", demand="pop_f", reach_km=0.5, west=LNG - 0.03, south=LAT - 0.02, east=LNG + 0.03, north=LAT + 0.02)
    params.update(kw)
    return client.get("/api/surface", params={k: v for k, v in params.items() if v is not None})


def test_surface_view_mode_masks_to_rectangle(client):
    j = view_surface(client).json()
    g = j["grid"]
    values = j["values"]["open"]
    assert j["summary"]["shape"] == "view" and j["layers"] == ["open", "demand"]
    # w prostokącie są wartości, a w rogach kwadratu siatki (poza prostokątem) null
    assert max(x for x in values if x is not None) > 0
    assert values[0] is None and values[-1] is None and values[g["nx"] - 1] is None
    non_null = sum(x is not None for x in values)
    assert 0.3 < non_null / len(values) < 0.9


def test_surface_view_summary_counts_only_visible_area(client):
    small = view_surface(client, west=LNG - 0.005, east=LNG + 0.005, south=LAT - 0.005, north=LAT + 0.005).json()["summary"]
    wide = view_surface(client).json()["summary"]
    assert 0 < small["demand_total"] < wide["demand_total"]
    assert small["competitors"]["total"] == 1 and wide["competitors"]["total"] >= 1


def test_surface_view_validation(client):
    assert view_surface(client, east=LNG + 1).status_code == 422                   # bok > 60 km
    assert view_surface(client, north=None).status_code == 422                     # niepełny prostokąt
    assert view_surface(client, west=LNG + 1).status_code == 422                   # odwrócone granice
    assert client.get("/api/surface", params=dict(type="beauty", demand="pop_f", reach_km=1)).status_code == 422   # ani okrąg, ani widok


def test_view_place_name_prefers_larger_place_over_distant_village():
    import duckdb
    from backend.app.analysis.national import place_name
    con = duckdb.connect()
    con.execute("CREATE TABLE places (name VARCHAR, kind VARCHAR, lat DOUBLE, lng DOUBLE, h3 VARCHAR)")
    con.execute("INSERT INTO places VALUES ('Miasteczko', 'town', 53.5835, 20.2865, 'x'), ('Wioska', 'village', 53.585, 20.324, 'x')")
    assert place_name(con, 53.586, 20.286) == "Miasteczko"          # miasteczko 0,3 km od punktu, wioska 2,6 km
    assert place_name(con, 53.585, 20.322) == "Wioska"              # przy samej wiosce wygrywa wioska
    assert place_name(con, 40.0, 10.0) is None                      # nic w pobliżu


def test_national_notes_warn_about_data_gaps(client):
    assert any("luk" in n for n in national(client).json()["notes"])           # warstwy z konkurencją
    assert not any("luk" in n for n in national(client, type="").json()["notes"])   # sam popyt nie zależy od firm


def test_national_top_is_refined_to_best_child_cell(client):
    """W oddalonym widoku (res < 8) pinezka stoi na faktycznie najlepszej komórce res 8, a nie na środku komórki-rodzica."""
    from backend.app.db import cursor
    j = national(client, px=200, west=LNG - 3, south=LAT - 2, east=LNG + 3, north=LAT + 2).json()
    assert j["resolution"] < 8
    con = cursor()
    for item in j["top"]["open"]:
        (value,) = con.execute('SELECT "open__beauty__pop_f" FROM national_r8 WHERE lat = ? AND lng = ?',
                               [item["lat"], item["lng"]]).fetchone()
        assert value == pytest.approx(item["value"], rel=1e-6)


def test_national_reports_reach_of_each_layer(client):
    """Trend jest zawsze liczony dla zasięgu domyślnego czynnika (10 km), a „Gdzie otworzyć” dla zasięgu branży (diy: 15 km)."""
    j = national(client, type="diy", demand="new_sf").json()
    assert j["layer_reach_km"] == {"open": 15.0, "demand": 15.0, "trend": 10.0}


def test_national_ignores_layer_missing_in_pyramid(make_client, tmp_path):
    """Przerwany ETL mógł zapisać warstwę w res 8 bez piramidy — API nie może jej oferować (zapytanie o res 5–7 dałoby błąd 500)."""
    import duckdb
    from backend.app import config
    from backend.app.db import reset_connection
    client = make_client(pop={c: 1000.0 for c in disk(k=3)}, pois=POIS, national=True)
    reset_connection()
    con = duckdb.connect(str(config.DB_PATH))
    con.execute('ALTER TABLE national_r6 DROP COLUMN "open__beauty__pop_f"')
    con.close()
    reset_connection()
    j = national(client).json()
    assert j["layers"] == ["demand"]

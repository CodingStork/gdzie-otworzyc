import duckdb
import pytest

from backend.app.analysis.service import nearest_place_name
from tests.conftest import CENTER, disk

LAT, LNG = CENTER
# 1° szerokości ≈ 111 km; 0,018° ≈ 2 km, 0,0045° ≈ 0,5 km
DLAT_2KM, DLAT_05KM = 0.018, 0.0045
VIEW_BBOX = "20.97,52.20,21.05,52.26"


def _con(make_client, places, **kw):
    """Klient API (i tym samym baza w pliku) + osobne połączenie do wywołań serwisu."""
    from backend.app import config
    client = make_client(places=places, **kw)
    return client, duckdb.connect(str(config.DB_PATH), read_only=True)


def test_suburb_two_km_beats_city_half_km(make_client):
    _, con = _con(make_client, [("Śródmieście Wielkie", "city", LAT + DLAT_05KM, LNG),
                                ("Zaodrze", "suburb", LAT + DLAT_2KM, LNG)])
    assert nearest_place_name(con, LAT, LNG) == "Zaodrze"


def test_nearest_within_same_priority(make_client):
    _, con = _con(make_client, [("Daleko", "village", LAT + DLAT_2KM, LNG), ("Blisko", "village", LAT + DLAT_05KM, LNG)])
    assert nearest_place_name(con, LAT, LNG) == "Blisko"


def test_town_beats_city_when_no_suburb(make_client):
    _, con = _con(make_client, [("Miasto", "city", LAT + DLAT_05KM, LNG), ("Miasteczko", "town", LAT + DLAT_2KM, LNG)])
    assert nearest_place_name(con, LAT, LNG) == "Miasteczko"


def test_nothing_within_three_km_returns_none(make_client):
    _, con = _con(make_client, [("Za daleko", "suburb", LAT + 0.04, LNG)])    # ~4,4 km
    assert nearest_place_name(con, LAT, LNG) is None


def test_missing_places_table_returns_none(make_client):
    client = make_client(pop={c: 1.0 for c in disk(k=2)})
    from backend.app import config
    assert nearest_place_name(duckdb.connect(str(config.DB_PATH), read_only=True), LAT, LNG) is None


def test_view_top_uses_place_names(make_client):
    pop = {c: 1000.0 for c in disk()}
    # siatka wsi co ~1,4 km pokrywa całe dane — każdy heksagon ma miejscowość w promieniu 3 km
    places = [("Osiedle Testowe", "suburb", LAT, LNG)] + [
        (f"Wieś {i}/{j}", "village", LAT + i * 0.0125, LNG + j * 0.02) for i in range(-10, 11) for j in range(-10, 11)]
    client = make_client(pop=pop, places=places, pois=[("beauty", LAT, LNG)])
    j = client.get("/api/view", params=dict(type="beauty", demand="pop_f", bbox=VIEW_BBOX, zoom=13, bandwidth_km=1)).json()
    assert all(not t["name"].startswith("okolice") for t in j["top"])
    assert all(t["name"] for t in j["top"])


def test_view_top_falls_back_to_coordinates(api_client):
    j = api_client.get("/api/view", params=dict(type="beauty", demand="pop_f", bbox=VIEW_BBOX, zoom=13, bandwidth_km=1)).json()
    assert all(t["name"].startswith("okolice ") for t in j["top"])


def test_api_poi_filters_type_and_bbox(make_client):
    client = make_client(pop={}, pois=[("cafe", LAT, LNG), ("cafe", LAT + 1, LNG), ("beauty", LAT, LNG)])
    bbox = f"{LNG - 0.1},{LAT - 0.1},{LNG + 0.1},{LAT + 0.1}"
    j = client.get("/api/poi", params=dict(type="cafe", bbox=bbox)).json()
    assert j["truncated"] is False and len(j["items"]) == 1
    assert set(j["items"][0]) == {"lat", "lng", "name"}


def test_api_poi_truncates_at_5000(make_client):
    pois = [("cafe", LAT + (i % 100) * 0.0001, LNG + (i // 100) * 0.0001) for i in range(5001)]
    client = make_client(pop={}, pois=pois)
    bbox = f"{LNG - 0.1},{LAT - 0.1},{LNG + 0.1},{LAT + 0.1}"
    j = client.get("/api/poi", params=dict(type="cafe", bbox=bbox)).json()
    assert len(j["items"]) == 5000 and j["truncated"] is True


def test_api_poi_validation(api_client):
    assert api_client.get("/api/poi", params=dict(type="cafe", bbox="1,2,3")).status_code == 422
    r = api_client.get("/api/poi", params=dict(type="cafe", bbox="a,b,c,d"))
    assert r.status_code == 422 and "Nieprawidłowy bbox" in r.text
    assert api_client.get("/api/poi", params=dict(type="cafe", bbox="20,52,19,53")).status_code == 422
    assert api_client.get("/api/poi", params=dict(type="xxx", bbox="19,52,20,53")).status_code == 422


def test_api_poi_without_table_returns_empty(make_client):
    client = make_client(pop={c: 1.0 for c in disk(k=1)})
    j = client.get("/api/poi", params=dict(type="cafe", bbox="19,52,22,53")).json()
    assert j == {"items": [], "truncated": False}

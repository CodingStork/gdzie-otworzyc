"""v3.3: ostrzeżenia „mało danych o firmach” w dymku (/api/point) i w podsumowaniu obszaru (/api/surface → summary)."""
import pytest

from tests.conftest import CENTER, disk

TOWN = CENTER
CITY = (51.10, 17.03)


@pytest.fixture
def client(make_client):
    """Miasteczko bez salonów (CENTER) i miasto ze 100 salonami rozłożonymi po całym mieście (Wrocław)."""
    pop = {c: 1000.0 for c in disk(TOWN, k=12)} | {c: 1000.0 for c in disk(CITY, k=12)}
    pois = [("beauty", CITY[0] + (i % 10 - 4.5) * 0.008, CITY[1] + (i // 10 - 4.5) * 0.012) for i in range(100)]
    return make_client(pop=pop, pois=pois, gaps=True)


def point(client, place, **kw):
    params = dict(lat=place[0], lng=place[1], type="beauty", demand="pop_f", reach_km=1.5)
    params.update(kw)
    return client.get("/api/point", params={k: v for k, v in params.items() if v is not None}).json()


def summary(client, place, **kw):
    params = dict(lat=place[0], lng=place[1], type="beauty", demand="pop_f", radius_km=3, reach_km=1.5)
    params.update(kw)
    return client.get("/api/surface", params={k: v for k, v in params.items() if v is not None}).json()["summary"]


def test_point_in_town_without_firms_warns_with_numbers(client):
    g = point(client, TOWN)["data_gap"]
    assert g["warn"] is True and g["observed"] == 0 and g["expected"] >= 3 and g["radius_km"] == 2
    assert g["share"] == pytest.approx(1.0, abs=0.01)           # wszyscy klienci tego miejsca mieszkają w luce


def test_point_in_city_does_not_warn(client):
    g = point(client, CITY)["data_gap"]
    assert g["warn"] is False and g["observed"] > 0.25 * g["expected"] and g["share"] < 0.5


def test_point_data_gap_needs_type_and_demand(client):
    assert point(client, TOWN, demand="")["data_gap"] is None
    assert point(client, TOWN, type="")["data_gap"] is None


def test_point_data_gap_none_without_gap_tables(make_client):
    c = make_client(pop={cell: 1000.0 for cell in disk(k=3)}, pois=[("beauty", *CENTER)])
    assert point(c, CENTER)["data_gap"] is None


def test_summary_warns_when_area_has_far_fewer_firms_than_average(client):
    s = summary(client, TOWN)
    assert s["data_gap"] is True and s["competitors"]["total"] == 0 and s["expected_firms"] >= 3
    assert s["verdict"] == "unknown"                            # zamiast „mniej konkurencji niż średnio”


def test_summary_no_warning_in_city(client):
    s = summary(client, CITY)
    assert s["data_gap"] is False and s["verdict"] in ("less", "similar", "more") and s["verdict"] != "unknown"


def test_summary_without_gap_tables_has_no_warning(make_client):
    c = make_client(pop={cell: 1000.0 for cell in disk(k=3)}, pois=[("beauty", *CENTER)])
    s = summary(c, CENTER)
    assert s["data_gap"] is False and s["expected_firms"] is None

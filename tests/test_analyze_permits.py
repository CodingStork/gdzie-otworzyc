import pytest

from tests.conftest import CENTER, disk

LAT, LNG = CENTER
PARAMS = dict(type="paving", lat=LAT, lng=LNG, radius_km=5)


@pytest.fixture
def api_client_with_permits(make_client):
    """Ludność wokół Warszawy + pozwolenia: sf 5 (2026-09) i 7 (2024-01), mf 3 (2026-09)."""
    return make_client(
        pop={c: 1000.0 for c in disk()},
        permits=[(LAT, LNG, "2026-09-01", "sf", 5), (LAT, LNG, "2024-01-01", "sf", 7), (LAT, LNG, "2026-09-01", "mf", 3)],
    )


def _demand_total(j):
    return sum(r[4] for r in j["hexes"])      # kolumna d = wartość czynnika popytu w samym heksagonie


def test_new_sf_counts_only_window(api_client_with_permits):
    j = api_client_with_permits.get("/api/analyze", params=dict(PARAMS, demand="new_sf", months=24)).json()
    assert _demand_total(j) == pytest.approx(5)
    assert j["permits_period"] == {"from": "2024-10", "to": "2026-09"}


def test_new_all_sums_kinds(api_client_with_permits):
    j = api_client_with_permits.get("/api/analyze", params=dict(PARAMS, demand="new_all", months=24)).json()
    assert _demand_total(j) == pytest.approx(8)


def test_new_mf_counts_only_multifamily(api_client_with_permits):
    j = api_client_with_permits.get("/api/analyze", params=dict(PARAMS, demand="new_mf", months=24)).json()
    assert _demand_total(j) == pytest.approx(3)


def test_window_length_changes_result(api_client_with_permits):
    get = lambda months: api_client_with_permits.get(
        "/api/analyze", params=dict(PARAMS, demand="new_sf", months=months)).json()
    assert _demand_total(get(12)) == pytest.approx(5)
    assert _demand_total(get(36)) == pytest.approx(12)          # okno 36 mies. obejmuje styczeń 2024
    assert get(36)["permits_period"] == {"from": "2023-10", "to": "2026-09"}


def test_census_demand_has_no_permits_period(api_client_with_permits):
    j = api_client_with_permits.get("/api/analyze", params=dict(PARAMS, demand="pop_total")).json()
    assert "permits_period" not in j


def test_analyze_permits_missing_warns(api_client):
    r = api_client.get("/api/analyze", params=dict(PARAMS, demand="new_sf"))
    assert r.status_code == 200
    j = r.json()
    assert j["hexes"] == [] and j["top"] == []
    assert any("pozwoleniach" in w for w in j["warnings"])


def test_analyze_no_permits_in_area_warns_about_demand(make_client):
    # tabela pozwoleń istnieje, ale pozwolenia są daleko od analizowanego obszaru
    client = make_client(pop={c: 1000.0 for c in disk()},
                         permits=[(50.0, 19.9, "2026-09-01", "sf", 4)])
    j = client.get("/api/analyze", params=dict(PARAMS, demand="new_sf")).json()
    assert any("popycie" in w for w in j["warnings"])


def test_percentile_is_computed_over_shown_hexes(make_client):
    """Najgorszy pokazany heksagon ma percentyl 0 — heksagony bez popytu i konkurencji nie zawyżają rang."""
    east = (LAT, LNG + 0.12)      # pozwolenia tylko na wschodnim skraju danych (~8 km od środka)
    client = make_client(pop={c: 1000.0 for c in disk()}, permits=[(*east, "2026-09-01", "sf", 50)])
    j = client.get("/api/analyze", params=dict(type="kindergarten", demand="new_sf", lat=LAT, lng=LNG, radius_km=8)).json()
    assert j["hexes"] and min(r[6] for r in j["hexes"]) == 0 and max(r[6] for r in j["hexes"]) == 100


def test_bandwidth_above_slider_limit_is_rejected(api_client):
    r = api_client.get("/api/analyze", params=dict(type="beauty", demand="pop_f", lat=LAT, lng=LNG, radius_km=3, bandwidth_km=50))
    assert r.status_code == 422

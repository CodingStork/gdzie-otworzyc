import duckdb
import h3
import numpy as np
from fastapi.testclient import TestClient

from backend.app import config
from backend.app.catalog import POOR_WARNING
from backend.app.db import reset_connection
from backend.app.main import app
from tests.conftest import CENTER, disk

PARAMS = dict(type="beauty", demand="pop_f", lat=CENTER[0], lng=CENTER[1], radius_km=3)


def test_analyze_returns_hexes_and_top(api_client):
    j = api_client.get("/api/analyze", params=PARAMS).json()
    assert j["res"] == 8 and len(j["hexes"]) > 10 and 1 <= len(j["top"]) <= 5
    best = max(j["hexes"], key=lambda r: r[1])
    assert best[1] == j["top"][0]["score"]
    assert j["bandwidth_km"] == 1.5
    assert j["stats"]["n_hex"] == len(j["hexes"])
    assert len(j["stats"]["score_breaks"]) >= 1
    h3_id, score, D, S, d, s, pct = j["hexes"][0]
    assert isinstance(h3_id, str) and 0 <= pct <= 100


def test_competitor_lowers_score_nearby(api_client):
    j = api_client.get("/api/analyze", params=dict(PARAMS, radius_km=5)).json()
    by_h3 = {r[0]: r for r in j["hexes"]}
    with_poi = by_h3[h3.latlng_to_cell(52.23, 21.01, 8)]
    far = by_h3[h3.latlng_to_cell(52.23 - 0.03, 21.01 + 0.03, 8)]   # ~3 km dalej, bez konkurentów obok
    assert with_poi[5] == 1 and far[5] == 0           # s = liczba firm w samym heksagonie
    assert with_poi[1] < far[1]                       # konkurent obniża wynik
    assert with_poi[3] > far[3]                       # S w zasięgu większe przy konkurencie


def test_analyze_no_competitors_warns(api_client):
    j = api_client.get("/api/analyze", params=dict(type="paving", demand="pop_total", lat=CENTER[0], lng=CENTER[1],
                                                   radius_km=3)).json()
    assert any("konkurencji" in w for w in j["warnings"]) and POOR_WARNING in j["warnings"]
    assert all(r[3] == 0 and r[1] == r[2] for r in j["hexes"])          # S=0 → score = D
    assert j["stats"]["n_competitors"] == 0 and j["top"]


def test_analyze_half_empty_area(make_client):
    # dane tylko na wschód od środka (symuluje morze/zagranicę na zachodzie)
    center_lng = CENTER[1]
    east = {c: 1000.0 for c in disk() if h3.cell_to_latlng(c)[1] >= center_lng}
    client = make_client(pop=east, pois=[("beauty", 52.23, 21.05)])
    j = client.get("/api/analyze", params=dict(PARAMS, radius_km=6)).json()
    assert j["top"] and all(t["lng"] >= center_lng - 0.01 for t in j["top"])
    # żaden heksagon nie leży tam, gdzie nie ma danych (brak „heksagonów na morzu”)
    assert all(h3.cell_to_latlng(r[0])[1] >= center_lng - 0.01 for r in j["hexes"])


def test_analyze_empty_area_warns_without_error(make_client):
    client = make_client(pop={c: 1000.0 for c in disk((50.0, 19.0), 3)})   # dane tylko pod Krakowem
    j = client.get("/api/analyze", params=dict(PARAMS, radius_km=2)).json()    # pytamy o Warszawę
    assert j["hexes"] == [] and j["top"] == []
    assert any("popycie" in w for w in j["warnings"])


def test_analyze_validation(api_client):
    assert api_client.get("/api/analyze", params=dict(PARAMS, type="xxx")).status_code == 422
    r = api_client.get("/api/analyze", params=dict(PARAMS, lat=40))
    assert r.status_code == 422 and "poza Polską" in r.text
    r = api_client.get("/api/analyze", params=dict(PARAMS, type="xxx"))
    assert "Nieznany typ działalności" in r.text
    r = api_client.get("/api/analyze", params=dict(PARAMS, demand="xxx"))
    assert "Nieznany czynnik popytu" in r.text
    assert api_client.get("/api/analyze", params=dict(PARAMS, radius_km=0.5)).status_code == 422
    assert api_client.get("/api/analyze", params=dict(PARAMS, radius_km=51)).status_code == 422
    assert api_client.get("/api/analyze", params=dict(PARAMS, months=18)).status_code == 422
    no_point = {k: v for k, v in PARAMS.items() if k not in ("lat", "lng")}
    assert api_client.get("/api/analyze", params=no_point).status_code == 422


def test_bandwidth_override_changes_result(api_client):
    a = api_client.get("/api/analyze", params=PARAMS).json()
    b = api_client.get("/api/analyze", params=dict(PARAMS, bandwidth_km=4)).json()
    assert a["bandwidth_km"] == 1.5 and b["bandwidth_km"] == 4
    assert a["hexes"] != b["hexes"]


def test_large_radius_uses_coarser_resolution(api_client):
    j = api_client.get("/api/analyze", params=dict(PARAMS, radius_km=20)).json()
    assert j["res"] == 7


def test_analyze_db_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "nie_ma.duckdb")
    reset_connection()
    r = TestClient(app).get("/api/analyze", params=PARAMS)
    assert r.status_code == 503 and "etl.run_all" in r.text

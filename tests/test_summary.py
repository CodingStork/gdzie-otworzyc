"""Testy v3.1 backendu: podsumowanie obszaru (/api/surface → summary), średnia krajowa, min. zasięg, trend budów."""
import h3
import pytest

from backend.app.analysis.service import _haversine_km
from tests.conftest import CENTER, disk

LAT, LNG = CENTER
POP = {c: 1000.0 for c in disk(k=12)}
FAR = 0.5     # ~55 km na północ: poza każdym okręgiem testów


def surface(client, **kw):
    params = dict(type="beauty", demand="pop_f", lat=LAT, lng=LNG, radius_km=3, reach_km=0.5)
    params.update(kw)
    return client.get("/api/surface", params={k: v for k, v in params.items() if v is not None})


def in_circle_total(radius_km, share=1.0):
    return sum(v for c, v in POP.items() if _haversine_km(LAT, LNG, *h3.cell_to_latlng(c)) <= radius_km) * share


# ---------------------------------------------------------------- podsumowanie ----

def test_summary_counts_and_sources(make_client):
    pois = [("beauty", LAT, LNG), ("beauty", LAT + 0.01, LNG, "overture"), ("beauty", LAT, LNG + 0.01, "overture"),
            ("beauty", LAT + FAR, LNG), ("cafe", LAT, LNG)]
    s = surface(make_client(pop=POP, pois=pois)).json()["summary"]
    assert s["competitors"] == {"total": 3, "osm": 1, "overture": 2}
    assert s["radius_km"] == 3 and s["type_plural"] == "salony kosmetyczne" and s["demand_genitive"] == "kobiet"
    assert s["demand_total"] == pytest.approx(in_circle_total(3, 0.515), rel=0.02)   # haversine vs układ lokalny: kilka komórek na brzegu
    assert s["per_firm"] == pytest.approx(s["demand_total"] / 3, rel=1e-3)


def test_summary_national_average_and_verdict_more(make_client):
    # 10 firm w okręgu i żadnej poza nim: w okręgu jest mniej mieszkańców niż w całym kraju, więc na firmę przypada mniej
    pois = [("beauty", LAT + 0.001 * i, LNG) for i in range(10)]
    s = surface(make_client(pop=POP, pois=pois)).json()["summary"]
    assert s["national_per_firm"] == pytest.approx(len(POP) * 1000 * 0.515 / 10, rel=1e-3)
    assert s["verdict"] == "more"


def test_summary_verdict_less_and_similar(make_client):
    pois = [("beauty", LAT, LNG)] + [("beauty", LAT + FAR, LNG + 0.001 * i) for i in range(20)]
    assert surface(make_client(pop=POP, pois=pois)).json()["summary"]["verdict"] == "less"
    # to samo zagęszczenie w okręgu i w kraju: popyt w okręgu / firmy w okręgu ≈ krajowy → „similar”
    total = len(POP) * 1000
    n_in = round(in_circle_total(3) / total * 40)               # tyle firm w okręgu, ile przypada proporcjonalnie na 40 w kraju
    pois = [("beauty", LAT + 0.0005 * i, LNG) for i in range(n_in)] + \
           [("beauty", LAT + FAR, LNG + 0.001 * i) for i in range(40 - n_in)]
    s = surface(make_client(pop=POP, pois=pois), demand="pop_total").json()["summary"]
    assert s["verdict"] == "similar", s


def test_summary_zero_competitors(make_client):
    s = surface(make_client(pop=POP, pois=[("cafe", LAT, LNG)])).json()["summary"]
    assert s["competitors"] == {"total": 0, "osm": 0, "overture": 0}
    assert s["per_firm"] is None and s["national_per_firm"] is None and s["verdict"] == "less"


def test_summary_only_demand_and_only_type(make_client):
    client = make_client(pop=POP, pois=[("beauty", LAT, LNG)])
    only_demand = surface(client, type="").json()["summary"]
    assert only_demand["demand_total"] > 0 and only_demand["competitors"] is None
    assert only_demand["per_firm"] is None and only_demand["verdict"] is None and only_demand["type_plural"] is None
    only_type = surface(client, demand="").json()["summary"]
    assert only_type["demand_total"] is None and only_type["demand_genitive"] is None
    assert only_type["competitors"]["total"] == 1 and only_type["verdict"] is None


def test_summary_permits_demand(make_client):
    permits = [(LAT, LNG, "2026-09-01", "sf", 5), (LAT + FAR, LNG, "2026-09-01", "sf", 100)]
    client = make_client(pop=POP, pois=[("paving", LAT, LNG)], permits=permits)
    s = surface(client, type="paving", demand="new_sf", radius_km=3, reach_km=2).json()["summary"]
    assert s["demand_total"] == 5 and s["demand_genitive"] == "nowych domów jednorodzinnych"
    assert s["national_per_firm"] == pytest.approx(105 / 1)           # wszystkie pozwolenia w oknie / wszystkie firmy


# ---------------------------------------------------------------- minimalny zasięg ----

def test_reach_below_min_is_raised_with_note(make_client):
    j = surface(make_client(pop=POP, pois=[("beauty", LAT, LNG)]), reach_km=0.1).json()
    assert j["reach_km"] == 0.3
    assert any("300 m" in n for n in j["notes"])


def test_reach_at_min_has_no_note(make_client):
    j = surface(make_client(pop=POP, pois=[("beauty", LAT, LNG)]), reach_km=0.3).json()
    assert j["reach_km"] == 0.3 and not any("300 m" in n for n in j["notes"])


def test_point_reach_below_min(make_client):
    client = make_client(pop=POP, pois=[("beauty", LAT, LNG)])
    j = client.get("/api/point", params=dict(lat=LAT, lng=LNG, type="beauty", demand="pop_f", reach_km=0.1)).json()
    assert j["radius_km"] == 0.3 and any("300 m" in n for n in j["notes"])


# ---------------------------------------------------------------- trend budów ----

def trend_client(make_client):
    """Najnowsze dane: 2026-09. Przy środku przybywa pozwoleń (1 → 9), 3 km na północ bez zmian (5 → 5)."""
    north = LAT + 0.027
    permits = [(LAT, LNG, "2025-03-01", "sf", 1), (LAT, LNG, "2026-03-01", "sf", 9),
               (north, LNG, "2025-03-01", "sf", 5), (north, LNG, "2026-09-01", "sf", 5)]
    return make_client(pop=POP, pois=[("paving", LAT, LNG)], permits=permits)


def test_trend_layer_only_for_permits(make_client):
    client = trend_client(make_client)
    assert surface(client, type="paving", demand="pop_total", reach_km=1).json()["layers"] == ["open", "demand"]
    j = surface(client, type="paving", demand="new_sf", reach_km=1, radius_km=6).json()
    assert j["layers"] == ["open", "demand", "trend"]
    assert surface(client, type="", demand="new_sf", reach_km=1, radius_km=6).json()["layers"] == ["demand", "trend"]


def test_trend_maximum_where_construction_grows(make_client):
    j = surface(trend_client(make_client), type="", demand="new_sf", reach_km=1, radius_km=6).json()
    best = j["top"]["trend"][0]
    assert best["value"] > 0 and abs(best["lat"] - LAT) < 0.01 and abs(best["lng"] - LNG) < 0.02
    assert all(abs(t["lat"] - (LAT + 0.027)) > 0.01 for t in j["top"]["trend"][:1])
    values = [x for x in j["values"]["trend"] if x is not None]
    assert max(values) > 0 and min(values) <= 0                      # na północy nie przybywa (5 → 5): ≈ 0 albo mniej


def test_trend_negative_where_construction_falls(make_client):
    permits = [(LAT, LNG, "2025-03-01", "sf", 9), (LAT, LNG, "2026-03-01", "sf", 1)]
    j = surface(make_client(pop=POP, permits=permits), type="", demand="new_sf", reach_km=1, radius_km=3).json()
    assert min(x for x in j["values"]["trend"] if x is not None) < 0
    assert j["top"]["trend"] == []                                    # top-5 trendu = największy WZROST

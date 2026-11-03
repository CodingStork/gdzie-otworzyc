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
    # 40 firm w okręgu i żadnej poza nim: w okręgu jest mniej mieszkańców niż w całym kraju, więc na firmę przypada mniej
    pois = [("beauty", LAT + 0.0005 * i, LNG) for i in range(40)]
    s = surface(make_client(pop=POP, pois=pois)).json()["summary"]
    assert s["national_per_firm"] == pytest.approx(len(POP) * 1000 * 0.515 / 40, rel=1e-3)
    # baza bez klas gęstości (krok `gaps` nie był liczony): punktem odniesienia jest średnia krajowa
    assert s["benchmark"] == "national"
    assert s["benchmark_firms"] == pytest.approx(s["demand_total"] / s["national_per_firm"], rel=1e-2)
    assert s["benchmark_per_firm"] == pytest.approx(s["national_per_firm"], rel=1e-2)
    assert s["verdict"] == "more"


def test_summary_small_difference_is_not_a_verdict(make_client):
    """8 firm przy ok. 5 oczekiwanych to jeszcze nie „więcej konkurencji” — tyle daje zwykły przypadek (Poisson: ok. 13%).
    Przed audytem ten sam obszar dostawał werdykt „więcej konkurencji niż przeciętnie” (8 > 1,25 · 5)."""
    pois = [("beauty", LAT + 0.001 * i, LNG) for i in range(8)]
    s = surface(make_client(pop=POP, pois=pois)).json()["summary"]
    assert 4 < s["benchmark_firms"] < 6 and s["verdict"] == "similar"


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
    # w całej „Polsce” nie ma żadnego salonu — nie ma z czym porównać, więc nie mówimy „mniej konkurencji”
    s = surface(make_client(pop=POP, pois=[("cafe", LAT, LNG)])).json()["summary"]
    assert s["competitors"] == {"total": 0, "osm": 0, "overture": 0}
    assert s["per_firm"] is None and s["national_per_firm"] is None and s["verdict"] is None


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
    client = make_client(pop=POP, pois=[("diy", LAT, LNG)], permits=permits)
    s = surface(client, type="diy", demand="new_sf", radius_km=3, reach_km=2).json()["summary"]
    assert s["demand_total"] == 5 and s["demand_genitive"] == "nowych domów jednorodzinnych"
    assert s["national_per_firm"] == pytest.approx(105 / 1)           # wszystkie pozwolenia w oknie / wszystkie firmy
    assert s["verdict"] == "few"                                      # 5 / 105 ≈ 0,05 oczekiwanej firmy — nie ma czego oceniać


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
    """Najnowsze dane: 2026-09 (miesiąc niepełny, trend go pomija). Przy środku przybywa pozwoleń (1 → 9), 3 km na północ bez zmian (5 → 5)."""
    north = LAT + 0.027
    permits = [(LAT, LNG, "2025-03-01", "sf", 1), (LAT, LNG, "2026-03-01", "sf", 9),
               (north, LNG, "2025-03-01", "sf", 5), (north, LNG, "2026-08-01", "sf", 5),
               (LAT + FAR, LNG, "2026-09-01", "sf", 1)]       # daleko stąd; wyznacza najnowszy miesiąc danych (2026-09)
    return make_client(pop=POP, pois=[("diy", LAT, LNG)], permits=permits)


def test_trend_layer_only_for_permits(make_client):
    client = trend_client(make_client)
    assert surface(client, type="diy", demand="pop_total", reach_km=1).json()["layers"] == ["open", "demand"]
    j = surface(client, type="diy", demand="new_sf", reach_km=1, radius_km=6).json()
    assert j["layers"] == ["open", "demand", "trend"]
    assert surface(client, type="", demand="new_sf", reach_km=1, radius_km=6).json()["layers"] == ["demand", "trend"]


def test_trend_maximum_where_construction_grows(make_client):
    j = surface(trend_client(make_client), type="", demand="new_sf", reach_km=1, radius_km=6).json()
    best = j["top"]["trend"][0]
    assert best["value"] > 0 and abs(best["lat"] - LAT) < 0.01 and abs(best["lng"] - LNG) < 0.02
    values = [x for x in j["values"]["trend"] if x is not None]
    assert max(values) > 0 and min(values) <= 0                      # na północy nie przybywa (5 → 5): ≈ 0 albo mniej


def test_trend_negative_where_construction_falls(make_client):
    permits = [(LAT, LNG, "2025-03-01", "sf", 9), (LAT, LNG, "2026-03-01", "sf", 1),
               (LAT + FAR, LNG, "2026-09-01", "sf", 1)]          # daleko stąd; wyznacza najnowszy miesiąc danych
    j = surface(make_client(pop=POP, permits=permits), type="", demand="new_sf", reach_km=1, radius_km=3).json()
    assert min(x for x in j["values"]["trend"] if x is not None) < 0
    assert j["top"]["trend"] == []                                    # top-5 trendu = największy WZROST


def test_trend_ignores_incomplete_newest_month(make_client):
    """Najnowszy miesiąc w danych jest zwykle niepełny (dane z bieżącego miesiąca) — liczony jako pełny zaniżałby trend."""
    permits = [(LAT, LNG, "2025-03-01", "sf", 1), (LAT, LNG, "2026-03-01", "sf", 1),
               (LAT, LNG, "2026-09-01", "sf", 50)]            # 50 pozwoleń w ostatnim (niepełnym) miesiącu
    j = surface(make_client(pop=POP, permits=permits), type="", demand="new_sf", reach_km=1, radius_km=3).json()
    assert j["top"]["trend"] == []                            # 1 → 1: bez zmian, a nie „+50”


def test_verdict_without_national_average_is_none(make_client):
    """Brak danych o pozwoleniach w kraju: nie ma z czym porównać, więc nie ma też werdyktu „mniej konkurencji”."""
    s = surface(make_client(pop=POP, pois=[("diy", LAT, LNG)]), type="diy", demand="new_sf",
                reach_km=2).json()["summary"]
    assert s["competitors"]["total"] == 1 and s["national_per_firm"] is None and s["verdict"] is None


def test_top_names_use_street_labels(make_client):
    # siatka ulic co ~100 m pokrywa cały obszar, więc każde miejsce z top-5 ma ulicę w promieniu 150 m
    streets = [(f"Prosta {i}x{j}", LAT + i * 0.001, LNG + j * 0.0015) for i in range(-30, 31) for j in range(-30, 31)]
    client = make_client(pop=POP, pois=[("beauty", LAT, LNG)], streets=streets)
    names = [t["name"] for t in surface(client).json()["top"]["open"]]
    assert names and all(n.startswith("ul. Prosta ") for n in names)


# ---------------------------------------------------------------- werdykt: małe liczby i podobne miejsca ----

def test_verdict_rules():
    from backend.app.analysis.service import verdict
    assert verdict(0, None) is None
    assert verdict(0, 2.5) == "few"                       # poniżej 3 oczekiwanych firm nie oceniamy
    assert verdict(1, 4) == "less"                        # P(X ≤ 1 | 4) ≈ 9%
    assert verdict(2, 4) == "similar"                     # P(X ≤ 2 | 4) ≈ 24% — zwykły przypadek
    assert verdict(36, 49) == "less"                      # P ≈ 3%, 36 ≤ 0,8 · 49
    assert verdict(10, 7) == "similar"                    # P(X ≥ 10 | 7) ≈ 17%
    assert verdict(40, 28) == "more"                      # P ≈ 2%, 40 ≥ 1,25 · 28
    assert verdict(45, 49) == "similar"                   # różnica za mała, choć liczby duże


TOWN = (52.23, 21.01)
COUNTRYSIDE = (51.0, 18.0)


def _town_and_countryside(make_client, gaps):
    """Gęste miasteczko (127 tys. mieszkańców, 60 salonów) i rzadko zaludniona wieś daleko stąd (63 tys., bez salonów)."""
    pop = {c: 1000.0 for c in disk(TOWN, k=6)} | {c: 50.0 for c in disk(COUNTRYSIDE, k=20)}
    pois = [("beauty", TOWN[0] + (i % 10 - 4.5) * 0.002, TOWN[1] + (i // 10 - 2.5) * 0.003) for i in range(60)]
    return make_client(pop=pop, pois=pois, gaps=gaps)


def test_summary_compares_with_similar_places_not_national_average(make_client):
    """Miasto, które ma tyle salonów, co typowe miasto, NIE jest „więcej konkurencji” — tylko tak wychodziło przy średniej
    krajowej, bo zaniżają ją wsie (ich mieszkańcy korzystają z salonów w mieście)."""
    params = dict(lat=TOWN[0], lng=TOWN[1], radius_km=3)
    national = surface(_town_and_countryside(make_client, gaps=False), **params).json()["summary"]
    assert national["benchmark"] == "national" and national["verdict"] == "more"
    similar = surface(_town_and_countryside(make_client, gaps=True), **params).json()["summary"]
    assert similar["benchmark"] == "similar_places"
    assert similar["benchmark_firms"] == pytest.approx(60, rel=0.15) and similar["verdict"] == "similar"
    assert similar["benchmark_per_firm"] == pytest.approx(similar["demand_total"] / similar["benchmark_firms"], rel=1e-2)


def test_summary_type_only_gets_verdict_from_similar_places(make_client):
    s = surface(_town_and_countryside(make_client, gaps=True), demand="", lat=TOWN[0], lng=TOWN[1]).json()["summary"]
    assert s["benchmark"] == "similar_places" and s["verdict"] == "similar" and s["per_firm"] is None


def test_summary_names_the_place_of_a_circle(make_client):
    """„Obszar: Brzeg, promień 3 km” zamiast „punkt na mapie” — miasto w okręgu ma pierwszeństwo przed bliższym osiedlem."""
    places = [("Miasteczko", "town", LAT + 0.012, LNG), ("Osiedle", "suburb", LAT - 0.003, LNG)]   # 1,3 km i 0,33 km
    s = surface(make_client(pop=POP, pois=[("beauty", LAT, LNG)], places=places)).json()["summary"]
    assert s["place_name"] == "Miasteczko"


def test_summary_names_village_when_no_town_in_circle(make_client):
    places = [("Wioska", "village", LAT + 0.003, LNG)]
    assert surface(make_client(pop=POP, pois=[("beauty", LAT, LNG)], places=places)).json()["summary"]["place_name"] == "Wioska"

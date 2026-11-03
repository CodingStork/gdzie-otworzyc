from fastapi.testclient import TestClient

from backend.app.catalog import (
    ALL_TYPES, DEMANDS, GROUPS, HIDDEN_TYPES, MEDIUM_WARNING, TYPE_ALIASES, TYPES, catalog_json, match_types,
)
from backend.app.main import app


def test_catalog_counts():
    assert len(TYPES) == 10 and len(DEMANDS) == 9
    assert all(t.suggested_demands[0] in DEMANDS for t in TYPES.values())
    assert all(d in DEMANDS for t in TYPES.values() for d in t.suggested_demands)
    assert {t.group for t in TYPES.values()} == {g for g, _ in GROUPS}


def test_craftsmen_are_hidden_from_catalog():
    """Rzemieślnicy (praca u klienta) nie mają w otwartych danych firm — nie pokazujemy dla nich „konkurencji”."""
    removed = {"paving", "garden", "windows", "kitchen", "installer"}
    assert not removed & set(TYPES) and removed | {"nails"} == set(HIDDEN_TYPES)
    assert removed <= set(ALL_TYPES)
    ids = {t["id"] for g in catalog_json()["groups"] for t in g["types"]}
    assert not removed & ids


def test_every_type_has_known_demands_and_group_is_not_empty():
    assert all(set(t.suggested_demands) <= set(DEMANDS) and t.suggested_demands for t in TYPES.values())
    assert all(any(t.group == g for t in TYPES.values()) for g, _ in GROUPS)


def test_osm_quality_matches_completeness_analysis():
    """docs/kompletnosc-danych.md: sklepy, gastronomia, salony — dobre; barber/paznokcie/tatuaż/fitness — średnie."""
    good = {"hairdresser", "beauty", "grocery", "restaurant", "kindergarten", "cafe", "diy"}
    assert {t.id for t in TYPES.values() if t.osm_quality == "good"} == good
    assert {t.id for t in TYPES.values() if t.osm_quality == "medium"} == {"barber", "tattoo", "fitness"}
    assert not any(t.osm_quality == "poor" for t in TYPES.values())


def test_demand_definitions():
    assert DEMANDS["pop_f"].column == "pop_f" and DEMANDS["pop_f"].source == "census"
    assert DEMANDS["new_sf"].source == "permits" and DEMANDS["new_sf"].kinds == ("sf",)
    assert DEMANDS["new_all"].kinds == ("sf", "mf") and DEMANDS["new_all"].needs_months
    assert not DEMANDS["pop_total"].needs_months


def test_match_barber_is_also_hairdresser():
    assert set(match_types({"shop": "hairdresser", "hairdresser": "barber"})) == {"hairdresser", "barber"}


def test_match_requires_all_tags():
    assert match_types({"shop": "trade"}) == []
    assert match_types({"shop": "trade", "trade": "building_supplies"}) == ["diy"]


def test_match_fitness_sports_centre():
    assert match_types({"leisure": "sports_centre", "sport": "fitness"}) == ["fitness"]
    assert match_types({"leisure": "sports_centre", "sport": "soccer"}) == []


def test_match_semicolon_separated_values():
    # w OSM wartość może być listą rozdzieloną średnikami
    assert match_types({"leisure": "sports_centre", "sport": "yoga;fitness"}) == ["fitness"]


def test_match_returns_types_in_catalog_order_without_duplicates():
    got = match_types({"shop": "beauty", "beauty": "nails"})
    assert got == ["beauty", "nails"]
    assert match_types({"amenity": "bench"}) == []


def test_match_alternative_rules():
    assert match_types({"craft": "paver"}) == ["paving"]
    assert match_types({"craft": "stonemason"}) == ["paving"]
    assert match_types({"shop": "barber"}) == ["barber"]


def test_api_catalog():
    j = TestClient(app).get("/api/catalog").json()
    beauty = next(t for g in j["groups"] for t in g["types"] if t["id"] == "beauty")
    assert beauty["default_demand"] == "pop_f" and beauty["bandwidth_km"] == 1.5
    assert beauty["warning"] is None
    barber = next(t for g in j["groups"] for t in g["types"] if t["id"] == "barber")
    assert barber["warning"] == MEDIUM_WARNING
    assert j["months_options"] == [12, 24, 36] and j["default_months"] == 24
    assert len(j["demands"]) == 9 and len(j["groups"]) == 2
    assert sum(len(g["types"]) for g in j["groups"]) == 10
    assert j["aliases"] == {"nails": "beauty"}


def test_catalog_json_is_serializable_function():
    assert catalog_json()["groups"][0]["id"] == "personal"


def test_every_type_has_plural_name():
    j = catalog_json()
    types = [t for g in j["groups"] for t in g["types"]]
    assert all(t["plural"] for t in types) and next(t for t in types if t["id"] == "hairdresser")["plural"] == "fryzjerzy"


def test_every_demand_has_genitive_for_summary_sentences():
    assert all(d.genitive for d in DEMANDS.values())
    assert DEMANDS["pop_f"].genitive == "kobiet" and DEMANDS["new_sf"].genitive == "nowych domów jednorodzinnych"
    assert {d["id"]: d["genitive"] for d in catalog_json()["demands"]}["pop_ge65"] == "seniorów"


def test_nails_merged_into_beauty():
    """Audyt: każdy „salon paznokci” w danych jest też salonem kosmetycznym (OSM shop=beauty, Overture nail_salon),
    a osobny typ pomijał salony kosmetyczne robiące manicure — więc typ zniknął z katalogu, a stare linki prowadzą do salonu."""
    assert "nails" not in TYPES and "nails" in HIDDEN_TYPES and TYPE_ALIASES["nails"] == "beauty"
    assert "nail_salon" in TYPES["beauty"].overture
    assert "beauty" in match_types({"shop": "beauty", "beauty": "nails"})


def test_old_nails_link_is_served_as_beauty(api_client):
    j = api_client.get("/api/surface", params=dict(type="nails", demand="pop_f", lat=52.23, lng=21.01,
                                                   radius_km=2, reach_km=1.5)).json()
    assert j["summary"]["type_plural"] == "salony kosmetyczne"


def test_caveats_are_short_sentences_for_risky_types():
    """Typy, w których mapa czegoś ważnego nie widzi, mają jedno zdanie zastrzeżenia (pokazywane pod wyborem branży)."""
    for type_id in ("cafe", "restaurant", "grocery", "diy", "kindergarten", "barber", "tattoo"):
        caveat = TYPES[type_id].caveat
        assert caveat and caveat.endswith(".") and len(caveat) < 260
    j = catalog_json()
    assert next(t for g in j["groups"] for t in g["types"] if t["id"] == "cafe")["caveat"] == TYPES["cafe"].caveat


def test_diy_default_demand_is_residents():
    """Rejestr pozwoleń liczy blok jak jeden dom, więc „nowe budynki” zaniżałyby popyt z osiedli bloków — domyślnie mieszkańcy."""
    assert TYPES["diy"].suggested_demands[0] == "pop_total"

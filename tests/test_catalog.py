from fastapi.testclient import TestClient

from backend.app.catalog import DEMANDS, GROUPS, POOR_WARNING, TYPES, catalog_json, match_types
from backend.app.main import app


def test_catalog_counts():
    assert len(TYPES) == 16 and len(DEMANDS) == 9
    assert all(t.suggested_demands[0] in DEMANDS for t in TYPES.values())
    assert all(d in DEMANDS for t in TYPES.values() for d in t.suggested_demands)
    assert {t.group for t in TYPES.values()} == {g for g, _ in GROUPS}


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
    paving = next(t for g in j["groups"] for t in g["types"] if t["id"] == "paving")
    assert paving["warning"] == POOR_WARNING
    assert j["months_options"] == [12, 24, 36] and j["default_months"] == 24
    assert len(j["demands"]) == 9 and len(j["groups"]) == 3
    assert sum(len(g["types"]) for g in j["groups"]) == 16


def test_catalog_json_is_serializable_function():
    assert catalog_json()["groups"][0]["id"] == "personal"

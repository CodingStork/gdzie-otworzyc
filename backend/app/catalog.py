"""Katalog: typy działalności (konkurencja z OSM) i czynniki popytu.

To jedyne źródło prawdy — korzysta z niego ETL (reguły tagów OSM → typ) i API (lista
w interfejsie). Kody PKD (2007) są przygotowane pod późniejszą integrację z CEIDG.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class TagRule:
    """Reguła dopasowania obiektu OSM: WSZYSTKIE pary klucz=wartość muszą pasować ("*" = dowolna wartość)."""
    tags: dict[str, str]


@dataclass(frozen=True)
class Demand:
    """Czynnik popytu: kolumna ze spisu ludności albo liczba nowych budów z pozwoleń GUNB."""
    id: str
    name: str
    source: Literal["census", "permits"]
    column: str | None        # kolumna tabeli hex_pop_* (tylko dla census)
    kinds: tuple[str, ...]    # rodzaje budynków w permits: "sf" (jednorodzinny), "mf" (wielorodzinny)
    needs_months: bool        # czy w UI pokazać wybór okresu 12/24/36 miesięcy


@dataclass(frozen=True)
class BusinessType:
    id: str
    group: str
    name: str
    rules: tuple[TagRule, ...]            # obiekt pasuje, gdy pasuje DOWOLNA reguła
    pkd: str                              # kod PKD 2007 (pod przyszłe CEIDG)
    suggested_demands: tuple[str, ...]    # pierwszy = domyślny
    bandwidth_km: float                   # domyślny zasięg klienta h (szerokość pasma jądra)
    osm_quality: Literal["good", "medium", "poor"]  # na ile kompletne są dane OSM dla tej branży


GROUPS: tuple[tuple[str, str], ...] = (
    ("personal", "Usługi osobiste"),
    ("construction", "Budowlanka / dom"),
    ("retail", "Handel / gastro / sport"),
)

POOR_WARNING = "Dane o firmach tego typu w OpenStreetMap są bardzo niepełne. Traktuj mapę głównie jako mapę popytu."
MONTHS_OPTIONS = (12, 24, 36)
DEFAULT_MONTHS = 24


def _census(id: str, name: str, column: str) -> Demand:
    return Demand(id, name, "census", column, (), False)


def _permits(id: str, name: str, kinds: tuple[str, ...]) -> Demand:
    return Demand(id, name, "permits", None, kinds, True)


DEMANDS: dict[str, Demand] = {d.id: d for d in (
    _census("pop_total", "Mieszkańcy", "pop_total"),
    _census("pop_f", "Kobiety", "pop_f"),
    _census("pop_m", "Mężczyźni", "pop_m"),
    _census("pop_lt15", "Dzieci (<15 lat)", "pop_lt15"),
    _census("pop_1564", "Osoby 15–64 lata", "pop_1564"),
    _census("pop_ge65", "Seniorzy (65+)", "pop_ge65"),
    _permits("new_sf", "Nowe domy jednorodzinne", ("sf",)),
    _permits("new_mf", "Nowe bloki (wielorodzinne)", ("mf",)),
    _permits("new_all", "Wszystkie nowe budynki mieszkalne", ("sf", "mf")),
)}


def _rules(*tag_dicts: dict[str, str]) -> tuple[TagRule, ...]:
    return tuple(TagRule(t) for t in tag_dicts)


def _type(id, group, name, rules, pkd, demands, bandwidth_km, quality) -> BusinessType:
    return BusinessType(id, group, name, rules, pkd, tuple(demands), bandwidth_km, quality)


TYPES: dict[str, BusinessType] = {t.id: t for t in (
    # --- Usługi osobiste ---
    _type("hairdresser", "personal", "Fryzjer", _rules({"shop": "hairdresser"}), "96.02.Z",
          ("pop_total", "pop_f", "pop_1564"), 1.5, "medium"),
    _type("barber", "personal", "Barber",
          _rules({"shop": "hairdresser", "hairdresser": "barber"}, {"shop": "hairdresser", "male": "yes"},
                 {"shop": "barber"}),
          "96.02.Z", ("pop_m", "pop_total", "pop_1564"), 2, "poor"),
    _type("beauty", "personal", "Salon kosmetyczny", _rules({"shop": "beauty"}), "96.02.Z",
          ("pop_f", "pop_total", "pop_1564"), 1.5, "medium"),
    _type("nails", "personal", "Stylizacja paznokci",
          _rules({"shop": "beauty", "beauty": "nails"}, {"shop": "nails"}), "96.02.Z",
          ("pop_f", "pop_total"), 1.5, "poor"),
    _type("tattoo", "personal", "Studio tatuażu", _rules({"shop": "tattoo"}), "96.09.Z",
          ("pop_1564", "pop_total"), 5, "medium"),
    # --- Budowlanka / dom ---
    _type("paving", "construction", "Brukarstwo", _rules({"craft": "paver"}, {"craft": "stonemason"}), "43.99.Z",
          ("new_sf", "new_all", "pop_total"), 15, "poor"),
    _type("garden", "construction", "Ogrody i zieleń", _rules({"craft": "gardener"}, {"shop": "garden_centre"}),
          "81.30.Z", ("new_sf", "new_all", "pop_total"), 15, "poor"),
    _type("windows", "construction", "Okna i drzwi",
          _rules({"shop": "windows"}, {"shop": "doors"}, {"craft": "window_construction"}), "43.32.Z",
          ("new_all", "new_sf", "pop_total"), 15, "poor"),
    _type("diy", "construction", "Market / hurtownia budowlana",
          _rules({"shop": "doityourself"}, {"shop": "hardware"}, {"shop": "trade", "trade": "building_supplies"}),
          "47.52.Z", ("new_all", "new_sf", "pop_total"), 15, "good"),
    _type("kitchen", "construction", "Meble kuchenne / stolarz",
          _rules({"shop": "kitchen"}, {"craft": "carpenter"}, {"craft": "joiner"}), "31.02.Z",
          ("new_all", "new_sf", "pop_total"), 10, "poor"),
    _type("installer", "construction", "Instalatorzy (hydraulik, elektryk)",
          _rules({"craft": "plumber"}, {"craft": "electrician"}, {"craft": "hvac"}), "43.22.Z",
          ("new_all", "new_sf", "pop_total"), 10, "poor"),
    # --- Handel / gastro / sport ---
    _type("grocery", "retail", "Sklep spożywczy", _rules({"shop": "convenience"}, {"shop": "supermarket"}),
          "47.11.Z", ("pop_total", "pop_ge65"), 1, "good"),
    _type("cafe", "retail", "Kawiarnia", _rules({"amenity": "cafe"}), "56.30.Z",
          ("pop_1564", "pop_total"), 1.5, "good"),
    _type("restaurant", "retail", "Restauracja / fast food",
          _rules({"amenity": "restaurant"}, {"amenity": "fast_food"}), "56.10.A",
          ("pop_total", "pop_1564"), 2, "good"),
    _type("fitness", "retail", "Siłownia / fitness",
          _rules({"leisure": "fitness_centre"}, {"leisure": "sports_centre", "sport": "fitness"}), "93.13.Z",
          ("pop_1564", "pop_total"), 3, "medium"),
    _type("kindergarten", "retail", "Przedszkole / żłobek",
          _rules({"amenity": "kindergarten"}, {"amenity": "childcare"}), "85.10.Z",
          ("pop_lt15", "new_sf", "new_all"), 2, "good"),
)}


def _tag_matches(tags: Mapping[str, str], key: str, wanted: str) -> bool:
    if key not in tags:
        return False
    if wanted == "*":
        return True
    # w OSM wartość bywa listą rozdzielaną średnikami (np. sport=yoga;fitness)
    return wanted in [v.strip() for v in tags[key].split(";")]


def match_types(tags: Mapping[str, str]) -> list[str]:
    """Zwraca id typów działalności pasujących do tagów obiektu OSM (w kolejności katalogu)."""
    return [
        t.id for t in TYPES.values()
        if any(all(_tag_matches(tags, k, v) for k, v in rule.tags.items()) for rule in t.rules)
    ]


def catalog_json() -> dict:
    """Katalog w formie przesyłanej do przeglądarki (GET /api/catalog)."""
    groups = []
    for group_id, group_name in GROUPS:
        types = [
            {
                "id": t.id,
                "name": t.name,
                "default_demand": t.suggested_demands[0],
                "suggested_demands": list(t.suggested_demands),
                "bandwidth_km": t.bandwidth_km,
                "osm_quality": t.osm_quality,
                "warning": POOR_WARNING if t.osm_quality == "poor" else None,
            }
            for t in TYPES.values() if t.group == group_id
        ]
        groups.append({"id": group_id, "name": group_name, "types": types})
    demands = [
        {"id": d.id, "name": d.name, "source": d.source, "needs_months": d.needs_months}
        for d in DEMANDS.values()
    ]
    return {
        "groups": groups,
        "demands": demands,
        "months_options": list(MONTHS_OPTIONS),
        "default_months": DEFAULT_MONTHS,
    }

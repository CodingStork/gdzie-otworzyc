"""Katalog: typy działalności (konkurencja z OSM i Overture Maps) i czynniki popytu.

To jedyne źródło prawdy — korzysta z niego ETL (reguły tagów OSM i kategorie Overture → typ) i API (lista
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
    genitive: str             # dopełniacz liczby mnogiej do zdań typu „1 firma na ok. 260 {kobiet}”


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
    overture: tuple[str, ...] = ()        # kategorie Overture Maps (`taxonomy.primary`) liczone do tego typu


# Grupa „Budowlanka / dom” zniknęła razem z rzemieślnikami (patrz HIDDEN_TYPES) — został w niej tylko market budowlany,
# który jest zwykłym handlem z lokalem, więc przeniesiono go do „Handel / gastro / sport”.
GROUPS: tuple[tuple[str, str], ...] = (
    ("personal", "Usługi osobiste"),
    ("retail", "Handel / gastro / sport"),
)

POOR_WARNING = "Dane o firmach tego typu (OpenStreetMap, Overture Maps) są bardzo niepełne. Traktuj mapę głównie jako mapę popytu."
MEDIUM_WARNING = "Dane o tych firmach są niepełne — część firm może nie być widoczna."


def quality_warning(quality: str) -> str | None:
    """Ostrzeżenie o kompletności danych o firmach: „poor” — mocne, „medium” — łagodne, „good” — brak."""
    return POOR_WARNING if quality == "poor" else MEDIUM_WARNING if quality == "medium" else None


MONTHS_OPTIONS = (12, 24, 36)
DEFAULT_MONTHS = 24


def _census(id: str, name: str, column: str, genitive: str) -> Demand:
    return Demand(id, name, "census", column, (), False, genitive)


def _permits(id: str, name: str, kinds: tuple[str, ...], genitive: str) -> Demand:
    return Demand(id, name, "permits", None, kinds, True, genitive)


DEMANDS: dict[str, Demand] = {d.id: d for d in (
    _census("pop_total", "Mieszkańcy", "pop_total", "mieszkańców"),
    _census("pop_f", "Kobiety", "pop_f", "kobiet"),
    _census("pop_m", "Mężczyźni", "pop_m", "mężczyzn"),
    _census("pop_lt15", "Dzieci (<15 lat)", "pop_lt15", "dzieci"),
    _census("pop_1564", "Osoby 15–64 lata", "pop_1564", "osób w wieku 15–64 lata"),
    _census("pop_ge65", "Seniorzy (65+)", "pop_ge65", "seniorów"),
    _permits("new_sf", "Nowe domy jednorodzinne", ("sf",), "nowych domów jednorodzinnych"),
    _permits("new_mf", "Nowe bloki (wielorodzinne)", ("mf",), "nowych budynków wielorodzinnych"),
    _permits("new_all", "Wszystkie nowe budynki mieszkalne", ("sf", "mf"), "nowych budynków mieszkalnych"),
)}


def _rules(*tag_dicts: dict[str, str]) -> tuple[TagRule, ...]:
    return tuple(TagRule(t) for t in tag_dicts)


def _type(id, group, name, rules, pkd, demands, bandwidth_km, quality, overture=()) -> BusinessType:
    return BusinessType(id, group, name, rules, pkd, tuple(demands), bandwidth_km, quality, tuple(overture))


# Restauracje i bary szybkiej obsługi w taksonomii Overture to dziesiątki osobnych kategorii kuchni.
_RESTAURANTS = (
    "restaurant", "pizza_restaurant", "fast_food_restaurant", "polish_restaurant", "italian_restaurant",
    "doner_kebab_restaurant", "sushi_restaurant", "burger_restaurant", "diner", "turkish_restaurant",
    "asian_restaurant", "buffet_restaurant", "european_restaurant", "barbecue_restaurant", "chinese_restaurant",
    "indian_restaurant", "japanese_restaurant", "vietnamese_restaurant", "american_restaurant",
    "bar_and_grill_restaurant", "seafood_restaurant", "breakfast_and_brunch_restaurant", "sandwich_shop",
    "chicken_restaurant", "vegetarian_restaurant", "thai_restaurant", "eastern_european_restaurant",
    "steakhouse", "mexican_restaurant", "greek_restaurant", "korean_restaurant", "hot_dog_restaurant",
)


TYPES: dict[str, BusinessType] = {t.id: t for t in (
    # --- Usługi osobiste ---
    _type("hairdresser", "personal", "Fryzjer", _rules({"shop": "hairdresser"}), "96.02.Z",
          ("pop_total", "pop_f", "pop_1564"), 1.5, "good",
          overture=("hair_salon", "barber", "hair_stylist")),
    _type("barber", "personal", "Barber",
          _rules({"shop": "hairdresser", "hairdresser": "barber"}, {"shop": "hairdresser", "male": "yes"},
                 {"shop": "barber"}),
          "96.02.Z", ("pop_m", "pop_total", "pop_1564"), 2, "medium",
          overture=("barber",)),
    _type("beauty", "personal", "Salon kosmetyczny", _rules({"shop": "beauty"}), "96.02.Z",
          ("pop_f", "pop_total", "pop_1564"), 1.5, "good",
          overture=("beauty_salon", "skin_care_and_makeup", "nail_salon")),
    _type("nails", "personal", "Stylizacja paznokci",
          _rules({"shop": "beauty", "beauty": "nails"}, {"shop": "nails"}), "96.02.Z",
          ("pop_f", "pop_total"), 1.5, "medium",
          overture=("nail_salon",)),
    _type("tattoo", "personal", "Studio tatuażu", _rules({"shop": "tattoo"}), "96.09.Z",
          ("pop_1564", "pop_total"), 5, "medium",
          overture=("tattoo_and_piercing",)),
    # --- Handel / gastro / sport ---
    _type("diy", "retail", "Market / hurtownia budowlana",
          _rules({"shop": "doityourself"}, {"shop": "hardware"}, {"shop": "trade", "trade": "building_supplies"}),
          "47.52.Z", ("new_all", "new_sf", "pop_total"), 15, "good",
          overture=("building_supply_store", "hardware_store", "home_improvement_store", "hardware_home_and_garden_store")),
    _type("grocery", "retail", "Sklep spożywczy", _rules({"shop": "convenience"}, {"shop": "supermarket"}),
          "47.11.Z", ("pop_total", "pop_ge65"), 1, "good",
          overture=("grocery_store", "convenience_store", "supermarket", "organic_grocery_store")),
    _type("cafe", "retail", "Kawiarnia", _rules({"amenity": "cafe"}), "56.30.Z",
          ("pop_1564", "pop_total"), 1.5, "good",
          overture=("cafe", "coffee_shop")),
    _type("restaurant", "retail", "Restauracja / fast food",
          _rules({"amenity": "restaurant"}, {"amenity": "fast_food"}), "56.10.A",
          ("pop_total", "pop_1564"), 2, "good",
          overture=_RESTAURANTS),
    _type("fitness", "retail", "Siłownia / fitness",
          _rules({"leisure": "fitness_centre"}, {"leisure": "sports_centre", "sport": "fitness"}), "93.13.Z",
          ("pop_1564", "pop_total"), 3, "medium",
          overture=("gym", "yoga_studio", "pilates_studio")),
    _type("kindergarten", "retail", "Przedszkole / żłobek",
          _rules({"amenity": "kindergarten"}, {"amenity": "childcare"}), "85.10.Z",
          ("pop_lt15", "new_sf", "new_all"), 2, "good",
          overture=("preschool", "day_care_preschool", "child_care_and_day_care", "kindergarten")),
)}


# Firmy pracujące u klienta (brukarz, ogrodnik, instalator, okna, kuchnie) prawie nie mają lokali, więc w OSM i Overture
# jest ich o rząd wielkości mniej niż w rzeczywistości (docs/kompletnosc-danych.md). Pokazywanie „konkurencji” dla nich
# wprowadzałoby w błąd, dlatego NIE trafiają do TYPES ani do /api/catalog. ETL nadal je zbiera do tabeli `poi`
# (match_types / match_overture sięgają po ALL_TYPES) — przydadzą się po dołączeniu CEIDG (M9). Popyt „nowe domy”
# jest nadal dostępny w interfejsie jako samodzielny czynnik („Twoi klienci to”).
HIDDEN_TYPES: dict[str, BusinessType] = {t.id: t for t in (
    _type("paving", "construction", "Brukarstwo", _rules({"craft": "paver"}, {"craft": "stonemason"}), "43.99.Z",
          ("new_sf", "new_all", "pop_total"), 15, "poor",
          overture=("paving_contractor", "masonry_concrete")),
    _type("garden", "construction", "Ogrody i zieleń", _rules({"craft": "gardener"}, {"shop": "garden_centre"}),
          "81.30.Z", ("new_sf", "new_all", "pop_total"), 15, "poor",
          overture=("gardener", "landscaping", "nursery_and_gardening_store")),
    _type("windows", "construction", "Okna i drzwi",
          _rules({"shop": "windows"}, {"shop": "doors"}, {"craft": "window_construction"}), "43.32.Z",
          ("new_all", "new_sf", "pop_total"), 15, "poor",
          overture=("window_supplier", "door_supplier", "windows_installation", "door_sales_service")),
    _type("kitchen", "construction", "Meble kuchenne / stolarz",
          _rules({"shop": "kitchen"}, {"craft": "carpenter"}, {"craft": "joiner"}), "31.02.Z",
          ("new_all", "new_sf", "pop_total"), 10, "poor",
          overture=("carpenter", "cabinetry", "kitchen_and_bath_store")),
    _type("installer", "construction", "Instalatorzy (hydraulik, elektryk)",
          _rules({"craft": "plumber"}, {"craft": "electrician"}, {"craft": "hvac"}), "43.22.Z",
          ("new_all", "new_sf", "pop_total"), 10, "poor",
          overture=("plumbing", "electrician", "hvac_service")),
)}

ALL_TYPES: dict[str, BusinessType] = {**TYPES, **HIDDEN_TYPES}


# Nazwy typów w liczbie mnogiej, mianownik — do podpisów „Gdzie są {firmy}” (np. „Gdzie są fryzjerzy”).
PLURALS: dict[str, str] = {
    "hairdresser": "fryzjerzy", "barber": "barberzy", "beauty": "salony kosmetyczne",
    "nails": "salony stylizacji paznokci", "tattoo": "studia tatuażu", "paving": "firmy brukarskie",
    "garden": "firmy ogrodnicze", "windows": "sklepy z oknami i drzwiami", "diy": "markety budowlane",
    "kitchen": "stolarze i studia kuchenne", "installer": "instalatorzy", "grocery": "sklepy spożywcze",
    "cafe": "kawiarnie", "restaurant": "restauracje i bary szybkiej obsługi", "fitness": "siłownie",
    "kindergarten": "przedszkola i żłobki",
}


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
        t.id for t in ALL_TYPES.values()
        if any(all(_tag_matches(tags, k, v) for k, v in rule.tags.items()) for rule in t.rules)
    ]


def match_overture(category: str | None) -> list[str]:
    """Id typów działalności, do których należy kategoria Overture (`taxonomy.primary`), w kolejności katalogu."""
    return [t.id for t in ALL_TYPES.values() if category in t.overture]


def catalog_json() -> dict:
    """Katalog w formie przesyłanej do przeglądarki (GET /api/catalog)."""
    groups = []
    for group_id, group_name in GROUPS:
        types = [
            {
                "id": t.id,
                "name": t.name,
                "plural": PLURALS[t.id],
                "default_demand": t.suggested_demands[0],
                "suggested_demands": list(t.suggested_demands),
                "bandwidth_km": t.bandwidth_km,
                "osm_quality": t.osm_quality,
                "warning": quality_warning(t.osm_quality),
            }
            for t in TYPES.values() if t.group == group_id
        ]
        groups.append({"id": group_id, "name": group_name, "types": types})
    demands = [
        {"id": d.id, "name": d.name, "source": d.source, "needs_months": d.needs_months, "genitive": d.genitive}
        for d in DEMANDS.values()
    ]
    return {
        "groups": groups,
        "demands": demands,
        "months_options": list(MONTHS_OPTIONS),
        "default_months": DEFAULT_MONTHS,
    }

"""Budynki mieszkalne z OpenStreetMap → wagi do rozłożenia ludności (metoda dasymetryczna).

Spis ludności (Eurostat) podaje liczbę mieszkańców w kwadratach 1 km × 1 km. Wiemy więc, że w kwadracie
mieszka np. 1000 osób, ale nie wiemy GDZIE w jego obrębie — może w jednym osiedlu, a reszta to las.
METODA DASYMETRYCZNA (dasymetric mapping) rozkłada te liczby nierównomiernie, proporcjonalnie do
„wagi mieszkalnej” miejsc w kwadracie. Jako wagę bierzemy ważoną powierzchnię użytkową budynków:

    waga budynku = powierzchnia rzutu [m²] × liczba kondygnacji × współczynnik typu budynku

Powierzchnia × kondygnacje przybliża powierzchnię użytkową (większy dom = więcej mieszkańców),
a współczynnik typu odsiewa budynki niemieszkalne (garaże, stodoły) i obniża wagę budynków
o nieznanym przeznaczeniu (`building=yes` — w Polsce to w większości domy, ale też szopy).
Ograniczenie: to wciąż szacunek — nie znamy faktycznej liczby mieszkań w budynku.
"""
from collections.abc import Mapping

import duckdb
import h3
import numpy as np
import osmium
import pandas as pd
from pyproj import Transformer

# Budynki w pełni mieszkalne (współczynnik 1,0).
RESIDENTIAL = {"house", "detached", "semidetached_house", "terrace", "bungalow",
               "residential", "apartments", "farm", "dormitory"}
UNKNOWN_FACTOR = 0.5                                   # building=yes: nie wiadomo, czy ktoś tam mieszka
DEFAULT_LEVELS = {"apartments": 5, "residential": 2}  # brak tagu building:levels → typowa liczba kondygnacji
MIN_AREA_M2 = 20                                       # mniejsze rzuty to szopy, kiosk, altany
MAX_LEVELS = 40
CHUNK = 1_000_000                                      # tyle budynków trzymamy naraz w listach Pythona


def building_factor(tag: str) -> float:
    """Współczynnik typu budynku: 1,0 mieszkalny, 0,5 nieokreślony (`yes`), 0 pozostałe."""
    if tag in RESIDENTIAL:
        return 1.0
    if tag == "yes":
        return UNKNOWN_FACTOR
    return 0.0


def levels(tags: Mapping[str, str], building: str) -> int:
    """Liczba kondygnacji z `building:levels` (np. "2.5" → 2), przycięta do 1–40; śmieci → wartość domyślna."""
    default = DEFAULT_LEVELS.get(building, 1)
    try:
        n = int(float(tags["building:levels"]))
    except (KeyError, ValueError, OverflowError):   # brak tagu, tekst, "inf"
        return default
    return min(max(n, 1), MAX_LEVELS)


def polygon_area_m2(coords: list[tuple[float, float]]) -> float:
    """Pole wielokąta [m²] wzorem Gaussa (shoelace) w lokalnym rzucie równoodległościowym.

    `coords` to (lat, lng). Stopnie zamieniamy na metry wokół środka budynku:
    1° szerokości ≈ 110 540 m, 1° długości ≈ 111 320 m · cos(szerokość). Dla obiektu wielkości
    budynku błąd takiego uproszczenia jest pomijalny.
    """
    lat0 = sum(c[0] for c in coords) / len(coords)
    kx = 111_320 * np.cos(np.radians(lat0))
    xs = [c[1] * kx for c in coords]
    ys = [c[0] * 110_540 for c in coords]
    area2 = sum(xs[i] * ys[(i + 1) % len(xs)] - xs[(i + 1) % len(xs)] * ys[i] for i in range(len(xs)))
    return abs(area2) / 2


def extract_buildings(pbf_path) -> pd.DataFrame:
    """Czyta budynki (tylko drogi/ways) z PBF → ramka `lat, lng, w` z wagą > 0.

    Relacje (budynki-multipoligony) pomijamy; środek budynku to średnia jego wierzchołków.
    """
    chunks, lat, lng, w = [], [], [], []

    def flush():
        if lat:
            chunks.append(pd.DataFrame({"lat": lat.copy(), "lng": lng.copy(), "w": w.copy()}))
            lat.clear(), lng.clear(), w.clear()

    processor = (osmium.FileProcessor(str(pbf_path), osmium.osm.NODE | osmium.osm.WAY)
                 .with_locations()
                 .with_filter(osmium.filter.KeyFilter("building")))
    for way in processor:
        if not way.is_way():
            continue                                  # węzeł z tagiem building nie ma obrysu
        building = way.tags.get("building")
        factor = building_factor(building)
        if factor == 0.0:
            continue                                  # tanie odrzucenie przed liczeniem geometrii
        pts = [(n.location.lat, n.location.lon) for n in way.nodes if n.location.valid()]
        if len(pts) > 1 and way.nodes[0].ref == way.nodes[-1].ref:
            pts = pts[:-1]                            # zamknięty obrys: ostatni punkt powtarza pierwszy
        if len(pts) < 3:
            continue
        area = polygon_area_m2(pts)
        if area < MIN_AREA_M2:
            continue
        tags = {t.k: t.v for t in way.tags}
        lat.append(sum(p[0] for p in pts) / len(pts))
        lng.append(sum(p[1] for p in pts) / len(pts))
        w.append(area * levels(tags, building) * factor)
        if len(lat) >= CHUNK:
            flush()
    flush()
    if not chunks:
        return pd.DataFrame({"lat": [], "lng": [], "w": []}, dtype=float)
    return pd.concat(chunks, ignore_index=True)


def build_building_weights(pbf_path, con: duckdb.DuckDBPyConnection) -> int:
    """Tabela building_weights(cell_e, cell_n, h3, w): suma wag budynków w parze (komórka spisu, heksagon res 9).

    Komórka spisu to kwadrat 1 km w EPSG:3035, identyfikowany lewym dolnym rogiem — tak samo jak
    w `population.py`, dzięki czemu wagi łatwo dopasować do komórek ludności.
    """
    df = extract_buildings(pbf_path)
    to_3035 = Transformer.from_crs(4326, 3035, always_xy=True)
    x, y = to_3035.transform(df["lng"].to_numpy(), df["lat"].to_numpy())
    df["cell_e"] = (np.floor(np.asarray(x) / 1000) * 1000).astype("int64")
    df["cell_n"] = (np.floor(np.asarray(y) / 1000) * 1000).astype("int64")
    df["h3"] = [h3.latlng_to_cell(la, lo, 9) for la, lo in zip(df["lat"], df["lng"])]
    out = df.groupby(["cell_e", "cell_n", "h3"], as_index=False)["w"].sum()
    print(f"building_weights: {len(df):,} budynków, suma wag {df['w'].sum():,.0f}, {len(out):,} wierszy", flush=True)

    con.register("weights_df", out)
    con.execute("""CREATE OR REPLACE TABLE building_weights AS
                   SELECT CAST(cell_e AS INTEGER) AS cell_e, CAST(cell_n AS INTEGER) AS cell_n, h3, w FROM weights_df""")
    con.unregister("weights_df")
    return len(out)

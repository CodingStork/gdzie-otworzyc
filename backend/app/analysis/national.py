"""Tryb „Cała Polska” (`/api/national`): gotowa mapa policzona w ETL (tabele `national_r5 … r8`, patrz `etl/national.py`).

Odpowiedź ma kształt zbliżony do `/api/surface` (`layers`, `grid`, `values`, `top`, `notes`, `warnings`), więc frontend rysuje ją
tym samym kodem mgły. Różnice: siatka jest prostokątna i równa w rzucie Mercatora (tak jak mapa na ekranie — obraz przylega do kafelków),
a skala kolorów (`scale`) jest STAŁA dla całego kraju (percentyle z `national_meta`), niezależna od tego, co widać w kadrze.
"""
import functools
import math

import h3
import numpy as np
from scipy.spatial import cKDTree

from backend.app.analysis.layers import is_trend, layers_for
from backend.app.analysis.service import _haversine_km, _permit_window, _period
from backend.app.analysis.surface import top_points
from backend.app.catalog import DEFAULT_MONTHS, TYPES, quality_warning
from backend.app.db import DatabaseMissing, cursor, on_reset
from etl.aggregate import table_exists

PX_RANGE = (200, 4000)
GRID_CELL_PX = 4              # komórka siatki odpowiedzi ma ok. 4 px ekranu
TARGET_CELL_PX = 4            # wybieramy najgrubszą rozdzielczość H3, której komórki mają co najwyżej tyle pikseli
MAX_CELLS = 60_000            # tyle komórek H3 najwyżej czytamy z bazy na jedno zapytanie
RESOLUTIONS = (5, 6, 7, 8)    # od najgrubszej
LAT_LIMITS = (48.5, 55.5)
LNG_LIMITS = (13.5, 24.5)
TOP_NAME_MAX_KM = 8           # w dużym widoku nazwą miejsca jest najbliższa miejscowość nawet z kilku km
NATIONAL_MISSING_MESSAGE = "Gotowa mapa Polski nie została jeszcze policzona. Uruchom: uv run python -m etl.run_all --only national"
GAPS_NOTE = ("Największe wartości bywają skutkiem luk w danych o firmach (miejsca bez wpisów w OpenStreetMap i Overture Maps) — "
             "zanim ruszysz z inwestycją, sprawdź konkurencję na miejscu.")
NO_LAYER_NOTE = "Dla tego wyboru nie ma gotowej mapy Polski — przybliż mapę, a policzymy ją na żywo."


# Nazwa miejsca w dużym widoku: najbliższa miejscowość, ale większa „przyciąga” mocniej (odległość dzielimy przez wagę) —
# punkt przy rynku miasteczka ma nazywać się jak ono, a nie jak wieś oddalona o 3 km (w `service.nearest_place_name`
# wygrywa rodzaj miejsca, co dla małego okręgu jest dobre, a dla widoku kraju dawało wsie zamiast miast).
PLACE_WEIGHT = {"city": 3.0, "town": 2.0, "suburb": 1.0, "village": 1.0, "neighbourhood": 1.0, "quarter": 1.0, "hamlet": 0.5}


def place_name(con, lat: float, lng: float, max_km: float = TOP_NAME_MAX_KM, check_table: bool = True) -> str | None:
    if check_table and not table_exists(con, "places"):
        return None
    d = max_km / 110.0
    rows = con.execute("SELECT name, kind, lat, lng FROM places WHERE lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?",
                       [lat - d, lat + d, lng - d * 1.7, lng + d * 1.7]).fetchall()
    best = None
    for name, kind, plat, plng in rows:
        dist = _haversine_km(lat, lng, plat, plng)
        if dist <= max_km and (best is None or dist / PLACE_WEIGHT.get(kind, 1.0) < best[0]):
            best = (dist / PLACE_WEIGHT.get(kind, 1.0), name)
    return best[1] if best else None


class NationalMissing(Exception):
    """Brak tabel gotowej mapy Polski — trzeba uruchomić krok ETL `national`."""


def _merc_y(lat) -> np.ndarray:
    """Współrzędna pionowa w rzucie Mercatora (radiany) — mapa Leaflet jest w tym rzucie."""
    return np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))


def _merc_lat(y) -> np.ndarray:
    return np.degrees(2 * np.arctan(np.exp(y)) - np.pi / 2)


def _spacing_km(res: int) -> float:
    """Odległość między środkami sąsiednich komórek H3 (heksagon: √3 · długość krawędzi)."""
    return h3.average_hexagon_edge_length(res, unit="km") * math.sqrt(3)


def choose_resolution(width_km: float, height_km: float, px: int) -> int:
    """Najgrubsza rozdzielczość, której komórki mają ≤ 4 px na ekranie (gładko, a mało punktów); nigdy więcej niż ~60 tys. komórek."""
    km_per_px = width_km / px
    res = next((r for r in RESOLUTIONS if _spacing_km(r) / km_per_px <= TARGET_CELL_PX), RESOLUTIONS[-1])
    while res > RESOLUTIONS[0] and width_km * height_km / h3.average_hexagon_area(res, unit="km^2") > MAX_CELLS:
        res -= 1
    return res


def _scale_json(layer: str, p5, p99):
    if p99 is None:
        return None
    if is_trend(layer):
        return {"max": float(p99)}
    return {"lo": float(max(p5, p99 / 100)), "hi": float(p99)}     # jak logScale w frontendzie: najwyżej 2 rzędy wielkości


_tables_ok = [False]          # sprawdzenie istnienia tabel kosztuje kilka ms — robimy je raz na otwarcie bazy
on_reset(lambda: _tables_ok.__setitem__(0, False))


def _read_meta(con) -> dict:
    if not _tables_ok[0]:
        if not (table_exists(con, "national_meta") and all(table_exists(con, f"national_r{r}") for r in RESOLUTIONS)):
            raise NationalMissing()
        _tables_ok[0] = True
    return {layer: (p5, p99, reach) for layer, p5, p99, reach in
            con.execute("SELECT layer, p5, p99, reach_km FROM national_meta").fetchall()}


def run_national(con, type_id, demand_id, west, south, east, north, px) -> dict:
    meta = _read_meta(con)
    wanted, reach_km = layers_for(type_id, demand_id)
    layers = {logical: column for logical, column in wanted.items() if column in meta}
    notes, warnings = [], []
    if len(layers) < len(wanted) or (type_id and demand_id and "open" not in layers):
        notes.append(NO_LAYER_NOTE)          # np. czynnik spoza zalecanych dla branży: „Gdzie otworzyć” liczy tylko tryb na żywo
    if type_id and quality_warning(TYPES[type_id].osm_quality):
        warnings.append(quality_warning(TYPES[type_id].osm_quality))
    if "open" in layers or "competition" in layers:
        notes.append(GAPS_NOTE)
    if layers:
        notes.append(f"Mapa Polski policzona dla typowego zasięgu: {str(f'{reach_km:g}').replace('.', ',')} km. "
                     "Przybliż, by zobaczyć Twoje ustawienia.")

    # Siatka odpowiedzi: równa w Mercatorze, komórki ~4 px.
    mid_lat = (south + north) / 2
    width_km = (east - west) * 111.32 * math.cos(math.radians(mid_lat))
    height_km = (north - south) * 110.54
    res = choose_resolution(width_km, height_km, px)
    nx = max(1, math.ceil(px / GRID_CELL_PX))
    y_north, y_south = float(_merc_y(north)), float(_merc_y(south))
    cell_y = math.radians(east - west) / nx                          # komórka kwadratowa w rzucie Mercatora
    ny = max(1, round((y_north - y_south) / cell_y))
    while nx * ny > MAX_CELLS:                                       # wąski, wysoki widok: rzadsza siatka
        nx, ny = max(1, nx // 2), max(1, ny // 2)
        cell_y = math.radians(east - west) / nx
    grid = {"west": west, "east": east, "south": south, "north": north, "nx": nx, "ny": ny,
            "cell_m": (east - west) / nx * 111_320 * math.cos(math.radians(mid_lat)), "projection": "mercator"}
    response = {"mode": "national", "layers": list(layers), "reach_km": reach_km, "resolution": res, "grid": grid,
                "values": {}, "scale": {}, "top": {}, "notes": notes, "warnings": warnings}
    if not layers:
        return response

    spacing = _spacing_km(res)
    pad_lat, pad_lng = spacing / 110.54, spacing / (111.32 * math.cos(math.radians(mid_lat)))
    columns = list(layers.values())
    sql = ", ".join(f'"{c}"' for c in columns)
    rows = con.execute(f"SELECT lat, lng, {sql} FROM national_r{res} WHERE lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?",
                       [south - pad_lat, north + pad_lat, west - pad_lng, east + pad_lng]).fetchall()
    data = np.array(rows, dtype=float).reshape(-1, 2 + len(columns))
    lat, lng = data[:, 0], data[:, 1]
    gx = np.floor((lng - west) / (east - west) * nx).astype(int)
    gy = np.floor((y_north - _merc_y(lat)) / cell_y).astype(int)
    inside = (gx >= 0) & (gx < nx) & (gy >= 0) & (gy < ny)

    # środki komórek siatki (do wypełnienia dziur, gdy komórki H3 są większe niż komórki siatki)
    centers_lng = west + (np.arange(nx) + 0.5) / nx * (east - west)
    centers_lat = _merc_lat(y_north - (np.arange(ny) + 0.5) * cell_y)
    km_x = lambda lng_: (lng_ - west) * 111.32 * math.cos(math.radians(mid_lat))
    km_y = lambda lat_: (lat_ - south) * 110.54
    cx, cy = np.meshgrid(km_x(centers_lng), km_y(centers_lat))
    tree = cKDTree(np.column_stack([km_x(lng), km_y(lat)])) if len(data) else None

    has_places = table_exists(con, "places")
    in_view = (lat >= south) & (lat <= north) & (lng >= west) & (lng <= east)
    min_sep_m = width_km * 1000 / 6                                   # top-5 nie z jednego rejonu: odstęp ≥ 1/6 szerokości widoku
    for k, (logical, column) in enumerate(layers.items()):
        v = data[:, 2 + k]
        cells = np.full(nx * ny, np.nan)
        if inside.any():
            idx = gy[inside] * nx + gx[inside]
            vals = v[inside]
            order = np.argsort(np.abs(vals), kind="stable")           # przy kilku komórkach H3 w jednej komórce siatki wygrywa największa
            cells[idx[order]] = vals[order]
        empty = np.flatnonzero(np.isnan(cells))
        if tree is not None and len(empty):
            dist, near = tree.query(np.column_stack([cx.ravel()[empty], cy.ravel()[empty]]), distance_upper_bound=0.58 * spacing)
            hit = np.isfinite(dist)
            cells[empty[hit]] = v[near[hit]]
        response["values"][logical] = [None if np.isnan(x) else float(x) for x in cells]
        response["scale"][logical] = _scale_json(column, *meta[column][:2])

        xy = np.column_stack([km_x(lng), km_y(lat)]) * 1000
        picks = top_points(np.nan_to_num(v), xy, in_view, min_sep_m)
        response["top"][logical] = [
            {"lat": float(lat[i]), "lng": float(lng[i]), "value": float(v[i]),
             "name": (place_name(con, float(lat[i]), float(lng[i]), check_table=False) if has_places else None) or f"okolice {lat[i]:.2f}, {lng[i]:.2f}"}
            for i in picks]
    if any("__new_" in c or c.startswith("trend__") for c in columns):          # warstwy z pozwoleń: podajemy okres danych
        window = _permit_window(con, 5, DEFAULT_MONTHS)
        if window is not None:
            response["permits_period"] = _period(window)
    return response


def _quantum(span_deg: float) -> float:
    """Krok zaokrąglania granic widoku (potęga dwójki, ok. 1/16–1/32 szerokości), żeby sąsiednie przesunięcia mapy trafiały w cache."""
    return 2.0 ** math.floor(math.log2(max(span_deg, 1e-4) / 16))


@functools.lru_cache(maxsize=64)
def _cached(type_id, demand_id, west, south, east, north, px) -> dict:
    return run_national(cursor(), type_id, demand_id, west, south, east, north, px)


def cached_national(type_id, demand_id, west, south, east, north, px) -> dict:
    """run_national z pamięcią podręczną (LRU 64); granice widoku zaokrąglone na zewnątrz do siatki, px do wielokrotności 250."""
    west, east = max(west, LNG_LIMITS[0]), min(east, LNG_LIMITS[1])
    south, north = max(south, LAT_LIMITS[0]), min(north, LAT_LIMITS[1])
    if not (west < east and south < north):
        return run_national(cursor(), type_id, demand_id, LNG_LIMITS[0], LAT_LIMITS[0], LNG_LIMITS[0] + 0.01, LAT_LIMITS[0] + 0.01, px)
    q = _quantum(max(east - west, north - south))
    west, south = math.floor(west / q) * q, math.floor(south / q) * q
    east, north = math.ceil(east / q) * q, math.ceil(north / q) * q
    px = min(PX_RANGE[1], max(PX_RANGE[0], round(px / 250) * 250))
    return _cached(type_id, demand_id, west, south, east, north, px)


on_reset(_cached.cache_clear)

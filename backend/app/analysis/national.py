"""Tryb „Cała Polska” (`/api/national`): gotowa mapa policzona w ETL (tabele `national_r5 … r8`, patrz `etl/national.py`).

Odpowiedź ma kształt zbliżony do `/api/surface` (`layers`, `grid`, `values`, `top`, `notes`, `warnings`), więc frontend rysuje ją
tym samym kodem mgły. Różnice: siatka jest prostokątna i równa w rzucie Mercatora (tak jak mapa na ekranie — obraz przylega do kafelków),
a skala kolorów (`scale`) jest STAŁA dla całego kraju (percentyle z `national_meta`), niezależna od tego, co widać w kadrze.
"""
import dataclasses
import functools
import math

import h3
import numpy as np
from scipy.spatial import cKDTree

from backend.app.analysis.layers import is_trend, layer_months, layers_for, rel_layer
from backend.app.analysis.kernel import LocalFrame
from backend.app.analysis.service import SurfaceParams, _box, _permit_window, _period, area_summary, place_name
from backend.app.analysis.surface import top_points
from backend.app.catalog import DEFAULT_MONTHS, GAP_SHARE, TYPES, quality_warning
from backend.app.db import DatabaseMissing, cursor, on_reset
from etl.aggregate import table_exists

PX_RANGE = (200, 4000)       # szerokość mapy w px poza zakresem jest przycinana (nie jest błędem)
BASE_RES = 8
GRID_CELL_PX = 4              # komórka siatki odpowiedzi ma ok. 4 px ekranu
TARGET_CELL_PX = 4            # wybieramy najgrubszą rozdzielczość H3, której komórki mają co najwyżej tyle pikseli
MAX_CELLS = 60_000            # tyle komórek H3 najwyżej czytamy z bazy na jedno zapytanie
RESOLUTIONS = (5, 6, 7, 8)    # od najgrubszej
LAT_LIMITS = (48.5, 55.5)
LNG_LIMITS = (13.5, 24.5)
MIN_SCALE_RATIO = 10          # skala kolorów obejmuje co najmniej 10-krotną różnicę (jak MIN_RATIO w colors.js)
TOP_NAME_MAX_KM = 8           # w dużym widoku nazwą miejsca jest najbliższa miejscowość nawet z kilku km
NATIONAL_MISSING_MESSAGE = "Gotowa mapa Polski nie została jeszcze policzona. Uruchom: uv run python -m etl.run_all --only national"
NO_LAYER_NOTE = "Dla tego wyboru nie ma gotowej mapy Polski — przybliż mapę, a policzymy ją na żywo."


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
    # Jak logScale we frontendzie: skala obejmuje najwyżej 2 rzędy wielkości (inaczej wszystko byłoby czerwone) i NAJMNIEJ jeden
    # (audyt: przy wąskim zakresie, np. 310–600, różnica 20% wyglądała jak przepaść między bielą a czerwienią).
    return {"lo": float(min(max(p5, p99 / 100), p99 / MIN_SCALE_RATIO)), "hi": float(p99)}


_available: list[set | None] = [None]    # warstwy obecne we WSZYSTKICH poziomach piramidy; liczone raz na otwarcie bazy
on_reset(lambda: _available.__setitem__(0, None))


def _read_meta(con) -> dict:
    """national_meta jako {warstwa: (p5, p99, zasięg)}, tylko dla warstw, które mają kolumnę w każdej tabeli national_r5…r8
    (przerwany ETL mógł zapisać warstwę w res 8, a nie zdążyć zbudować piramidy — wtedy zapytanie o res 5–7 kończyłoby się błędem)."""
    if _available[0] is None:
        if not (table_exists(con, "national_meta") and all(table_exists(con, f"national_r{r}") for r in RESOLUTIONS)):
            raise NationalMissing()
        per_table = [{row[0] for row in con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?", [f"national_r{r}"]).fetchall()}
            for r in RESOLUTIONS]
        _available[0] = set.intersection(*per_table)
    return {layer: (p5, p99, reach) for layer, p5, p99, reach in
            con.execute("SELECT layer, p5, p99, reach_km FROM national_meta").fetchall() if layer in _available[0]}


def _best_cell_position(con, res: int, column: str, value_column: str, lat: float, lng: float, spacing_km: float,
                        value: float) -> tuple[float, float, float]:
    """Położenie i wartość najlepszej komórki res 8 w komórce res < 8 (piramida trzyma środek komórki-rodzica, a wartość to max dzieci,
    więc pinezka stawiana w środku rodzica mogłaby leżeć kilka km od faktycznie najlepszego miejsca; res 5: ~17 km między środkami).

    „Najlepsza” = największa `column` (dla „Gdzie otworzyć” są to wiarygodni klienci), a podawana wartość to `value_column` w TEJ komórce —
    inaczej pod nazwą rejonu stałaby liczba z innej (np. podejrzanej) komórki. Na res 8 zwraca to, co dostała."""
    if res >= BASE_RES:
        return lat, lng, value
    d = spacing_km / 110.54 * 0.6
    row = con.execute(f'SELECT lat, lng, "{value_column}" FROM national_r{BASE_RES} WHERE lat BETWEEN ? AND ? AND lng BETWEEN ? AND ? '
                      f'ORDER BY "{column}" DESC LIMIT 1', [lat - d, lat + d, lng - d * 1.7, lng + d * 1.7]).fetchone()
    return (float(row[0]), float(row[1]), float(row[2])) if row else (lat, lng, value)


def run_national(con, type_id, demand_id, west, south, east, north, px, with_top: bool = True) -> dict:
    meta = _read_meta(con)
    wanted, reach_km = layers_for(type_id, demand_id)
    layers = {logical: column for logical, column in wanted.items() if column in meta}
    notes, warnings = [], []
    if len(layers) < len(wanted) or (type_id and demand_id and "open" not in layers):
        notes.append(NO_LAYER_NOTE)          # np. czynnik spoza zalecanych dla branży: „Gdzie otworzyć” liczy tylko tryb na żywo
    if type_id and quality_warning(TYPES[type_id].osm_quality):
        warnings.append(quality_warning(TYPES[type_id].osm_quality))
    rel_column = rel_layer(*layers["open"].split("__")[1:]) if "open" in layers else None
    if rel_column is not None and rel_column not in meta:
        rel_column = None                       # stara baza bez warstw „wiarygodni klienci” — mapa jak w v3.2, bez kreskowania
    # Audyt (szum): notatki „szare kreskowanie…” i „mapa policzona dla typowego zasięgu…” dublowały pytajnik w legendzie
    # i podpowiedź pod suwakiem zasięgu, więc ich tu nie ma. W `notes` zostaje tylko to, czego interfejs inaczej nie powie.

    # Siatka odpowiedzi: równa w Mercatorze, komórki ~4 px.
    mid_lat = (south + north) / 2
    width_km = (east - west) * 111.32 * math.cos(math.radians(mid_lat))
    height_km = (north - south) * 110.54
    res = choose_resolution(width_km, height_km, px)
    nx = max(1, math.ceil(px / GRID_CELL_PX))
    y_north, y_south = float(_merc_y(north)), float(_merc_y(south))
    cell_y = math.radians(east - west) / nx                          # komórka kwadratowa w rzucie Mercatora
    ny = max(1, round((y_north - y_south) / cell_y))
    if nx * ny > MAX_CELLS:                                          # bardzo duży ekran: komórki siatki większe niż 4 px, ale nie więcej niż trzeba
        nx = max(1, int(nx * math.sqrt(MAX_CELLS / (nx * ny))))
        cell_y = math.radians(east - west) / nx
        ny = max(1, round((y_north - y_south) / cell_y))
        while nx * ny > MAX_CELLS and nx > 1:
            nx -= 1
            cell_y = math.radians(east - west) / nx
            ny = max(1, round((y_north - y_south) / cell_y))
    grid_south = float(_merc_lat(y_north - ny * cell_y))             # ny to liczba całkowita wierszy, więc dolna krawędź obrazu leży tu
    grid = {"west": west, "east": east, "south": grid_south, "north": north, "nx": nx, "ny": ny,
            "cell_m": (east - west) / nx * 111_320 * math.cos(math.radians(mid_lat)), "projection": "mercator"}
    response = {"mode": "national", "layers": list(layers), "reach_km": reach_km, "resolution": res, "grid": grid,
                "values": {}, "scale": {}, "top": {}, "notes": notes, "warnings": warnings,
                "layer_reach_km": {logical: float(meta[column][2]) for logical, column in layers.items()}}
    if not layers:
        return response

    spacing = _spacing_km(res)
    pad_lat, pad_lng = spacing / 110.54, spacing / (111.32 * math.cos(math.radians(mid_lat)))
    columns = list(layers.values()) + ([rel_column] if rel_column else [])
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
    def to_grid(v: np.ndarray) -> np.ndarray:
        """Wartości komórek H3 → komórki siatki odpowiedzi (NaN = brak danych)."""
        cells = np.full(nx * ny, np.nan)
        if inside.any():
            idx = gy[inside] * nx + gx[inside]
            vals = v[inside]
            order = np.argsort(np.abs(vals), kind="stable")           # przy kilku komórkach H3 w jednej komórce siatki wygrywa największa
            cells[idx[order]] = vals[order]
        empty = np.flatnonzero(np.isnan(cells))
        if tree is not None and len(empty):
            dist, near = tree.query(np.column_stack([cx.ravel()[empty], cy.ravel()[empty]]), distance_upper_bound=0.62 * spacing)
            hit = np.isfinite(dist)
            cells[empty[hit]] = v[near[hit]]
        return cells

    xy = np.column_stack([km_x(lng), km_y(lat)]) * 1000
    for k, (logical, column) in enumerate(layers.items()):
        v = data[:, 2 + k]
        cells = to_grid(v)
        response["values"][logical] = [None if np.isnan(x) else float(x) for x in cells]
        response["scale"][logical] = _scale_json(column, *meta[column][:2])

        score, order_column = v, column                   # czym porządkujemy najlepsze miejsca (wartość podajemy zawsze z `column`)
        if logical == "open" and rel_column:
            order_column = rel_column
            rel = data[:, -1]
            # Luka: mniej niż połowa klientów jest wiarygodna (rel < (1 − GAP_SHARE) · E). Dla res < 8 to porównanie maksimów komórek-dzieci.
            gap_cell = rel < (1 - GAP_SHARE) * v
            rel_grid = to_grid(rel)
            open_grid = cells
            gap = np.where(np.isnan(open_grid), np.nan, (rel_grid < (1 - GAP_SHARE) * open_grid).astype(float))
            response["gap"] = {"open": [None if np.isnan(x) else int(x) for x in gap]}
            score = np.where(gap_cell, 0.0, rel)          # miejsca w luce nie trafiają do najlepszych; kolejność wg wiarygodnych klientów
        picks = top_points(np.nan_to_num(score), xy, in_view, min_sep_m) if with_top else []
        top = []
        for i in picks:
            plat, plng, shown = _best_cell_position(con, res, order_column, column,
                                                    float(lat[i]), float(lng[i]), spacing, float(v[i]))
            top.append({"lat": plat, "lng": plng, "value": shown,
                        "name": (place_name(con, plat, plng, max_km=TOP_NAME_MAX_KM, check_table=False) if has_places else None) or f"okolice {plat:.2f}, {plng:.2f}"})
        response["top"][logical] = top
    if any(layer_months(c) for c in columns):                                    # warstwy z pozwoleń: podajemy okres danych
        window = _permit_window(con, 5, DEFAULT_MONTHS)
        if window is not None:
            response["permits_period"] = _period(window)
    return response


def clamp_px(px: int) -> int:
    return min(PX_RANGE[1], max(PX_RANGE[0], round(px / 250) * 250))


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
    px = clamp_px(px)
    return _cached(type_id, demand_id, west, south, east, north, px)


on_reset(_cached.cache_clear)


# ---------------------------------------------------------------- duży obszar (v3.6) ----
# Okrąg „20% ekranu” przy oddalonej mapie ma promień kilkudziesięciu–kilkuset km (np. całe województwo). Liczenie Huffa na żywo
# dla takiego obszaru trwałoby minuty, więc wartości bierzemy z gotowej mapy Polski (ETL `national`, typowy zasięg branży)
# i przycinamy do obszaru, a podsumowanie liczymy tak samo jak dla małego obszaru (z grubszych komórek H3).

BIG_AREA_RES = 7              # komórki popytu do podsumowania dużego obszaru (~5 km² — przy setkach km błąd brzegu jest pomijalny)
BIG_NO_LAYER_NOTE = ("Dla tego wyboru nie ma gotowej mapy dużych obszarów — zaznacz obszar do 30 km promienia "
                     "(albo 60 km boku), a policzymy go z Twoimi ustawieniami.")


def big_area_note(reach_km: float) -> str:
    return (f"Duży obszar: mapa jest policzona wcześniej dla typowego zasięgu ({str(f'{reach_km:g}').replace('.', ',')} km) "
            "i 24 miesięcy pozwoleń. Zaznacz obszar do 30 km promienia, żeby użyć swoich ustawień i zobaczyć najlepsze miejsca.")


def _cell_centers(grid: dict) -> tuple[np.ndarray, np.ndarray]:
    """Środki komórek siatki odpowiedzi (wiersze od północy, siatka równa w rzucie Mercatora) — (lat, lng) każdej komórki."""
    nx, ny = grid["nx"], grid["ny"]
    y_north, y_south = float(_merc_y(grid["north"])), float(_merc_y(grid["south"]))
    lats = _merc_lat(y_north - (np.arange(ny) + 0.5) * (y_north - y_south) / ny)
    lngs = grid["west"] + (np.arange(nx) + 0.5) / nx * (grid["east"] - grid["west"])
    lng_grid, lat_grid = np.meshgrid(lngs, lats)
    return lat_grid.ravel(), lng_grid.ravel()


def run_area(con, p: SurfaceParams, px: int) -> dict:
    """Odpowiedź /api/surface dla DUŻEGO obszaru: gotowa mapa Polski w prostokącie obejmującym obszar, poza okręgiem pusto,
    plus podsumowanie obszaru. Bez najlepszych miejsc (audyt: na dużym obszarze ranking mieszałby miasta ze wsiami,
    dla których model zawyża wynik) — notatka mówi, jak je zobaczyć."""
    frame = LocalFrame(p.lat, p.lng)
    rect = None
    if p.bbox:
        west, south, east, north = p.bbox
        corners = frame.to_metric(np.array([south, south, north, north]), np.array([west, east, west, east]))
        rect = (*corners.min(axis=0), *corners.max(axis=0))
        q = dataclasses.replace(p, radius_km=float(np.hypot(*np.abs(corners).max(axis=0))) / 1000)   # okrąg opisany
    else:
        south, north, west, east = _box(p.lat, p.lng, p.radius_km)
        q = p
    response = run_national(con, p.type_id, p.demand_id, west, south, east, north, px, with_top=False)
    if rect is None and response["values"]:
        # Poza okręgiem nie pokazujemy wartości (podsumowanie i tak liczy tylko okrąg).
        lat, lng = _cell_centers(response["grid"])
        outside = np.hypot(*frame.to_metric(lat, lng).T) > p.radius_km * 1000
        for key in ("values", "gap"):
            for layer, cells in response.get(key, {}).items():
                response[key][layer] = [None if out else v for v, out in zip(cells, outside)]
    notes = [n for n in response["notes"] if n != NO_LAYER_NOTE]
    if len(notes) < len(response["notes"]):
        notes.insert(0, BIG_NO_LAYER_NOTE)
    if response["layers"]:
        notes.append(big_area_note(response["reach_km"]))
    response.update(notes=notes, top={}, area="big",
                    summary=area_summary(con, q, frame, rect, res=BIG_AREA_RES))
    return response


@functools.lru_cache(maxsize=16)
def _cached_area(key: SurfaceParams, px: int) -> dict:
    return run_area(cursor(), key, px)


def cached_area(p: SurfaceParams, px: int) -> dict:
    """run_area z pamięcią podręczną (LRU 16); miejsce zaokrąglone do ~10 m, promień do 0,5 km, px do wielokrotności 250."""
    key = dataclasses.replace(p, lat=round(p.lat, 4), lng=round(p.lng, 4), radius_km=round(p.radius_km * 2) / 2,
                              reach_km=round(p.reach_km, 1), bbox=tuple(round(v, 4) for v in p.bbox) if p.bbox else None)
    return _cached_area(key, clamp_px(px))


on_reset(_cached_area.cache_clear)

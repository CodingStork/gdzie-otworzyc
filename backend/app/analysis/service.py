"""Serwis analizy v3: mapa okolicy wybranego miejsca (`run_surface`) i szczegóły klikniętego punktu.

Przepływ `run_surface` (spec v3 §3):
  1. siatka w EPSG:2180 pokrywająca okrąg o promieniu „promień obszaru” wokół miejsca,
  2. źródła popytu (komórki H3 z ludnością albo pozwoleniami) i konkurenci (firmy z OSM),
  3. wartości na siatce: „Gdzie otworzyć” (model Huffa), „Gdzie są klienci”, „Gdzie są firmy”,
  4. top-5 maksimów w okręgu (z odstępem), nazwy najbliższych miejscowości.
"""
import datetime
import functools
import math
import re
from dataclasses import dataclass

import duckdb
import h3
import numpy as np

from backend.app.analysis.kernel import LocalFrame
from backend.app.analysis.surface import (
    competition_density, demand_potential, huff_and_potential, make_grid, top_points,
)
from backend.app.catalog import DEMANDS, PLURALS, POOR_WARNING, TYPES
from backend.app.db import DatabaseMissing, cursor, on_reset
from etl.aggregate import table_exists

NO_COMPETITORS_WARNING = (
    "Nie znaleziono konkurencji w OpenStreetMap ani w Overture Maps w tym obszarze — wynik pokazuje sam popyt."
)
PERMITS_MISSING_WARNING = "Dane o pozwoleniach nie zostały jeszcze zaimportowane."
MIN_REACH_KM = 0.3                # dane o ludności mają rozdzielczość ok. 300 m (komórka H3 res 9)
MIN_REACH_NOTE = "Dane o mieszkańcach mają rozdzielczość ok. 300 m — mniejszy zasięg nie dodaje informacji."
PERMITS_MIN_REACH_KM = 1.0        # lokalizacja pozwoleń to środek obrębu — dokładniej nie da się zliczać
PERMITS_NOTE = ("Lokalizację pozwoleń znamy z dokładnością do obrębu, dlatego zasięg dla nowych domów "
                "wynosi co najmniej 1 km.")


def _permit_window(con, res: int, months: int) -> tuple[datetime.date, datetime.date] | None:
    """Okno czasowe pozwoleń: `months` miesięcy liczone wstecz od NAJNOWSZYCH danych (nie od dziś).

    Zwraca (pierwszy miesiąc okna, ostatni miesiąc danych) albo None, gdy brak tabeli/danych.
    """
    table = f"permits_r{res}"
    if not table_exists(con, table):
        return None
    newest = con.execute(f"SELECT MAX(month) FROM {table}").fetchall()[0][0]
    if newest is None:
        return None
    index = newest.year * 12 + newest.month - 1 - (months - 1)
    return datetime.date(index // 12, index % 12 + 1, 1), newest


def _period(window) -> dict | None:
    if window is None:
        return None
    return {"from": window[0].strftime("%Y-%m"), "to": window[1].strftime("%Y-%m")}


# Im niższy numer, tym ważniejszy rodzaj miejsca przy nazywaniu lokalizacji: osiedle/wieś jest
# bardziej precyzyjne niż nazwa całego miasta, więc wygrywa nawet jeśli leży nieco dalej.
PLACE_PRIORITY = {"suburb": 0, "neighbourhood": 0, "quarter": 0, "village": 0, "hamlet": 0, "town": 1, "city": 2}


def nearest_place_name(con: duckdb.DuckDBPyConnection, lat: float, lng: float, max_km: float = 3.0) -> str | None:
    """Nazwa najlepszej miejscowości/osiedla w promieniu max_km od punktu (albo None).

    Kolejność: najpierw priorytet rodzaju (osiedle/wieś < miasteczko < miasto), w obrębie
    priorytetu — najbliższe. Wstępnie wybieramy prostokąt ±0,05° (~5 km), dokładną
    odległość liczymy wzorem haversine (odległość na kuli ziemskiej).
    """
    if not table_exists(con, "places"):
        return None
    rows = con.execute(
        "SELECT name, kind, lat, lng FROM places WHERE lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?",
        [lat - 0.05, lat + 0.05, lng - 0.05, lng + 0.05]).fetchall()
    best = None
    for name, kind, plat, plng in rows:
        dist_km = _haversine_km(lat, lng, plat, plng)
        if dist_km > max_km:
            continue
        key = (PLACE_PRIORITY[kind], dist_km)
        if best is None or key < best[0]:
            best = (key, name)
    return best[1] if best else None


# Nazwy zaczynające się od tych słów już mówią, czym jest miejsce — „ul.” byłoby błędem („ul. Plac Solny”).
NO_UL_PREFIX = re.compile(
    r"^(aleja|aleje|al|plac|pl|rondo|osiedle|os|bulwar|skwer|rynek|droga|most|park|wybrzeże|ul|ulica)(\.|\s|$)", re.IGNORECASE)
STREET_MAX_M = 150


def street_label(con: duckdb.DuckDBPyConnection, lat: float, lng: float) -> str:
    """Nazwa lokalizacji do listy „Najlepsze miejsca”: „ul. Długa, Zaodrze”.

    Ulica = najbliższy punkt z tabeli `streets` w promieniu 150 m; za nią dopisujemy nazwę
    miejscowości/osiedla (o ile jej nazwa nie wchodzi już w nazwę ulicy). Gdy ulicy nie ma:
    sama nazwa miejsca, a gdy i jej brak — współrzędne.
    """
    place = nearest_place_name(con, lat, lng)
    street = None
    if table_exists(con, "streets"):
        # prostokąt ±0,0015° szerokości (~170 m) i ±0,0025° długości (~170 m), potem dokładna odległość
        rows = con.execute("SELECT name, lat, lng FROM streets WHERE lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?",
                           [lat - 0.0015, lat + 0.0015, lng - 0.0025, lng + 0.0025]).fetchall()
        if rows:
            dist = _haversine_m(lat, lng, np.array([r[1] for r in rows]), np.array([r[2] for r in rows]))
            best = int(np.argmin(dist))
            if dist[best] <= STREET_MAX_M:
                name = rows[best][0]
                street = name if NO_UL_PREFIX.match(name) else f"ul. {name}"
                # nazwa miejsca jako CAŁE słowo („Wrocław” nie jest w „Wrocławska”)
                if place and re.search(r"(?<!\w)" + re.escape(place) + r"(?!\w)", name, re.IGNORECASE):
                    place = None
    if street and place:
        return f"{street}, {place}"
    return street or place or f"okolice {lat:.3f}, {lng:.3f}"


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Odległość po powierzchni kuli (promień Ziemi 6371 km) między dwoma punktami."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(a))




# ---------------------------------------------------------------- /api/surface ----

@dataclass(frozen=True)
class SurfaceParams:
    type_id: str | None
    demand_id: str | None
    lat: float
    lng: float
    radius_km: float          # promień analizowanego obszaru (okrąg wokół miejsca)
    reach_km: float           # zasięg klienta (parametr rozpadu odległości)
    months: int = 24


def _is_permits(demand_id: str | None) -> bool:
    return bool(demand_id) and DEMANDS[demand_id].source == "permits"


def effective_reach_km(demand_id: str | None, reach_km: float) -> float:
    """Zasięg klienta: nie mniejszy niż 0,3 km (rozdzielczość danych), a dla pozwoleń niż 1 km."""
    reach_km = max(reach_km, MIN_REACH_KM)
    return max(reach_km, PERMITS_MIN_REACH_KM) if _is_permits(demand_id) else reach_km


def _reach_notes(demand_id: str | None, reach_km: float) -> list[str]:
    """Notatka, gdy zażądany zasięg został podniesiony (jedna, ta istotniejsza)."""
    if _is_permits(demand_id) and reach_km < PERMITS_MIN_REACH_KM:
        return [PERMITS_NOTE]
    return [MIN_REACH_NOTE] if reach_km < MIN_REACH_KM else []


def surface_layers(p: SurfaceParams) -> list[str]:
    """typ + klienci → ["open", "demand"]; sam popyt → ["demand"]; sama branża → ["competition"].

    Gdy popyt pochodzi z pozwoleń, dochodzi warstwa "trend" (gdzie budów przybywa).
    """
    if not p.type_id and not p.demand_id:
        raise ValueError("Wybierz typ działalności albo czynnik popytu")
    layers = ["open", "demand"] if p.type_id and p.demand_id else ["demand"] if p.demand_id else ["competition"]
    return layers + ["trend"] if _is_permits(p.demand_id) else layers


def demand_res(reach_km: float) -> int:
    """Rozdzielczość H3 źródeł popytu: duży zasięg nie wymaga drobnych komórek (a byłoby ich za dużo)."""
    return 9 if reach_km <= 2 else 8 if reach_km <= 8 else 7 if reach_km <= 12 else 6


def _box(lat: float, lng: float, radius_km: float) -> list[float]:
    """Prostokąt w stopniach (minLat, maxLat, minLng, maxLng) obejmujący okrąg o podanym promieniu."""
    dlat = radius_km / 110.54
    dlng = radius_km / (111.32 * math.cos(math.radians(lat)))
    return [lat - dlat, lat + dlat, lng - dlng, lng + dlng]


def load_demand(con, demand_id: str, res: int, box: list[float], months: int):
    """Źródła popytu: (lat, lng, waga) komórek H3 w prostokącie; waga = mieszkańcy albo liczba nowych budów.

    Zwraca (tablica N×3, okno pozwoleń lub None). Dla pozwoleń brak danych → pusta tablica i okno None.
    """
    demand = DEMANDS[demand_id]
    if not table_exists(con, f"hex_pop_r{res}"):
        raise DatabaseMissing(f"brak tabeli hex_pop_r{res}")
    if demand.source == "census":
        rows = con.execute(f"SELECT lat, lng, {demand.column} FROM hex_pop_r{res} "
                           f"WHERE lat BETWEEN ? AND ? AND lng BETWEEN ? AND ? AND {demand.column} > 0", box).fetchall()
        return np.array(rows, dtype=float).reshape(-1, 3), None
    window = _permit_window(con, res, months)
    if window is None:
        return np.empty((0, 3)), None
    kinds = ", ".join("?" for _ in demand.kinds)
    rows = con.execute(f"SELECT lat, lng, SUM(n) FROM permits_r{res} WHERE kind IN ({kinds}) AND month >= ? "
                       "AND lat BETWEEN ? AND ? AND lng BETWEEN ? AND ? GROUP BY lat, lng",
                       [*demand.kinds, window[0], *box]).fetchall()
    return np.array(rows, dtype=float).reshape(-1, 3), window


def load_competitors(con, type_id: str, box: list[float]) -> np.ndarray:
    """Dokładne położenia firm danego typu (z tabeli `poi`) w prostokącie; wynik N×2 (lat, lng)."""
    if not table_exists(con, "poi"):
        return np.empty((0, 2))
    rows = con.execute("SELECT lat, lng FROM poi WHERE type_id = ? AND lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?",
                       [type_id, *box]).fetchall()
    return np.array(rows, dtype=float).reshape(-1, 2)


def _shift_months(day: datetime.date, k: int) -> datetime.date:
    """Pierwszy dzień miesiąca przesunięty o k miesięcy (k może być ujemne)."""
    index = day.year * 12 + day.month - 1 + k
    return datetime.date(index // 12, index % 12 + 1, 1)


def load_trend(con, demand_id: str, res: int, box: list[float]):
    """Zmiana liczby nowych budów w komórkach: ostatnie 12 mies. MINUS poprzednie 12 mies.

    Okna liczymy od najnowszych danych (jak `_permit_window`), pomijając ostatni, niepełny miesiąc.
    Zwraca (tablica N×3: lat, lng, zmiana; okno ostatnich 12 mies. lub None).
    """
    window = _permit_window(con, res, 1)
    if window is None:
        return np.empty((0, 3)), None
    # Najnowszy miesiąc w danych jest zwykle niepełny (plik z bieżącego miesiąca) — liczony jak pełny zaniżałby trend
    # nawet o ok. 4% całości, czyli tyle, ile wynosi sam sygnał. Dlatego 12 miesięcy kończymy na poprzednim.
    last = _shift_months(window[1], -1)
    first = _shift_months(last, -11)
    kinds = DEMANDS[demand_id].kinds
    marks = ", ".join("?" for _ in kinds)
    rows = con.execute(f"SELECT lat, lng, SUM(CASE WHEN month >= ? THEN n ELSE -n END) FROM permits_r{res} "
                       f"WHERE kind IN ({marks}) AND month >= ? AND month <= ? AND lat BETWEEN ? AND ? AND lng BETWEEN ? AND ? "
                       "GROUP BY lat, lng", [first, *kinds, _shift_months(first, -12), last, *box]).fetchall()
    return np.array(rows, dtype=float).reshape(-1, 3), (first, last)


# ---------------------------------------------------------------- podsumowanie obszaru ----

_national: dict[tuple, float | None] = {}     # średnia krajowa liczona raz na (typ, popyt, okres); czyszczona przy zmianie bazy
on_reset(_national.clear)


def national_per_firm(con, type_id: str, demand_id: str, months: int) -> float | None:
    """Ile „klientów” (popytu) przypada w całej Polsce na jedną firmę danego typu (None, gdy brak firm lub popytu)."""
    key = (type_id, demand_id, months)
    if key not in _national:
        firms = con.execute("SELECT COUNT(*) FROM poi WHERE type_id = ?", [type_id]).fetchone()[0] if table_exists(con, "poi") else 0
        demand, total = DEMANDS[demand_id], 0.0
        if demand.source == "census":
            total = con.execute(f"SELECT COALESCE(SUM({demand.column}), 0) FROM hex_pop_r5").fetchone()[0]
        else:
            window = _permit_window(con, 5, months)
            if window is not None:
                marks = ", ".join("?" for _ in demand.kinds)
                total = con.execute(f"SELECT COALESCE(SUM(n), 0) FROM permits_r5 WHERE kind IN ({marks}) AND month >= ?",
                                    [*demand.kinds, window[0]]).fetchone()[0]
        _national[key] = total / firms if firms and total else None
    return _national[key]


def verdict(per_firm: float | None, national: float | None) -> str | None:
    """„less” = mniej konkurencji niż przeciętnie (na firmę przypada >125% średniej), „more” = więcej (<80%).

    Brak firm w obszarze → „less”; brak średniej krajowej (np. brak danych o pozwoleniach) → None (nie ma z czym porównać).
    """
    if per_firm is None:
        return "less"
    if national is None:
        return None
    if per_firm > 1.25 * national:
        return "less"
    return "more" if per_firm < 0.8 * national else "similar"


def area_summary(con, p: SurfaceParams, frame: LocalFrame) -> dict:
    """Liczby dla całego okręgu obszaru: popyt, firmy (OSM / Overture), ile klientów na firmę, porównanie z Polską.

    Popyt liczymy z komórek res 9, których środek leży w okręgu; firmy — punkty `poi` w okręgu.
    """
    radius_m = p.radius_km * 1000
    box = _box(p.lat, p.lng, p.radius_km)
    summary = {"demand_total": None, "demand_genitive": None, "competitors": None, "type_plural": None,
               "per_firm": None, "national_per_firm": None, "verdict": None, "radius_km": p.radius_km}
    if p.demand_id:
        arr, _ = load_demand(con, p.demand_id, 9, box, p.months)
        total = 0.0
        if len(arr):
            xy = frame.to_metric(arr[:, 0], arr[:, 1])
            total = float(arr[np.hypot(xy[:, 0], xy[:, 1]) <= radius_m, 2].sum())
        summary["demand_total"] = round(total)
        summary["demand_genitive"] = DEMANDS[p.demand_id].genitive
    if p.type_id:
        counts = {"osm": 0, "overture": 0}
        if table_exists(con, "poi"):
            rows = con.execute("SELECT source, lat, lng FROM poi WHERE type_id = ? AND lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?",
                               [p.type_id, *box]).fetchall()
            if rows:
                xy = frame.to_metric(np.array([r[1] for r in rows]), np.array([r[2] for r in rows]))
                for (source, _, _), d in zip(rows, np.hypot(xy[:, 0], xy[:, 1])):
                    if d <= radius_m:
                        counts[source] += 1
        summary["competitors"] = {"total": counts["osm"] + counts["overture"], **counts}
        summary["type_plural"] = PLURALS[p.type_id]
    if p.type_id and p.demand_id:
        firms = summary["competitors"]["total"]
        summary["per_firm"] = round(summary["demand_total"] / firms, 1) if firms else None
        national = national_per_firm(con, p.type_id, p.demand_id, p.months)
        summary["national_per_firm"] = round(national, 1) if national else None
        summary["verdict"] = verdict(summary["per_firm"], national)
    return summary


def _round_significant(values: np.ndarray, digits: int = 3) -> np.ndarray:
    """Zaokrąglenie do `digits` cyfr znaczących (mniejsza odpowiedź JSON).

    Zostawiamy 3 cyfry, a nie 2: przy 2 cyfrach gładko zmieniająca się powierzchnia dostawała widoczne
    „schodki” (pierścienie jednego koloru) po zamianie na mgłę.
    """
    v = np.asarray(values, dtype=float)
    out = np.zeros_like(v)
    nz = v != 0                                          # wartości ujemne (spadek trendu) zaokrąglamy tak samo
    size = np.abs(v[nz])
    scale = 10.0 ** (np.floor(np.log10(size)) - (digits - 1))
    out[nz] = np.sign(v[nz]) * np.round(size / scale) * scale
    return out


def run_surface(con: duckdb.DuckDBPyConnection, p: SurfaceParams) -> dict:
    """Odpowiedź /api/surface: wartości na siatce w okręgu wokół miejsca + top-5 dla każdej warstwy."""
    layers = surface_layers(p)
    reach_km = effective_reach_km(p.demand_id, p.reach_km)
    reach_m, radius_m = reach_km * 1000, p.radius_km * 1000
    notes: list[str] = []
    warnings: list[str] = []
    btype = TYPES[p.type_id] if p.type_id else None
    if btype and btype.osm_quality == "poor":
        warnings.append(POOR_WARNING)
    notes += _reach_notes(p.demand_id, p.reach_km)

    frame = LocalFrame(p.lat, p.lng)                     # metry względem wybranego miejsca (osie na północ i wschód)
    center = np.zeros(2)
    grid_xy, mask, cell_m, nx, ny = make_grid(center, radius_m)
    g = grid_xy[mask]                                    # liczymy tylko punkty w okręgu

    # Źródła popytu: okrąg + bufor 4·zasięg (dalej rozpad i tak daje zero).
    dem_xy, dem_w, window = np.empty((0, 2)), np.empty(0), None
    if p.demand_id:
        res = demand_res(reach_km)
        arr, window = load_demand(con, p.demand_id, res, _box(p.lat, p.lng, p.radius_km + 4 * reach_km), p.months)
        if DEMANDS[p.demand_id].source == "permits" and window is None:
            warnings.append(PERMITS_MISSING_WARNING)
        if len(arr):
            dem_xy, dem_w = frame.to_metric(arr[:, 0], arr[:, 1]), arr[:, 2]
    # Konkurenci: dalej (8·zasięg), bo dostępność konkurencji C_i liczymy także dla źródeł z bufora.
    comp_xy = np.empty((0, 2))
    if p.type_id:
        comp = load_competitors(con, p.type_id, _box(p.lat, p.lng, p.radius_km + 8 * reach_km))
        if len(comp):
            comp_xy = frame.to_metric(comp[:, 0], comp[:, 1])
        elif "open" in layers:
            warnings.append(NO_COMPETITORS_WARNING)

    computed = {}
    if "open" in layers:                                  # E i P liczymy razem — te same pary punkt–źródło
        computed["open"], computed["demand"] = huff_and_potential(g, dem_xy, dem_w, comp_xy, reach_m)
    elif "demand" in layers:
        computed["demand"] = demand_potential(g, dem_xy, dem_w, reach_m)
    else:
        computed["competition"] = competition_density(g, comp_xy, reach_m)
    if "trend" in layers:                                 # zmiana liczby budów (ostatnie 12 mies. − poprzednie 12), też z rozpadem odległości
        trend, _ = load_trend(con, p.demand_id, demand_res(reach_km), _box(p.lat, p.lng, p.radius_km + 4 * reach_km))
        computed["trend"] = (demand_potential(g, frame.to_metric(trend[:, 0], trend[:, 1]), trend[:, 2], reach_m)
                             if len(trend) else np.zeros(len(g)))
    min_sep_m = max(reach_m, radius_m / 5)
    values, top = {}, {}
    for layer in layers:
        full = np.full(len(grid_xy), np.nan)             # NaN = poza okręgiem
        full[mask] = _round_significant(computed[layer])
        values[layer] = [None if np.isnan(x) else x for x in full.tolist()]
        picks = top_points(np.nan_to_num(full), grid_xy, mask, min_sep_m)
        lat, lng = frame.to_latlng(grid_xy[picks])
        top[layer] = [{"lat": float(a), "lng": float(b), "value": float(full[i]),
                       "name": street_label(con, float(a), float(b))}
                      for i, a, b in zip(picks, lat, lng)]

    # Prostokąt obrazu w stopniach: krawędzie kwadratu siatki (przy promieniu ≤ 30 km zniekształcenie jest pomijalne).
    half = nx * cell_m / 2
    edges = frame.to_latlng(np.array([[center[0] - half, center[1]], [center[0] + half, center[1]],
                                [center[0], center[1] - half], [center[0], center[1] + half]]))
    response = {"layers": layers, "reach_km": reach_km,
                "grid": {"west": float(edges[1][0]), "east": float(edges[1][1]),
                         "south": float(edges[0][2]), "north": float(edges[0][3]),
                         "nx": nx, "ny": ny, "cell_m": cell_m},
                "values": values, "top": top, "notes": notes, "warnings": warnings,
                "summary": area_summary(con, p, frame)}
    if window is not None:
        response["permits_period"] = _period(window)
    return response


@functools.lru_cache(maxsize=32)
def _cached(key: SurfaceParams) -> dict:
    return run_surface(cursor(), key)


def cached_surface(p: SurfaceParams) -> dict:
    """run_surface z pamięcią podręczną (LRU 32); klucz ma zaokrąglone parametry (miejsce ~10 m, promień 0,5 km, zasięg 0,1 km)."""
    key = SurfaceParams(p.type_id, p.demand_id, round(p.lat, 4), round(p.lng, 4),
                        round(p.radius_km * 2) / 2, round(p.reach_km, 1), p.months)
    return _cached(key)


on_reset(_cached.cache_clear)   # zmiana/ponowne otwarcie bazy unieważnia wyniki


# ---------------------------------------------------------------- /api/point ----

def _haversine_m(lat: float, lng: float, lats: np.ndarray, lngs: np.ndarray) -> np.ndarray:
    """Odległości [m] od punktu (lat, lng) do tablic punktów — wzór haversine na kuli o promieniu 6371 km."""
    p1, p2 = math.radians(lat), np.radians(lats)
    a = np.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * np.cos(p2) * np.sin(np.radians(lngs - lng) / 2) ** 2
    return 2 * 6_371_000 * np.arcsin(np.sqrt(a))


def point_details(con: duckdb.DuckDBPyConnection, lat: float, lng: float, type_id: str | None,
                  demand_id: str | None, reach_km: float, months: int) -> dict:
    """Dokładne liczby w okręgu zasięgu wokół punktu (dymek po kliknięciu mapy).

    Inaczej niż heatmapa (komórki + agregacja) liczymy tu na najdrobniejszych danych: popyt z komórek
    res 9, których środek leży w okręgu, a firmy z tabeli `poi` po dokładnej odległości punktów.
    """
    if not type_id and not demand_id:
        raise ValueError("Wybierz typ działalności albo czynnik popytu")
    radius_km = effective_reach_km(demand_id, reach_km)
    notes: list[str] = _reach_notes(demand_id, reach_km)
    result: dict = {"radius_km": radius_km, "demand": None, "demand_name": None, "competitors": None,
                    "type_name": None, "expected": None, "nearest": [], "notes": notes}

    # Prostokąt zawiera margines 0,2 km (promień komórki res 9), żeby do zapytania trafiła też komórka klikniętego punktu.
    box = _box(lat, lng, radius_km + 0.2)

    if demand_id:
        demand = DEMANDS[demand_id]
        result["demand_name"] = demand.name
        total = 0.0
        if demand.source == "census":
            if not table_exists(con, "hex_pop_r9"):
                raise DatabaseMissing("brak tabeli hex_pop_r9")
            rows = con.execute(f"SELECT lat, lng, {demand.column}, h3 FROM hex_pop_r9 "
                               "WHERE lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?", box).fetchall()
        else:
            window = _permit_window(con, 9, months)
            rows = []
            if window is None:
                notes.append(PERMITS_MISSING_WARNING)
            else:
                kinds = ", ".join("?" for _ in demand.kinds)
                rows = con.execute(f"SELECT lat, lng, SUM(n), h3 FROM permits_r9 WHERE kind IN ({kinds}) AND month >= ? "
                                   "AND lat BETWEEN ? AND ? AND lng BETWEEN ? AND ? GROUP BY lat, lng, h3",
                                   [*demand.kinds, window[0], *box]).fetchall()
                result["permits_period"] = _period(window)
        if rows:
            arr = np.array([r[:3] for r in rows], dtype=float)
            inside = _haversine_m(lat, lng, arr[:, 0], arr[:, 1]) <= radius_km * 1000
            # Komórka res 9 ma ~0,3 km między środkami, więc przy małym zasięgu okrąg często nie obejmuje żadnego
            # środka. Komórka, w której kliknięto, liczy się zawsze — tak samo jak własna komórka w heatmapie.
            own = h3.latlng_to_cell(lat, lng, 9)
            inside |= np.array([r[3] == own for r in rows])
            total = float(arr[inside, 2].sum())
        result["demand"] = total

    if type_id:
        result["type_name"] = TYPES[type_id].name
        rows = []
        if table_exists(con, "poi"):
            rows = con.execute("SELECT name, lat, lng, source FROM poi WHERE type_id = ? "
                               "AND lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?", [type_id, *box]).fetchall()
        competitors, nearest = 0, []
        if rows:
            dist = _haversine_m(lat, lng, np.array([r[1] for r in rows]), np.array([r[2] for r in rows]))
            order = [i for i in np.argsort(dist, kind="stable") if dist[i] <= radius_km * 1000]
            competitors = len(order)
            nearest = [{"name": rows[i][0] or "bez nazwy", "distance_m": round(float(dist[i])), "source": rows[i][3]}
                       for i in order[:5]]
        result["competitors"] = competitors
        result["nearest"] = nearest

    if type_id and demand_id:
        result["expected"] = _expected_at(con, lat, lng, type_id, demand_id, radius_km, months)
    return result


def _expected_at(con, lat: float, lng: float, type_id: str, demand_id: str, reach_km: float, months: int) -> float:
    """E (model Huffa) dla jednego punktu — te same źródła i wzór co w /api/surface, ale bez siatki."""
    arr, _ = load_demand(con, demand_id, demand_res(reach_km), _box(lat, lng, 4 * reach_km), months)
    if not len(arr):
        return 0.0
    comp = load_competitors(con, type_id, _box(lat, lng, 8 * reach_km))
    frame = LocalFrame(lat, lng)
    comp_xy = frame.to_metric(comp[:, 0], comp[:, 1]) if len(comp) else np.empty((0, 2))
    here = np.zeros((1, 2))
    return float(huff_and_potential(here, frame.to_metric(arr[:, 0], arr[:, 1]), arr[:, 2], comp_xy, reach_km * 1000)[0][0])

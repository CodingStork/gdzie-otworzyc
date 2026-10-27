"""Serwis analizy v2: heatmapa dla widocznego fragmentu mapy (bbox + zoom) i szczegóły klikniętego punktu.

Schemat `run_view` (patrz spec §4):
  1. `display_res` z zoomu (jak duże heksagony rysujemy), `r` = zasięg klienta,
  2. `compute_res` = najdrobniejsza rozdzielczość, na której obliczenia mieszczą się w limitach,
  3. wczytanie komórek `compute_res` z prostokąta widoku + bufora r (konkurent tuż za krawędzią
     widoku też wpływa na wynik),
  4. dla każdej komórki widoku: D = suma popytu i S = suma firm w OKRĘGU o promieniu r (2SFCA),
  5. agregacja do `display_res` średnią ważoną liczbą mieszkańców,
  6. percentyle (kolory) i legenda, top-5 miejsc.
Kroki 1–6 (bez top-5) trafiają do pamięci podręcznej; klucz zawiera bbox przyciągnięty do siatki.
"""
import datetime
import functools
import math
from dataclasses import dataclass

import duckdb
import h3
import numpy as np
import pandas as pd

from backend.app.analysis.kernel import catchment_sums, to_metric
from backend.app.analysis.resolution import (
    HEX_SPACING_KM,
    choose_compute_res,
    display_res_for_zoom,
    snap_bbox,
)
from backend.app.analysis.scoring import legend_values, percentile_rank, pick_top, score, weighted_parent_mean
from backend.app.catalog import DEMANDS, POOR_WARNING, TYPES
from backend.app.db import DatabaseMissing, cursor, on_reset
from etl.aggregate import table_exists

NO_COMPETITORS_WARNING = (
    "Nie znaleziono konkurencji w OpenStreetMap w tym obszarze — wynik pokazuje sam popyt."
)
PERMITS_MISSING_WARNING = "Dane o pozwoleniach nie zostały jeszcze zaimportowane."
PERMITS_MIN_RADIUS_KM = 1.0       # lokalizacja pozwoleń to środek obrębu — dokładniej nie da się zliczać
PERMITS_NOTE = ("Lokalizację pozwoleń znamy z dokładnością do obrębu, dlatego zasięg dla nowych domów "
                "wynosi co najmniej 1 km.")

# Zoom reprezentujący każdy display_res w kluczu pamięci podręcznej (display_res_for_zoom(zoom) = klucz).
_ZOOM_OF_RES = {5: 6, 6: 8, 7: 9, 8: 11, 9: 12}


@dataclass(frozen=True)
class ViewParams:
    type_id: str | None
    demand_id: str | None
    bbox: tuple[float, float, float, float]      # minLng, minLat, maxLng, maxLat
    zoom: int
    bandwidth_km: float
    months: int = 24


def view_mode(p: ViewParams) -> str:
    """full = typ + popyt (Okazja, Popyt, Konkurencja); demand = tylko popyt; competition = tylko typ."""
    if p.type_id and p.demand_id:
        return "full"
    if p.demand_id:
        return "demand"
    if p.type_id:
        return "competition"
    raise ValueError("Wybierz typ działalności albo czynnik popytu")


def effective_radius_km(p: ViewParams) -> float:
    """Zasięg klienta; dla popytu z pozwoleń nie mniejszy niż 1 km."""
    if p.demand_id and DEMANDS[p.demand_id].source == "permits":
        return max(p.bandwidth_km, PERMITS_MIN_RADIUS_KM)
    return p.bandwidth_km


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


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Odległość po powierzchni kuli (promień Ziemi 6371 km) między dwoma punktami."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(a))


# ------------------------------------------------------------------ /api/view ----

@dataclass
class ViewCore:
    """Wynik kroków 1–6 (to, co trafia do cache) + tablice potrzebne do wyboru top-5 dla dokładnego bbox."""
    response: dict
    top_metric: str | None = None
    h3: np.ndarray | None = None          # heksagony display_res, które mamy w odpowiedzi
    lat: np.ndarray | None = None
    lng: np.ndarray | None = None
    xy: np.ndarray | None = None          # współrzędne metryczne (EPSG:2180)
    value: np.ndarray | None = None       # metryka do rankingu top-5 (score / D / S)
    floor: np.ndarray | None = None       # wartość, której kwartyl odcina puste tereny (D; w trybie competition = S)


def _cells_query(con, table: str, columns: str, box: tuple[float, float, float, float], where: str = "",
                 params: list | None = None, group: str = "") -> pd.DataFrame:
    """SELECT z prostokąta (minLat, maxLat, minLng, maxLng) po kolumnach lat/lng tabeli."""
    sql = f"SELECT {columns} FROM {table} WHERE lat BETWEEN ? AND ? AND lng BETWEEN ? AND ? {where} {group}"
    return con.execute(sql, [*box, *(params or [])]).df()


def _empty_core(display_res: int, compute_res: int, radius_km: float, mode: str, notes: list[str],
                warnings: list[str], window=None) -> ViewCore:
    response = {"mode": mode, "display_res": display_res, "compute_res": compute_res, "radius_km": radius_km,
                "hexes": [], "legend": {}, "top_metric": None, "notes": notes, "warnings": warnings}
    if window is not None:
        response["permits_period"] = _period(window)
    return ViewCore(response)


def _compute_core(con: duckdb.DuckDBPyConnection, p: ViewParams) -> ViewCore:
    mode = view_mode(p)
    display_res = display_res_for_zoom(p.zoom)
    radius_km = effective_radius_km(p)
    notes: list[str] = []
    warnings: list[str] = []
    btype = TYPES[p.type_id] if p.type_id else None
    demand = DEMANDS[p.demand_id] if p.demand_id else None
    if btype and btype.osm_quality == "poor":
        warnings.append(POOR_WARNING)
    if demand and demand.source == "permits" and p.bandwidth_km < PERMITS_MIN_RADIUS_KM:
        notes.append(PERMITS_NOTE)

    compute_res = choose_compute_res(p.bbox, radius_km, display_res)
    # Przy res 9 drobniej się nie da; na grubszych poziomach tłumaczymy, dlaczego zasięg bywa „zaokrąglony”.
    if compute_res < 9 and radius_km < HEX_SPACING_KM[compute_res]:
        spacing = f"{HEX_SPACING_KM[compute_res]:.1f}".replace(".", ",")
        notes.append(f"Przy tym przybliżeniu najmniejszy liczony zasięg to ok. {spacing} km — "
                     "przybliż mapę, aby zobaczyć dokładniej.")
    if not table_exists(con, f"hex_pop_r{compute_res}"):
        raise DatabaseMissing(f"brak tabeli hex_pop_r{compute_res}")

    window = None
    if demand and demand.source == "permits":
        window = _permit_window(con, compute_res, p.months)
        if window is None:   # ETL pozwoleń jeszcze nie działał — czytelne ostrzeżenie zamiast błędu
            warnings.append(PERMITS_MISSING_WARNING)
            return _empty_core(display_res, compute_res, radius_km, mode, notes, warnings)

    # --- komórki obszaru + bufor r (prostokąt w stopniach) ---
    min_lng, min_lat, max_lng, max_lat = p.bbox
    dlat = radius_km / 110.54
    dlng = radius_km / (111.32 * math.cos(math.radians(max(abs(min_lat), abs(max_lat)))))
    box = (min_lat - dlat, max_lat + dlat, min_lng - dlng, max_lng + dlng)

    # Ludność jest zawsze potrzebna: jako „ląd” (tylko tam rysujemy heksagony) i jako waga przy agregacji.
    pop_col = demand.column if demand and demand.source == "census" else "pop_total"
    cells = _cells_query(con, f"hex_pop_r{compute_res}", f"h3, lat, lng, pop_total AS pop, {pop_col} AS d_census", box)
    frames = [cells[["h3", "lat", "lng"]]]
    if demand and demand.source == "permits":
        kinds = ", ".join("?" for _ in demand.kinds)
        permits = _cells_query(con, f"permits_r{compute_res}", "h3, lat, lng, SUM(n) AS d_permits", box,
                               f"AND kind IN ({kinds}) AND month >= ?", [*demand.kinds, window[0]], "GROUP BY h3, lat, lng")
        frames.append(permits[["h3", "lat", "lng"]])
    comp = None
    if btype and table_exists(con, f"poi_counts_r{compute_res}"):
        comp = _cells_query(con, f"poi_counts_r{compute_res}", "h3, lat, lng, n AS s", box, "AND type_id = ?", [p.type_id])
        frames.append(comp[["h3", "lat", "lng"]])

    allc = pd.concat(frames).drop_duplicates("h3").reset_index(drop=True)
    allc = allc.merge(cells[["h3", "pop", "d_census"]], how="left", on="h3")
    if demand and demand.source == "permits":
        allc = allc.merge(permits[["h3", "d_permits"]], how="left", on="h3")
        allc["d"] = allc["d_permits"]
    else:
        allc["d"] = allc["d_census"]
    if comp is not None:
        allc = allc.merge(comp[["h3", "s"]], how="left", on="h3")
    else:
        allc["s"] = 0.0
    allc = allc.fillna({"pop": 0.0, "d": 0.0, "s": 0.0}).reset_index(drop=True)

    if allc.empty:
        return _empty_core(display_res, compute_res, radius_km, mode, notes, warnings, window)
    if mode == "full" and allc["s"].sum() == 0:
        warnings.append(NO_COMPETITORS_WARNING)

    # --- D i S w okręgu: celem są komórki widoku, źródłem — wszystkie z bufora ---
    xy = to_metric(allc["lat"].to_numpy(), allc["lng"].to_numpy())
    in_view = ((allc["lat"] >= min_lat) & (allc["lat"] <= max_lat) &
               (allc["lng"] >= min_lng) & (allc["lng"] <= max_lng)).to_numpy()
    if not in_view.any():
        return _empty_core(display_res, compute_res, radius_km, mode, notes, warnings, window)
    sums = catchment_sums(xy[in_view], xy, allc[["d", "s"]].to_numpy(float), radius_m=radius_km * 1000)
    D, S = sums[:, 0], sums[:, 1]
    sc = score(D, S)
    t = allc[in_view]
    t_h3, t_lat, t_lng, t_pop = t["h3"].to_numpy(), t["lat"].to_numpy(), t["lng"].to_numpy(), t["pop"].to_numpy()

    # --- agregacja do display_res (średnia ważona ludnością) ---
    if compute_res > display_res:
        out_h3, vals = weighted_parent_mean(t_h3, np.column_stack([sc, D, S]), t_pop, display_res)
        sc, D, S = vals[:, 0], vals[:, 1], vals[:, 2]
        centers = np.array([h3.cell_to_latlng(c) for c in out_h3])
        out_lat, out_lng = centers[:, 0], centers[:, 1]
    else:
        out_h3, out_lat, out_lng = t_h3, t_lat, t_lng

    # --- które heksagony pokazujemy i jak je kolorujemy ---
    keep = {"full": (D > 0) | (S > 0), "demand": D > 0, "competition": S > 0}[mode]
    if not keep.any():
        return _empty_core(display_res, compute_res, radius_km, mode, notes, warnings, window)
    out_h3, out_lat, out_lng = out_h3[keep], out_lat[keep], out_lng[keep]
    sc, D, S = sc[keep], D[keep], S[keep]
    metrics: dict[str, np.ndarray] = {}
    if mode == "full":
        metrics["score"] = sc
    if mode in ("full", "demand"):
        metrics["D"] = D
    if mode in ("full", "competition"):
        metrics["S"] = S
    pct = {name: percentile_rank(values) for name, values in metrics.items()}

    def col(values: np.ndarray, name: str, i: int):
        return round(float(values[i]), 2) if name in metrics else None

    def pct_of(name: str, i: int):
        return int(pct[name][i]) if name in pct else None

    hexes = [[out_h3[i], col(sc, "score", i), col(D, "D", i), col(S, "S", i),
              pct_of("score", i), pct_of("D", i), pct_of("S", i)] for i in range(len(out_h3))]
    top_metric = {"full": "score", "demand": "D", "competition": "S"}[mode]
    response = {"mode": mode, "display_res": display_res, "compute_res": compute_res, "radius_km": radius_km,
                "hexes": hexes, "legend": {name: legend_values(v) for name, v in metrics.items()},
                "top_metric": top_metric, "notes": notes, "warnings": warnings}
    if window is not None:
        response["permits_period"] = _period(window)
    floor = S if mode == "competition" else D           # tryb competition: bez progu popytu (D := S)
    return ViewCore(response, top_metric, out_h3, out_lat, out_lng, to_metric(out_lat, out_lng),
                    metrics[top_metric], floor)


def _pick_top(con, core: ViewCore, bbox, radius_km: float) -> list[dict]:
    """Top-5 wśród heksagonów w DOKŁADNYM bbox widoku, z odstępem min. max(2r, 1/6 przekątnej widoku)."""
    if core.h3 is None:
        return []
    min_lng, min_lat, max_lng, max_lat = bbox
    inside = (core.lat >= min_lat) & (core.lat <= max_lat) & (core.lng >= min_lng) & (core.lng <= max_lng)
    idx = np.flatnonzero(inside)
    if len(idx) == 0:
        return []
    diag_km = math.hypot((max_lng - min_lng) * 111.32 * math.cos(math.radians((min_lat + max_lat) / 2)),
                         (max_lat - min_lat) * 110.54)
    min_sep_m = max(2 * radius_km, diag_km / 6) * 1000
    chosen = pick_top(core.value[idx], core.floor[idx], core.xy[idx], min_sep_m=min_sep_m)
    top = []
    for k in chosen:
        i = idx[k]
        lat, lng = float(core.lat[i]), float(core.lng[i])
        name = nearest_place_name(con, lat, lng) or f"okolice {lat:.3f}, {lng:.3f}"
        top.append({"h3": core.h3[i], "lat": lat, "lng": lng, "name": name, "value": round(float(core.value[i]), 2)})
    return top


def run_view(con: duckdb.DuckDBPyConnection, p: ViewParams) -> dict:
    """Pełna odpowiedź /api/view dla bbox dokładnie takiego, jaki podano (bez przyciągania i bez cache)."""
    core = _compute_core(con, p)
    return {**core.response, "top": _pick_top(con, core, p.bbox, core.response["radius_km"])}


@functools.lru_cache(maxsize=64)
def _cached_core(key: ViewParams) -> ViewCore:
    return _compute_core(cursor(), key)


def cached_view(p: ViewParams) -> dict:
    """run_view z pamięcią podręczną rdzenia (LRU 64) na bbox przyciągniętym do siatki.

    Małe przesunięcie mapy daje ten sam przyciągnięty bbox → wynik z cache. Top-5 liczymy za każdym
    razem dla dokładnego bbox widoku (tanie: tylko ranking gotowych heksagonów). Błędy nie są cache'owane.
    """
    display_res = display_res_for_zoom(p.zoom)
    key = ViewParams(p.type_id, p.demand_id, snap_bbox(p.bbox, display_res), _ZOOM_OF_RES[display_res],
                     round(p.bandwidth_km, 2), p.months)
    core = _cached_core(key)
    return {**core.response, "top": _pick_top(cursor(), core, p.bbox, core.response["radius_km"])}


on_reset(_cached_core.cache_clear)   # zmiana/ponowne otwarcie bazy unieważnia wyniki


# ---------------------------------------------------------------- /api/point ----

def _haversine_m(lat: float, lng: float, lats: np.ndarray, lngs: np.ndarray) -> np.ndarray:
    """Odległości [m] od punktu (lat, lng) do tablic punktów — wzór haversine na kuli o promieniu 6371 km."""
    p1, p2 = math.radians(lat), np.radians(lats)
    a = np.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * np.cos(p2) * np.sin(np.radians(lngs - lng) / 2) ** 2
    return 2 * 6_371_000 * np.arcsin(np.sqrt(a))


def point_details(con: duckdb.DuckDBPyConnection, lat: float, lng: float, type_id: str | None,
                  demand_id: str | None, bandwidth_km: float, months: int) -> dict:
    """Dokładne liczby w okręgu zasięgu wokół punktu (dymek po kliknięciu mapy).

    Inaczej niż heatmapa (komórki + agregacja) liczymy tu na najdrobniejszych danych: popyt z komórek
    res 9, których środek leży w okręgu, a firmy z tabeli `poi` po dokładnej odległości punktów.
    """
    if not type_id and not demand_id:
        raise ValueError("Wybierz typ działalności albo czynnik popytu")
    p = ViewParams(type_id, demand_id, (lng, lat, lng, lat), 13, bandwidth_km, months)
    radius_km = effective_radius_km(p)
    notes: list[str] = []
    result: dict = {"radius_km": radius_km, "demand": None, "demand_name": None, "competitors": None,
                    "type_name": None, "score": None, "nearest": [], "notes": notes}

    dlat = radius_km / 110.54
    dlng = radius_km / (111.32 * math.cos(math.radians(lat)))
    box = [lat - dlat, lat + dlat, lng - dlng, lng + dlng]

    if demand_id:
        demand = DEMANDS[demand_id]
        result["demand_name"] = demand.name
        total = 0.0
        if demand.source == "census":
            if not table_exists(con, "hex_pop_r9"):
                raise DatabaseMissing("brak tabeli hex_pop_r9")
            rows = con.execute(f"SELECT lat, lng, {demand.column} FROM hex_pop_r9 "
                               "WHERE lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?", box).fetchall()
        else:
            window = _permit_window(con, 9, months)
            rows = []
            if window is None:
                notes.append(PERMITS_MISSING_WARNING)
            else:
                kinds = ", ".join("?" for _ in demand.kinds)
                rows = con.execute(f"SELECT lat, lng, SUM(n) FROM permits_r9 WHERE kind IN ({kinds}) AND month >= ? "
                                   "AND lat BETWEEN ? AND ? AND lng BETWEEN ? AND ? GROUP BY lat, lng",
                                   [*demand.kinds, window[0], *box]).fetchall()
                result["permits_period"] = _period(window)
            if bandwidth_km < PERMITS_MIN_RADIUS_KM:
                notes.append(PERMITS_NOTE)
        if rows:
            arr = np.array(rows, dtype=float)
            inside = _haversine_m(lat, lng, arr[:, 0], arr[:, 1]) <= radius_km * 1000
            total = float(arr[inside, 2].sum())
        result["demand"] = total

    if type_id:
        result["type_name"] = TYPES[type_id].name
        rows = []
        if table_exists(con, "poi"):
            rows = con.execute("SELECT name, lat, lng FROM poi WHERE type_id = ? "
                               "AND lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?", [type_id, *box]).fetchall()
        competitors, nearest = 0, []
        if rows:
            dist = _haversine_m(lat, lng, np.array([r[1] for r in rows]), np.array([r[2] for r in rows]))
            order = [i for i in np.argsort(dist, kind="stable") if dist[i] <= radius_km * 1000]
            competitors = len(order)
            nearest = [{"name": rows[i][0] or "bez nazwy", "distance_m": round(float(dist[i]))} for i in order[:5]]
        result["competitors"] = competitors
        result["nearest"] = nearest

    if type_id and demand_id:
        result["score"] = float(score(np.array([result["demand"]]), np.array([result["competitors"]]))[0])
    return result

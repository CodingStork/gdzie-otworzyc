"""Serwis analizy: z tabel H3 w bazie liczy wynik „klienci na 1 konkurenta” dla wybranego obszaru.

Schemat (dla trybu lokalnego, czyli punkt + promień):
  1. wybór rozdzielczości H3 i szerokości pasma h,
  2. zebranie heksagonów z danymi w obszarze PLUS buforze 3h (efekt krawędzi — konkurent
     tuż za granicą obszaru też wpływa na wynik),
  3. sumy ważone jądrem Gaussa: D (popyt w zasięgu) i S (konkurencja w zasięgu),
  4. wynik = D / (S + 1), percentyle i ranking top-N — tylko dla heksagonów w obszarze.
"""
import datetime
import functools
import math
from dataclasses import dataclass
from typing import Literal

import duckdb
import h3
import numpy as np
import pandas as pd

from backend.app.analysis.kernel import kernel_sums, to_metric
from backend.app.analysis.resolution import HEX_SPACING_KM, choose_resolution, effective_bandwidth_km
from backend.app.analysis.scoring import percentile_rank, pick_top, quantile_breaks, score
from backend.app.catalog import DEMANDS, POOR_WARNING, TYPES
from backend.app.db import DatabaseMissing, cursor, on_reset
from etl.aggregate import table_exists

NO_DEMAND_WARNING = "Brak danych o popycie w tym obszarze."
NO_COMPETITORS_WARNING = (
    "Nie znaleziono konkurencji w OpenStreetMap w tym obszarze — wynik pokazuje sam popyt."
)
PERMITS_MISSING_WARNING = "Dane o pozwoleniach nie zostały jeszcze zaimportowane."


@dataclass(frozen=True)
class AnalysisParams:
    type_id: str
    demand_id: str
    lat: float | None = None
    lng: float | None = None
    radius_km: float | None = None
    scope: Literal["local", "poland"] = "local"
    bandwidth_km: float | None = None
    months: int = 24


def _fetch(con: duckdb.DuckDBPyConnection, sql: str, cells: list[str], params: list | None = None) -> pd.DataFrame:
    """Wykonuje zapytanie z JOIN-em do listy heksagonów (`cells_df`) przekazanej z Pythona."""
    con.register("cells_df", pd.DataFrame({"h3": cells}))
    try:
        return con.execute(sql, params or []).df()
    finally:
        con.unregister("cells_df")


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


def _demand_values(con, res: int, p: AnalysisParams, cells: list[str], window) -> pd.DataFrame:
    """Wartość czynnika popytu d_j w heksagonach (kolumny h3, d)."""
    demand = DEMANDS[p.demand_id]
    if demand.source == "census":
        # nazwa kolumny pochodzi z katalogu (nie od użytkownika) — bezpieczne w SQL
        return _fetch(con, f"SELECT t.h3, t.{demand.column} AS d FROM hex_pop_r{res} t "
                           f"JOIN cells_df c ON t.h3 = c.h3", cells)
    # Pozwolenia: suma liczby pozwoleń wybranych rodzajów (sf/mf) w oknie czasowym.
    kinds = ", ".join("?" for _ in demand.kinds)
    return _fetch(con, f"SELECT t.h3, SUM(t.n) AS d FROM permits_r{res} t JOIN cells_df c ON t.h3 = c.h3 "
                       f"WHERE t.kind IN ({kinds}) AND t.month >= ? GROUP BY t.h3",
                  cells, [*demand.kinds, window[0]])


def _competitor_counts(con, res: int, type_id: str, cells: list[str]) -> pd.DataFrame:
    """Liczba firm danego typu w heksagonach (kolumny h3, s); brak tabeli = brak firm."""
    if not table_exists(con, f"poi_counts_r{res}"):
        return _empty("s")
    return _fetch(con, f"SELECT t.h3, t.n AS s FROM poi_counts_r{res} t JOIN cells_df c ON t.h3 = c.h3 "
                       f"WHERE t.type_id = ?", cells, [type_id])


def _empty(value_column: str) -> pd.DataFrame:
    """Pusta ramka (h3, wartość) z poprawnymi typami — żeby dało się ją łączyć z innymi."""
    return pd.DataFrame({"h3": pd.Series([], dtype=object), value_column: pd.Series([], dtype=float)})


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


def _period(window) -> dict | None:
    if window is None:
        return None
    return {"from": window[0].strftime("%Y-%m"), "to": window[1].strftime("%Y-%m")}


def _empty_result(res: int, h_km: float, warnings: list[str], window=None) -> dict:
    result = {"res": res, "bandwidth_km": h_km, "hexes": [], "top": [], "warnings": warnings,
              "stats": {"n_hex": 0, "n_competitors": 0, "total_demand": 0.0,
                        "score_breaks": [], "D_breaks": [], "S_breaks": []}}
    if window is not None:
        result["permits_period"] = _period(window)
    return result


def _round1(x) -> float:
    return round(float(x), 1)


def run_analysis(con: duckdb.DuckDBPyConnection, p: AnalysisParams) -> dict:
    poland = p.scope == "poland"
    btype = TYPES[p.type_id]
    warnings: list[str] = []
    if btype.osm_quality == "poor":
        warnings.append(POOR_WARNING)

    res = choose_resolution(None if poland else p.radius_km)   # cała Polska → res 6
    if not table_exists(con, f"hex_pop_r{res}"):
        raise DatabaseMissing(f"brak tabeli hex_pop_r{res}")
    h_km = effective_bandwidth_km(p.bandwidth_km or btype.bandwidth_km, res)
    if not poland:
        radius_m = p.radius_km * 1000
        reach_m = radius_m + 3 * h_km * 1000   # obszar + bufor 3h (jądro jest obcięte dla d > 3h)

    window = None
    if DEMANDS[p.demand_id].source == "permits":
        window = _permit_window(con, res, p.months)
        if window is None:   # ETL pozwoleń jeszcze nie działał — czytelne ostrzeżenie zamiast błędu
            warnings.append(PERMITS_MISSING_WARNING)
            return _empty_result(res, h_km, warnings)

    if poland:
        # Cała Polska: obszar = bufor = wszystkie heksagony res 6, w których coś mamy (brak krawędzi do uwzględniania).
        union = [f"SELECT h3 FROM hex_pop_r{res}"]
        if table_exists(con, f"poi_counts_r{res}"):
            union.append(f"SELECT h3 FROM poi_counts_r{res}")
        if window is not None:
            union.append(f"SELECT h3 FROM permits_r{res}")
        candidates = [r[0] for r in con.execute(" UNION ".join(union)).fetchall()]
    else:
        # Heksagony w pobliżu punktu. Pierścienie H3 leżą w odległości od 0,87·k·odstęp do k·odstęp
        # od środka, stąd współczynnik 1,16 — żeby zasięg na pewno objął cały okrąg buforu.
        center = h3.latlng_to_cell(p.lat, p.lng, res)
        k = math.ceil(1.16 * reach_m / 1000 / HEX_SPACING_KM[res]) + 1
        candidates = list(h3.grid_disk(center, k))

    # „Ląd” = heksagony, w których cokolwiek mamy (ludność, popyt, konkurencja). Tylko one
    # są punktami źródłowymi i kandydatami do wyświetlenia — dzięki temu morze i teren
    # za granicą nie dostają heksagonów.
    pop_cells = _fetch(con, f"SELECT t.h3 FROM hex_pop_r{res} t JOIN cells_df c ON t.h3 = c.h3", candidates)
    demand = _demand_values(con, res, p, candidates, window)
    comp = _competitor_counts(con, res, p.type_id, candidates)

    cells = (pop_cells[["h3"]].merge(demand[["h3"]], how="outer", on="h3")
             .merge(comp[["h3"]], how="outer", on="h3").drop_duplicates())
    cells = cells.merge(demand, how="left", on="h3").merge(comp, how="left", on="h3").fillna({"d": 0.0, "s": 0.0})
    cells = cells.reset_index(drop=True)

    if cells.empty:
        warnings.append(NO_DEMAND_WARNING)
        return _empty_result(res, h_km, warnings, window)

    latlng = np.array([h3.cell_to_latlng(c) for c in cells["h3"]])
    xy = to_metric(latlng[:, 0], latlng[:, 1])
    if poland:
        in_area = np.ones(len(cells), dtype=bool)
    else:
        center_xy = to_metric(np.array([p.lat]), np.array([p.lng]))[0]
        dist = np.hypot(xy[:, 0] - center_xy[0], xy[:, 1] - center_xy[1])
        in_buffer = dist <= reach_m
        cells, latlng, xy = cells[in_buffer], latlng[in_buffer], xy[in_buffer]
        in_area = (dist <= radius_m)[in_buffer]

    d = cells["d"].to_numpy(float)
    s = cells["s"].to_numpy(float)
    if s.sum() == 0:
        warnings.append(NO_COMPETITORS_WARNING)

    # Sumy ważone jądrem: celem są heksagony obszaru, źródłami — wszystkie z bufora.
    sums = kernel_sums(xy[in_area], xy, np.column_stack([d, s]), bandwidth_m=h_km * 1000)
    D, S = sums[:, 0], sums[:, 1]
    a_d, a_s = d[in_area], s[in_area]
    area_h3 = cells["h3"].to_numpy()[in_area]
    area_latlng = latlng[in_area]
    area_xy = xy[in_area]

    total_demand = float(a_d.sum())
    if total_demand == 0:
        warnings.append(NO_DEMAND_WARNING)

    sc = score(D, S)
    keep = (D > 0) | (S > 0)
    # Percentyl liczymy tylko wśród pokazywanych heksagonów (tak samo jak klasy kolorów); puste
    # heksagony zaniżałyby rangi i najgorsze miejsce na mapie nie miałoby percentyla 0.
    pct = np.zeros(len(sc), dtype=int)
    pct[keep] = percentile_rank(sc[keep])
    hexes = [[area_h3[i], _round1(sc[i]), _round1(D[i]), _round1(S[i]), _round1(a_d[i]), _round1(a_s[i]), int(pct[i])]
             for i in np.flatnonzero(keep)]

    top = []
    min_sep_km = max(2 * h_km, 20) if poland else 2 * h_km    # w skali kraju miejsca z top-5 mają być od siebie daleko
    for i in pick_top(sc, D, area_xy, min_sep_m=min_sep_km * 1000):
        lat, lng = float(area_latlng[i][0]), float(area_latlng[i][1])
        name = nearest_place_name(con, lat, lng) or f"okolice {lat:.3f}, {lng:.3f}"
        top.append({"h3": area_h3[i], "lat": lat, "lng": lng, "name": name,
                    "score": _round1(sc[i]), "D": _round1(D[i]), "S": _round1(S[i])})

    result = {
        "res": res,
        "bandwidth_km": h_km,
        "hexes": hexes,
        "top": top,
        "stats": {
            "n_hex": len(hexes),
            "n_competitors": int(a_s.sum()),
            "total_demand": _round1(total_demand),
            "score_breaks": [round(b, 2) for b in quantile_breaks(sc[keep])],
            "D_breaks": [round(b, 2) for b in quantile_breaks(D[keep])],
            "S_breaks": [round(b, 2) for b in quantile_breaks(S[keep])],
        },
        "warnings": warnings,
    }
    if window is not None:
        result["permits_period"] = _period(window)
    return result


@functools.lru_cache(maxsize=128)
def _cached(key: AnalysisParams) -> dict:
    return run_analysis(cursor(), key)


def cached_analysis(p: AnalysisParams) -> dict:
    """run_analysis z pamięcią podręczną (LRU, 128 wyników).

    Klucz to parametry zaokrąglone: położenie do 3 miejsc po przecinku (~100 m), promień do 0,5 km,
    zasięg klienta do 0,1 km — drobne różnice (np. przesunięcie pinezki o kilka metrów) trafiają
    w ten sam wynik. W trybie „cała Polska” położenie i promień nie mają znaczenia. Błędy nie są cache'owane.
    """
    if p.scope == "poland":
        key = AnalysisParams(p.type_id, p.demand_id, scope="poland",
                             bandwidth_km=_round_to(p.bandwidth_km, 0.1), months=p.months)
    else:
        key = AnalysisParams(p.type_id, p.demand_id, round(p.lat, 3), round(p.lng, 3), _round_to(p.radius_km, 0.5),
                             "local", _round_to(p.bandwidth_km, 0.1), p.months)
    return _cached(key)


def _round_to(value: float | None, step: float) -> float | None:
    return None if value is None else round(round(value / step) * step, 6)


on_reset(_cached.cache_clear)   # zmiana/ponowne otwarcie bazy unieważnia wyniki

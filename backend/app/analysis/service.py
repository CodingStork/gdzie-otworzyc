"""Serwis analizy: z tabel H3 w bazie liczy wynik „klienci na 1 konkurenta” dla wybranego obszaru.

Schemat (dla trybu lokalnego, czyli punkt + promień):
  1. wybór rozdzielczości H3 i szerokości pasma h,
  2. zebranie heksagonów z danymi w obszarze PLUS buforze 3h (efekt krawędzi — konkurent
     tuż za granicą obszaru też wpływa na wynik),
  3. sumy ważone jądrem Gaussa: D (popyt w zasięgu) i S (konkurencja w zasięgu),
  4. wynik = D / (S + 1), percentyle i ranking top-N — tylko dla heksagonów w obszarze.
"""
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
from backend.app.db import DatabaseMissing
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


def _demand_values(con, res: int, p: AnalysisParams, cells: list[str], warnings: list[str]) -> pd.DataFrame:
    """Wartość czynnika popytu d_j w heksagonach (kolumny h3, d). Czynniki z pozwoleń — Task 15."""
    demand = DEMANDS[p.demand_id]
    if demand.source == "census":
        # nazwa kolumny pochodzi z katalogu (nie od użytkownika) — bezpieczne w SQL
        return _fetch(con, f"SELECT t.h3, t.{demand.column} AS d FROM hex_pop_r{res} t "
                           f"JOIN cells_df c ON t.h3 = c.h3", cells)
    warnings.append(PERMITS_MISSING_WARNING)
    return _empty("d")


def _competitor_counts(con, res: int, type_id: str, cells: list[str]) -> pd.DataFrame:
    """Liczba firm danego typu w heksagonach (kolumny h3, s); brak tabeli = brak firm."""
    if not table_exists(con, f"poi_counts_r{res}"):
        return _empty("s")
    return _fetch(con, f"SELECT t.h3, t.n AS s FROM poi_counts_r{res} t JOIN cells_df c ON t.h3 = c.h3 "
                       f"WHERE t.type_id = ?", cells, [type_id])


def _empty(value_column: str) -> pd.DataFrame:
    """Pusta ramka (h3, wartość) z poprawnymi typami — żeby dało się ją łączyć z innymi."""
    return pd.DataFrame({"h3": pd.Series([], dtype=object), value_column: pd.Series([], dtype=float)})


def _round1(x) -> float:
    return round(float(x), 1)


def run_analysis(con: duckdb.DuckDBPyConnection, p: AnalysisParams) -> dict:
    if p.scope == "poland":
        raise NotImplementedError("Tryb całej Polski — Task 17")
    btype = TYPES[p.type_id]
    warnings: list[str] = []
    if btype.osm_quality == "poor":
        warnings.append(POOR_WARNING)

    res = choose_resolution(p.radius_km)
    if not table_exists(con, f"hex_pop_r{res}"):
        raise DatabaseMissing(f"brak tabeli hex_pop_r{res}")
    h_km = effective_bandwidth_km(p.bandwidth_km or btype.bandwidth_km, res)
    radius_m = p.radius_km * 1000
    reach_m = radius_m + 3 * h_km * 1000   # obszar + bufor 3h (jądro jest obcięte dla d > 3h)

    # Heksagony w pobliżu punktu. Pierścienie H3 leżą w odległości od 0,87·k·odstęp do k·odstęp
    # od środka, stąd współczynnik 1,16 — żeby zasięg na pewno objął cały okrąg buforu.
    center = h3.latlng_to_cell(p.lat, p.lng, res)
    k = math.ceil(1.16 * reach_m / 1000 / HEX_SPACING_KM[res]) + 1
    candidates = list(h3.grid_disk(center, k))

    # „Ląd” = heksagony, w których cokolwiek mamy (ludność, popyt, konkurencja). Tylko one
    # są punktami źródłowymi i kandydatami do wyświetlenia — dzięki temu morze i teren
    # za granicą nie dostają heksagonów.
    pop_cells = _fetch(con, f"SELECT t.h3 FROM hex_pop_r{res} t JOIN cells_df c ON t.h3 = c.h3", candidates)
    demand = _demand_values(con, res, p, candidates, warnings)
    comp = _competitor_counts(con, res, p.type_id, candidates)

    cells = (pop_cells[["h3"]].merge(demand[["h3"]], how="outer", on="h3")
             .merge(comp[["h3"]], how="outer", on="h3").drop_duplicates())
    cells = cells.merge(demand, how="left", on="h3").merge(comp, how="left", on="h3").fillna({"d": 0.0, "s": 0.0})
    cells = cells.reset_index(drop=True)

    empty = {"res": res, "bandwidth_km": h_km, "hexes": [], "top": [], "warnings": warnings,
             "stats": {"n_hex": 0, "n_competitors": 0, "total_demand": 0.0,
                       "score_breaks": [], "D_breaks": [], "S_breaks": []}}
    if cells.empty:
        warnings.append(NO_DEMAND_WARNING)
        return empty

    latlng = np.array([h3.cell_to_latlng(c) for c in cells["h3"]])
    xy = to_metric(latlng[:, 0], latlng[:, 1])
    center_xy = to_metric(np.array([p.lat]), np.array([p.lng]))[0]
    dist = np.hypot(xy[:, 0] - center_xy[0], xy[:, 1] - center_xy[1])
    in_buffer = dist <= reach_m
    in_area = dist <= radius_m
    cells, latlng, xy, dist = cells[in_buffer], latlng[in_buffer], xy[in_buffer], dist[in_buffer]
    in_area = in_area[in_buffer]

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
    pct = percentile_rank(sc)
    keep = (D > 0) | (S > 0)
    hexes = [[area_h3[i], _round1(sc[i]), _round1(D[i]), _round1(S[i]), _round1(a_d[i]), _round1(a_s[i]), int(pct[i])]
             for i in np.flatnonzero(keep)]

    top = []
    for i in pick_top(sc, D, area_xy, min_sep_m=2 * h_km * 1000):
        lat, lng = float(area_latlng[i][0]), float(area_latlng[i][1])
        top.append({"h3": area_h3[i], "lat": lat, "lng": lng, "name": f"okolice {lat:.3f}, {lng:.3f}",
                    "score": _round1(sc[i]), "D": _round1(D[i]), "S": _round1(S[i])})

    return {
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

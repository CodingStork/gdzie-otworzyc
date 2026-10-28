"""Krok ETL `gaps`: gdzie w danych o firmach jest podejrzanie pusto (luki w OpenStreetMap i Overture Maps).

Model Huffa wierzy danym: w miasteczku, w którym nie ma w nich ani jednego salonu, „nowa firma zgarnia wszystkie klientki”.
Często to jednak luka w danych, a nie okazja. Dlatego dla każdej komórki z ludnością (H3 res 9) i każdego typu firmy liczymy:

    oczekiwane = (mieszkańcy w promieniu 2 km) × (firm tego typu w Polsce / mieszkańców Polski)   — „średnia krajowa”
    w danych   = liczba firm tego typu w promieniu 2 km

Komórka jest „luką”, gdy oczekiwane ≥ 3 (wieś, w której średnio byłoby 1 firma, nie jest oceniana — tam brak firm bywa prawdziwy)
i w danych jest najwyżej ¼ oczekiwanych. Progi (GAP_*) są w katalogu i wynikają z pomiaru opisanego w docs/raport-etl.md.

Wynik:
* `gap_rates(type_id, firms, population, rate)` — średnia krajowa firm na mieszkańca,
* `gap_share(type_id, res, h3, share)` — tylko wiersze z share > 0; res 9: 1 (komórka w luce); res 8, 7, 6: jaka część ludności
  komórki (ważona mieszkańcami komórek-dzieci res 9) mieszka w lukach. Takie udziały potrzebuje Huff dla źródeł popytu
  w grubszych rozdzielczościach (zasięg > 2 km).
"""
import duckdb
import h3
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from backend.app.analysis.kernel import to_metric
from backend.app.catalog import GAP_RADIUS_KM, TYPES, is_data_gap
from etl.aggregate import table_exists

SHARE_RESOLUTIONS = (8, 7, 6)      # res 9 jest zapisywana wprost (udział 1)
BLOCK = 20_000                     # tyle komórek liczymy naraz (żeby listy sąsiadów nie zjadły pamięci)


def gap_flags(pop_xy: np.ndarray, pop_w: np.ndarray, firm_xy: np.ndarray, rate: float) -> np.ndarray:
    """Dla każdej komórki z ludnością: czy jest „luką” (współrzędne w metrach, `rate` = firm na mieszkańca w Polsce).

    Jedna komórka = jeden punkt (środek) z wagą (mieszkańcy). „Okolica” to okrąg 2 km wokół środka komórki.
    """
    n = len(pop_xy)
    if n == 0:
        return np.zeros(0, dtype=bool)
    radius_m = GAP_RADIUS_KM * 1000
    tree = cKDTree(pop_xy)
    neighbours = np.empty(n)
    for s in range(0, n, BLOCK):
        lists = tree.query_ball_point(pop_xy[s:s + BLOCK], radius_m)       # sąsiedzi (razem z samą komórką)
        lengths = np.fromiter((len(l) for l in lists), dtype=int, count=len(lists))
        flat = np.concatenate(lists)
        starts = np.concatenate([[0], np.cumsum(lengths)[:-1]])
        neighbours[s:s + BLOCK] = np.add.reduceat(pop_w[flat], starts)    # suma mieszkańców w okręgu
    expected = neighbours * rate
    if len(firm_xy):
        observed = cKDTree(firm_xy).query_ball_point(pop_xy, radius_m, return_length=True)
    else:
        observed = np.zeros(n)
    return is_data_gap(expected, observed)


def share_by_parent(parent_codes: np.ndarray, pop: np.ndarray, flags: np.ndarray, n_parents: int) -> np.ndarray:
    """Udział ludności mieszkającej w lukach w każdej komórce-rodzicu (ważony mieszkańcami komórek-dzieci)."""
    total = np.bincount(parent_codes, weights=pop, minlength=n_parents)
    in_gap = np.bincount(parent_codes, weights=pop * flags, minlength=n_parents)
    return np.divide(in_gap, total, out=np.zeros(n_parents), where=total > 0)


def build_gaps(con: duckdb.DuckDBPyConnection) -> dict:
    """Tworzy tabele `gap_rates` i `gap_share` (puste, gdy brak ludności z lat/lng albo firm)."""
    con.execute("CREATE OR REPLACE TABLE gap_rates (type_id VARCHAR, firms INTEGER, population DOUBLE, rate DOUBLE)")
    con.execute("CREATE OR REPLACE TABLE gap_share (type_id VARCHAR, res INTEGER, h3 VARCHAR, share FLOAT)")
    if not table_exists(con, "hex_pop_r9") or not table_exists(con, "poi"):
        return {"types": 0, "rows": 0}
    cells = con.execute("SELECT h3, lat, lng, pop_total FROM hex_pop_r9 WHERE pop_total > 0 ORDER BY h3").fetchall()
    if not cells:
        return {"types": 0, "rows": 0}
    ids = np.array([c[0] for c in cells])
    pop = np.array([c[3] for c in cells], dtype=float)
    pop_xy = to_metric(np.array([c[1] for c in cells]), np.array([c[2] for c in cells]))
    population = float(pop.sum())

    # rodzice komórek w grubszych rozdzielczościach (raz, wspólnie dla wszystkich typów)
    parents = {}
    for res in SHARE_RESOLUTIONS:
        parent_ids = np.array([h3.cell_to_parent(c, res) for c in ids])
        unique, codes = np.unique(parent_ids, return_inverse=True)
        parents[res] = (unique, codes)

    rows_total, rates = 0, []
    for type_id in TYPES:
        firm_rows = con.execute("SELECT lat, lng FROM poi WHERE type_id = ?", [type_id]).fetchall()
        firm_xy = to_metric(*np.array(firm_rows, dtype=float).T) if firm_rows else np.empty((0, 2))
        rate = len(firm_rows) / population
        rates.append((type_id, len(firm_rows), population, rate))
        flags = gap_flags(pop_xy, pop, firm_xy, rate) if len(firm_rows) else np.zeros(len(ids), dtype=bool)
        parts = [pd.DataFrame({"type_id": type_id, "res": 9, "h3": ids[flags], "share": 1.0})]
        for res, (unique, codes) in parents.items():
            share = share_by_parent(codes, pop, flags, len(unique))
            keep = share > 0
            parts.append(pd.DataFrame({"type_id": type_id, "res": res, "h3": unique[keep], "share": share[keep]}))
        frame = pd.concat(parts, ignore_index=True)
        con.register("gap_part", frame)
        con.execute("INSERT INTO gap_share SELECT type_id, res, h3, CAST(share AS FLOAT) FROM gap_part")
        con.unregister("gap_part")
        rows_total += len(frame)
    con.executemany("INSERT INTO gap_rates VALUES (?, ?, ?, ?)", rates)
    return {"types": len(rates), "rows": rows_total}

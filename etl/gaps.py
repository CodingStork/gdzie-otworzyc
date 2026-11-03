"""Krok ETL `gaps`: gdzie w danych o firmach jest podejrzanie pusto (luki w OpenStreetMap i Overture Maps).

Model Huffa wierzy danym: w miasteczku, w którym nie ma w nich ani jednego salonu, „nowa firma zgarnia wszystkie klientki”.
Często to jednak luka w danych, a nie okazja. Dlatego dla każdej komórki z ludnością (H3 res 9) i każdego typu firmy liczymy:

    oczekiwane = (mieszkańcy w promieniu 2 km) × (firm tego typu w Polsce / mieszkańców Polski)   — „średnia krajowa”
    w danych   = liczba firm tego typu w promieniu 2 km

Komórka jest „luką”, gdy oczekiwane ≥ 3 (wieś, w której średnio byłoby 1 firma, nie jest oceniana — tam brak firm bywa prawdziwy)
i w danych jest najwyżej ¼ oczekiwanych. Progi (GAP_*) są w katalogu i wynikają z pomiaru opisanego w docs/raport-etl.md.

Ten sam krok liczy też „podobne miejsca” (audyt przydatności): średnia krajowa zaniża liczbę firm, jakiej można się spodziewać
w mieście, bo ciągną ją w dół wsie (ich mieszkańcy korzystają z usług w mieście — docs/kompletnosc-danych.md: salony
18 / 10 tys. mieszkańców w wielkich miastach, 4 na wsi, średnia 8,5). Dlatego ludność Polski dzielimy na 5 równych części
(kwintyle) według tego, ilu mieszkańców jest w promieniu 2 km od komórki — od najrzadziej do najgęściej zaludnionych okolic —
i dla każdej klasy liczymy firm na mieszkańca. Podsumowanie obszaru porównuje potem obszar z miejscami o podobnej gęstości.

Wynik:
* `gap_rates(type_id, firms, population, rate)` — średnia krajowa firm na mieszkańca,
* `density_cells(lat, lng, pop_total, cls)` — klasa gęstości (0 = najrzadziej, 4 = najgęściej zaludnione okolice) każdej
  komórki res 9 z ludnością,
* `density_rates(type_id, cls, firms, population, rate, min_residents, max_residents)` — firm na mieszkańca w każdej klasie
  (firma należy do klasy najbliższej komórki z ludnością); min/max_residents = zakres mieszkańców w 2 km w tej klasie,
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
DENSITY_CLASSES = 5                # „podobne miejsca”: kwintyle ludności wg zaludnienia okolicy (każda klasa = 1/5 Polaków)


def neighbourhood_population(pop_xy: np.ndarray, pop_w: np.ndarray) -> np.ndarray:
    """Ilu mieszkańców jest w promieniu 2 km od środka każdej komórki (razem z nią samą); współrzędne w metrach."""
    n = len(pop_xy)
    neighbours = np.zeros(n)
    if n == 0:
        return neighbours
    radius_m = GAP_RADIUS_KM * 1000
    tree = cKDTree(pop_xy)
    for s in range(0, n, BLOCK):
        lists = tree.query_ball_point(pop_xy[s:s + BLOCK], radius_m)       # sąsiedzi (razem z samą komórką)
        lengths = np.fromiter((len(l) for l in lists), dtype=int, count=len(lists))
        flat = np.concatenate(lists)
        starts = np.concatenate([[0], np.cumsum(lengths)[:-1]])
        neighbours[s:s + BLOCK] = np.add.reduceat(pop_w[flat], starts)    # suma mieszkańców w okręgu
    return neighbours


def gap_flags(pop_xy: np.ndarray, pop_w: np.ndarray, firm_xy: np.ndarray, rate: float,
              neighbours: np.ndarray | None = None) -> np.ndarray:
    """Dla każdej komórki z ludnością: czy jest „luką” (współrzędne w metrach, `rate` = firm na mieszkańca w Polsce).

    Jedna komórka = jeden punkt (środek) z wagą (mieszkańcy). „Okolica” to okrąg 2 km wokół środka komórki.
    `neighbours` (mieszkańcy okolicy) można podać z góry — nie zależą od typu firmy, więc `build_gaps` liczy je raz.
    """
    n = len(pop_xy)
    if n == 0:
        return np.zeros(0, dtype=bool)
    radius_m = GAP_RADIUS_KM * 1000
    if neighbours is None:
        neighbours = neighbourhood_population(pop_xy, pop_w)
    expected = neighbours * rate
    if len(firm_xy):
        observed = cKDTree(firm_xy).query_ball_point(pop_xy, radius_m, return_length=True)
    else:
        observed = np.zeros(n)
    return is_data_gap(expected, observed)


def density_classes(neighbours: np.ndarray, pop: np.ndarray, n: int = DENSITY_CLASSES) -> np.ndarray:
    """Klasa gęstości każdej komórki: 0 = najrzadziej zaludniona okolica … n−1 = najgęściej.

    Granice klas to kwantyle WAŻONE ludnością: sortujemy komórki wg mieszkańców w 2 km i tniemy tam, gdzie skumulowana ludność
    przekracza 1/n, 2/n… całości — każda klasa obejmuje ok. 1/n Polaków (bez arbitralnych progów „miasto/wieś”).
    Komórki o tej samej wartości trafiają do tej samej klasy.
    """
    if len(pop) == 0:
        return np.zeros(0, dtype=int)
    order = np.argsort(neighbours, kind="stable")
    cumulative = np.cumsum(pop[order]) / pop.sum()
    # granica klasy k = zaludnienie pierwszej komórki, przy której skumulowana ludność PRZEKRACZA k/n całości
    bounds = [neighbours[order][min(np.searchsorted(cumulative, k / n, side="right"), len(order) - 1)] for k in range(1, n)]
    return np.searchsorted(np.array(bounds), neighbours, side="right").astype(int)


def firms_by_class(pop_xy: np.ndarray, classes: np.ndarray, firm_xy: np.ndarray, n: int = DENSITY_CLASSES) -> np.ndarray:
    """Ile firm jest w każdej klasie gęstości: firma należy do klasy najbliższej komórki z ludnością."""
    if len(firm_xy) == 0 or len(pop_xy) == 0:
        return np.zeros(n, dtype=int)
    _, nearest = cKDTree(pop_xy).query(firm_xy)
    return np.bincount(classes[nearest], minlength=n)


def share_by_parent(parent_codes: np.ndarray, pop: np.ndarray, flags: np.ndarray, n_parents: int) -> np.ndarray:
    """Udział ludności mieszkającej w lukach w każdej komórce-rodzicu (ważony mieszkańcami komórek-dzieci)."""
    total = np.bincount(parent_codes, weights=pop, minlength=n_parents)
    in_gap = np.bincount(parent_codes, weights=pop * flags, minlength=n_parents)
    return np.divide(in_gap, total, out=np.zeros(n_parents), where=total > 0)


def build_gaps(con: duckdb.DuckDBPyConnection) -> dict:
    """Tworzy tabele `gap_rates`, `gap_share`, `density_cells` i `density_rates` (puste, gdy brak ludności z lat/lng albo firm)."""
    con.execute("CREATE OR REPLACE TABLE gap_rates (type_id VARCHAR, firms INTEGER, population DOUBLE, rate DOUBLE)")
    con.execute("CREATE OR REPLACE TABLE gap_share (type_id VARCHAR, res INTEGER, h3 VARCHAR, share FLOAT)")
    con.execute("CREATE OR REPLACE TABLE density_cells (lat DOUBLE, lng DOUBLE, pop_total DOUBLE, cls INTEGER)")
    con.execute("CREATE OR REPLACE TABLE density_rates (type_id VARCHAR, cls INTEGER, firms INTEGER, population DOUBLE, "
                "rate DOUBLE, min_residents DOUBLE, max_residents DOUBLE)")
    if not table_exists(con, "hex_pop_r9") or not table_exists(con, "poi"):
        return {"types": 0, "rows": 0}
    cells = con.execute("SELECT h3, lat, lng, pop_total FROM hex_pop_r9 WHERE pop_total > 0 ORDER BY h3").fetchall()
    if not cells:
        return {"types": 0, "rows": 0}
    ids = np.array([c[0] for c in cells])
    pop = np.array([c[3] for c in cells], dtype=float)
    lat, lng = np.array([c[1] for c in cells]), np.array([c[2] for c in cells])
    pop_xy = to_metric(lat, lng)
    population = float(pop.sum())

    # Mieszkańcy w 2 km i klasa gęstości każdej komórki — raz, wspólnie dla wszystkich typów.
    neighbours = neighbourhood_population(pop_xy, pop)
    classes = density_classes(neighbours, pop)
    class_pop = np.bincount(classes, weights=pop, minlength=DENSITY_CLASSES)
    class_min = [float(neighbours[classes == k].min()) if (classes == k).any() else None for k in range(DENSITY_CLASSES)]
    class_max = [float(neighbours[classes == k].max()) if (classes == k).any() else None for k in range(DENSITY_CLASSES)]
    con.register("density_in", pd.DataFrame({"lat": lat, "lng": lng, "pop_total": pop, "cls": classes}))
    con.execute("INSERT INTO density_cells SELECT lat, lng, pop_total, CAST(cls AS INTEGER) FROM density_in")
    con.unregister("density_in")

    # rodzice komórek w grubszych rozdzielczościach (raz, wspólnie dla wszystkich typów)
    parents = {}
    for res in SHARE_RESOLUTIONS:
        parent_ids = np.array([h3.cell_to_parent(c, res) for c in ids])
        unique, codes = np.unique(parent_ids, return_inverse=True)
        parents[res] = (unique, codes)

    rows_total, rates, density_rows = 0, [], []
    for type_id in TYPES:
        firm_rows = con.execute("SELECT lat, lng FROM poi WHERE type_id = ?", [type_id]).fetchall()
        firm_xy = to_metric(*np.array(firm_rows, dtype=float).T) if firm_rows else np.empty((0, 2))
        rate = len(firm_rows) / population
        rates.append((type_id, len(firm_rows), population, rate))
        flags = gap_flags(pop_xy, pop, firm_xy, rate, neighbours) if len(firm_rows) else np.zeros(len(ids), dtype=bool)
        per_class = firms_by_class(pop_xy, classes, firm_xy)
        density_rows.extend((type_id, k, int(per_class[k]), float(class_pop[k]),
                             float(per_class[k] / class_pop[k]) if class_pop[k] > 0 else None, class_min[k], class_max[k])
                            for k in range(DENSITY_CLASSES))
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
    con.executemany("INSERT INTO density_rates VALUES (?, ?, ?, ?, ?, ?, ?)", density_rows)
    return {"types": len(rates), "rows": rows_total, "density_cells": len(ids)}

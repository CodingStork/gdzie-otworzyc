"""Krok ETL `national`: gotowa mapa Polski (tryb „Cała Polska” w aplikacji).

Dla punktów rozmieszczonych po całym kraju (środki komórek H3 res 8, ~900 m między nimi) liczymy te same wielkości,
co `/api/surface` — model Huffa „Gdzie otworzyć”, potencjał popytu, zagęszczenie firm i trend budów — raz, dla
TYPOWEGO zasięgu branży (patrz `backend/app/analysis/layers.py`). Wynik trafia do tabeli szerokiej `national_r8`
(kolumna = warstwa), a grubsze poziomy `national_r7 … r5` powstają przez wzięcie **maksimum** z komórek-dzieci:
przy oddaleniu pokazujemy „najlepsze miejsce w tym rejonie”, a nie średnią, która zalałaby małe, dobre ośrodki.
`national_meta` trzyma percentyle wartości (p5, p99) — jedną, stałą skalę kolorów dla całego kraju.
Krok jest wznawialny na poziomie warstwy: warstwa z wpisem w `national_meta` jest pomijana (chyba że `force`).
"""
import datetime
import time

import duckdb
import h3
import numpy as np
import pandas as pd

from backend.app.analysis.kernel import to_metric
from backend.app.analysis.layers import Job, demand_layer, expected_layers, is_trend, jobs, layer_months, open_layer
from backend.app.analysis.service import _permit_window, demand_res, load_trend
from backend.app.analysis.surface import (
    competition_availability, competition_density, demand_potential, demand_potentials, huff_multi, round_significant,
)
from backend.app.catalog import DEFAULT_MONTHS, DEMANDS
from etl.aggregate import _register_h3_functions, table_exists

BASE_RES = 8
PYRAMID_RESOLUTIONS = (7, 6, 5)
POLAND_BOX = [48.5, 55.5, 13.5, 24.5]      # minLat, maxLat, minLng, maxLng — cała Polska z zapasem


def _quote(layer: str) -> str:
    return '"' + layer.replace('"', '') + '"'


# ---------------------------------------------------------------- punkty docelowe ----

def build_targets(con: duckdb.DuckDBPyConnection) -> int:
    """Tworzy `national_r8(h3, lat, lng)`: komórki res 8 z ludnością + ich sąsiedzi (firmę można otworzyć tuż obok osiedla)."""
    populated = [r[0] for r in con.execute(f"SELECT h3 FROM hex_pop_r{BASE_RES} WHERE pop_total > 0").fetchall()]
    cells: set[str] = set()
    for cell in populated:
        cells.update(h3.grid_disk(cell, 1))
    rows = []
    for cell in sorted(cells):
        lat, lng = h3.cell_to_latlng(cell)
        rows.append((cell, lat, lng))
    con.execute(f"CREATE OR REPLACE TABLE national_r{BASE_RES} (h3 VARCHAR, lat DOUBLE, lng DOUBLE)")
    con.executemany(f"INSERT INTO national_r{BASE_RES} VALUES (?, ?, ?)", rows)
    return len(rows)


# ---------------------------------------------------------------- źródła popytu i konkurenci ----

class _Sources:
    """Źródła popytu w całej Polsce (komórki H3 w danej rozdzielczości) w układzie EPSG:2180; kilka ostatnich zostaje w pamięci."""

    def __init__(self, con):
        self.con = con
        self._cache: dict[tuple, tuple] = {}

    def get(self, family: str, res: int):
        key = (family, res)
        if key not in self._cache:
            if len(self._cache) >= 3:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = self._load(family, res)
        return self._cache[key]

    def _load(self, family: str, res: int):
        """Zwraca (xy, {czynnik: wagi}) — wagi to mieszkańcy (spis) albo liczba pozwoleń w oknie DEFAULT_MONTHS."""
        con = self.con
        if family == "census":
            columns = sorted({d.column for d in DEMANDS.values() if d.source == "census"})
            arr = np.array(con.execute(f"SELECT lat, lng, {', '.join(columns)} FROM hex_pop_r{res} WHERE pop_total > 0").fetchall(),
                           dtype=float).reshape(-1, 2 + len(columns))
            weights = {d.id: arr[:, 2 + columns.index(d.column)] for d in DEMANDS.values() if d.source == "census"}
        else:
            window = _permit_window(con, res, DEFAULT_MONTHS)
            if window is None:
                return np.empty((0, 2)), {d.id: np.empty(0) for d in DEMANDS.values() if d.source == "permits"}
            rows = con.execute(f"""SELECT lat, lng, SUM(CASE WHEN kind = 'sf' THEN n ELSE 0 END),
                                          SUM(CASE WHEN kind = 'mf' THEN n ELSE 0 END)
                                   FROM permits_r{res} WHERE month >= ? GROUP BY lat, lng""", [window[0]]).fetchall()
            arr = np.array(rows, dtype=float).reshape(-1, 4)
            kind_col = {"sf": 2, "mf": 3}
            weights = {d.id: arr[:, [kind_col[k] for k in d.kinds]].sum(axis=1) for d in DEMANDS.values() if d.source == "permits"}
        return (to_metric(arr[:, 0], arr[:, 1]) if len(arr) else np.empty((0, 2))), weights


def _competitors_xy(con, type_id: str) -> np.ndarray:
    if not table_exists(con, "poi"):
        return np.empty((0, 2))
    rows = con.execute("SELECT lat, lng FROM poi WHERE type_id = ?", [type_id]).fetchall()
    return to_metric(*np.array(rows, dtype=float).reshape(-1, 2).T) if rows else np.empty((0, 2))


# ---------------------------------------------------------------- obliczenia jednego zadania ----

def compute_job(con, job: Job, targets_xy: np.ndarray, sources: _Sources, wanted: set[str]) -> dict[str, np.ndarray]:
    """Wartości warstw `wanted` (podzbiór job.outputs) w punktach docelowych; te same funkcje co /api/surface."""
    reach_m = job.reach_km * 1000
    out: dict[str, np.ndarray] = {}
    if job.kind == "comp":
        out[job.outputs[0]] = competition_density(targets_xy, _competitors_xy(con, job.type_id), reach_m)
    elif job.kind == "trend":
        arr, _ = load_trend(con, job.demands[0], demand_res(job.reach_km), POLAND_BOX)
        xy = to_metric(arr[:, 0], arr[:, 1]) if len(arr) else np.empty((0, 2))
        out[job.outputs[0]] = demand_potential(targets_xy, xy, arr[:, 2], reach_m) if len(arr) else np.zeros(len(targets_xy))
    else:
        dem_xy, weights = sources.get(job.family, demand_res(job.reach_km))
        w = np.column_stack([weights[d] for d in job.demands]) if len(dem_xy) else np.empty((0, len(job.demands)))
        if job.kind == "huff":
            availability = competition_availability(dem_xy, _competitors_xy(con, job.type_id), reach_m)   # C_i raz na typ
            e, p = huff_multi(targets_xy, dem_xy, w, availability, reach_m)
            for k, d in enumerate(job.demands):
                out[open_layer(job.type_id, d)] = e[:, k]
                out[demand_layer(d, job.reach_km)] = p[:, k]
        else:
            p = demand_potentials(targets_xy, dem_xy, w, reach_m)
            for k, d in enumerate(job.demands):
                out[demand_layer(d, job.reach_km)] = p[:, k]
    return {layer: values for layer, values in out.items() if layer in wanted}


def _scale(values: np.ndarray, layer: str) -> tuple[float | None, float | None]:
    """p5 i p99 wartości dodatnich (dla trendu: wartości bezwzględnych niezerowych) — stała skala kolorów dla całego kraju."""
    v = np.abs(values) if is_trend(layer) else values
    v = v[v > 0]
    return (float(np.percentile(v, 5)), float(np.percentile(v, 99))) if len(v) else (None, None)


# ---------------------------------------------------------------- piramida ----

def build_pyramid(con: duckdb.DuckDBPyConnection, layers: list[str]) -> dict[str, int]:
    """national_r7 … r5: z komórek-dzieci bierzemy MAKSIMUM (trend: wartość o największym module, ze znakiem)."""
    _register_h3_functions(con)
    aggregates = ", ".join(
        (f"arg_max({_quote(l)}, abs({_quote(l)})) AS {_quote(l)}" if is_trend(l) else f"MAX({_quote(l)}) AS {_quote(l)}")
        for l in layers)
    counts = {f"national_r{BASE_RES}": con.execute(f"SELECT COUNT(*) FROM national_r{BASE_RES}").fetchone()[0]}
    finer = BASE_RES
    for res in PYRAMID_RESOLUTIONS:
        con.execute(f"""CREATE OR REPLACE TABLE national_r{res} AS
                        SELECT h3, h3_lat(h3) AS lat, h3_lng(h3) AS lng, {", ".join(_quote(l) for l in layers)}
                        FROM (SELECT h3_parent(h3, {res}) AS h3, {aggregates} FROM national_r{finer} GROUP BY 1)""")
        counts[f"national_r{res}"] = con.execute(f"SELECT COUNT(*) FROM national_r{res}").fetchone()[0]
        finer = res
    return counts


# ---------------------------------------------------------------- krok ETL ----

def build_national(con: duckdb.DuckDBPyConnection, force: bool = False, log=print) -> dict:
    """Liczy brakujące warstwy gotowej mapy Polski i odbudowuje piramidę. Zwraca podsumowanie (liczby, czasy)."""
    started = time.time()
    if not table_exists(con, f"hex_pop_r{BASE_RES}"):
        raise RuntimeError(f"Brak tabeli hex_pop_r{BASE_RES} — najpierw uruchom krok 'aggregate'")
    if force or not table_exists(con, "national_meta") or not table_exists(con, f"national_r{BASE_RES}"):
        for t in (f"national_r{BASE_RES}", *(f"national_r{r}" for r in PYRAMID_RESOLUTIONS), "national_meta"):
            con.execute(f"DROP TABLE IF EXISTS {t}")
        build_targets(con)
        con.execute("CREATE TABLE national_meta (layer VARCHAR PRIMARY KEY, p5 DOUBLE, p99 DOUBLE, reach_km DOUBLE, "
                    "months INTEGER, computed_at TIMESTAMP)")
    cells = con.execute(f"SELECT h3, lat, lng FROM national_r{BASE_RES} ORDER BY h3").fetchall()
    ids = [c[0] for c in cells]
    targets_xy = to_metric(np.array([c[1] for c in cells]), np.array([c[2] for c in cells]))
    done = {r[0] for r in con.execute("SELECT layer FROM national_meta").fetchall()}
    sources = _Sources(con)
    computed = 0
    for job in jobs():
        wanted = {layer for layer in job.outputs if layer not in done}
        if not wanted:
            continue
        t0 = time.time()
        values = compute_job(con, job, targets_xy, sources, wanted)
        for layer, v in values.items():
            v = round_significant(v).astype(np.float32)
            columns = {r[0] for r in con.execute(
                f"SELECT column_name FROM information_schema.columns WHERE table_name = 'national_r{BASE_RES}'").fetchall()}
            if layer in columns:                     # resztka przerwanego przebiegu — zapisujemy od nowa
                con.execute(f"ALTER TABLE national_r{BASE_RES} DROP COLUMN {_quote(layer)}")
            con.execute(f"ALTER TABLE national_r{BASE_RES} ADD COLUMN {_quote(layer)} FLOAT")
            con.register("layer_values", pd.DataFrame({"h3": ids, "v": v}))
            con.execute(f"UPDATE national_r{BASE_RES} SET {_quote(layer)} = layer_values.v "
                        f"FROM layer_values WHERE national_r{BASE_RES}.h3 = layer_values.h3")
            con.unregister("layer_values")
            p5, p99 = _scale(v.astype(float), layer)
            con.execute("INSERT INTO national_meta VALUES (?, ?, ?, ?, ?, ?)",
                        [layer, p5, p99, job.reach_km, layer_months(layer), datetime.datetime.now()])
            done.add(layer)
            computed += 1
        log(f"  [national] {job.kind} {job.type_id or ''} {job.reach_km:g} km: {len(values)} warstw w {time.time() - t0:.1f} s")
    layers = [layer for layer in expected_layers() if layer in done]
    counts = build_pyramid(con, layers)
    return {"layers": len(layers), "computed_now": computed, "tables": counts, "seconds": round(time.time() - started)}

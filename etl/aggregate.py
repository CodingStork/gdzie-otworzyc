"""Agregacja wielorozdzielcza: z tabel w rozdzielczości H3 9 budujemy res 8, 7, 6 i 5.

H3 jest hierarchiczne: każdy heksagon ma jednego "rodzica" w rozdzielczości niższej,
więc zliczanie/sumowanie do grubszej siatki to zwykłe GROUP BY po identyfikatorze rodzica.
Backend czyta potem wyłącznie gotowe tabele (res 9 dla bliskiego widoku, grubsze dla dalekiego).

Każda tabela dostaje też kolumny `lat, lng` (środek heksagonu), żeby backend mógł wybierać
komórki prostokątem widoku mapy zwykłym `WHERE lat BETWEEN ... AND lng BETWEEN ...`.
"""
import duckdb
import h3
from duckdb.sqltypes import DOUBLE, INTEGER, VARCHAR

POP_COLS = ["pop_total", "pop_f", "pop_m", "pop_lt15", "pop_1564", "pop_ge65"]
BASE_RES = 9                      # najdrobniejsza rozdzielczość w bazie
COARSE_RESOLUTIONS = (8, 7, 6, 5)


def table_exists(con: duckdb.DuckDBPyConnection, name: str) -> bool:
    n = con.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?", [name]).fetchall()[0][0]
    return n > 0


def _register_h3_functions(con: duckdb.DuckDBPyConnection) -> None:
    """Udostępnia w SQL funkcje H3: h3_parent(h3, res), h3_cell(lat, lng, res), h3_lat(h3), h3_lng(h3)."""
    functions = [
        ("h3_parent", lambda cell, res: h3.cell_to_parent(cell, res), [VARCHAR, INTEGER], VARCHAR),
        ("h3_cell", lambda lat, lng, res: h3.latlng_to_cell(lat, lng, res), [DOUBLE, DOUBLE, INTEGER], VARCHAR),
        ("h3_lat", lambda cell: h3.cell_to_latlng(cell)[0], [VARCHAR], DOUBLE),
        ("h3_lng", lambda cell: h3.cell_to_latlng(cell)[1], [VARCHAR], DOUBLE),
    ]
    for name, fn, args, ret in functions:
        try:
            con.create_function(name, fn, args, ret)
        except duckdb.Error:
            pass  # funkcja jest już zarejestrowana w tym połączeniu


def _ensure_latlng(con: duckdb.DuckDBPyConnection, table: str) -> None:
    """Dodaje kolumny lat, lng (środek heksagonu) do tabeli, jeśli ich jeszcze nie ma."""
    cols = {r[0] for r in con.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = ?", [table]).fetchall()}
    if {"lat", "lng"} <= cols:
        return
    con.execute(f"ALTER TABLE {table} ADD COLUMN lat DOUBLE")
    con.execute(f"ALTER TABLE {table} ADD COLUMN lng DOUBLE")
    con.execute(f"UPDATE {table} SET lat = h3_lat(h3), lng = h3_lng(h3)")


def build_aggregates(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Tworzy tabele res 9→5 (z lat/lng). Pomija te, dla których brakuje tabeli źródłowej."""
    _register_h3_functions(con)
    created: list[str] = []

    if table_exists(con, f"hex_pop_r{BASE_RES}"):
        _ensure_latlng(con, f"hex_pop_r{BASE_RES}")
        created.append(f"hex_pop_r{BASE_RES}")
        sums = ", ".join(f"SUM({c}) AS {c}" for c in POP_COLS)
        finer = BASE_RES
        for res in COARSE_RESOLUTIONS:      # każdy poziom z poprzedniego (mniej wierszy niż z res 9 za każdym razem)
            con.execute(f"""CREATE OR REPLACE TABLE hex_pop_r{res} AS
                            SELECT h3, h3_lat(h3) AS lat, h3_lng(h3) AS lng, {", ".join(POP_COLS)}
                            FROM (SELECT h3_parent(h3, {res}) AS h3, {sums} FROM hex_pop_r{finer} GROUP BY 1)""")
            created.append(f"hex_pop_r{res}")
            finer = res

    if table_exists(con, "poi"):
        # res 9 liczymy z położenia punktów (kolumna poi.h3 jest w res 8); wyższe poziomy sumują zliczenia.
        con.execute(f"""CREATE OR REPLACE TABLE poi_counts_r{BASE_RES} AS
                        SELECT h3, h3_lat(h3) AS lat, h3_lng(h3) AS lng, type_id, n
                        FROM (SELECT h3_cell(lat, lng, {BASE_RES}) AS h3, type_id, CAST(COUNT(*) AS INTEGER) AS n
                              FROM poi GROUP BY 1, 2)""")
        created.append(f"poi_counts_r{BASE_RES}")
        finer = BASE_RES
        for res in COARSE_RESOLUTIONS:
            con.execute(f"""CREATE OR REPLACE TABLE poi_counts_r{res} AS
                            SELECT h3, h3_lat(h3) AS lat, h3_lng(h3) AS lng, type_id, n
                            FROM (SELECT h3_parent(h3, {res}) AS h3, type_id, CAST(SUM(n) AS INTEGER) AS n
                                  FROM poi_counts_r{finer} GROUP BY 1, 2)""")
            created.append(f"poi_counts_r{res}")
            finer = res

    if table_exists(con, f"permits_r{BASE_RES}"):
        _ensure_latlng(con, f"permits_r{BASE_RES}")
        created.append(f"permits_r{BASE_RES}")
        finer = BASE_RES
        for res in COARSE_RESOLUTIONS:
            con.execute(f"""CREATE OR REPLACE TABLE permits_r{res} AS
                            SELECT h3, h3_lat(h3) AS lat, h3_lng(h3) AS lng, month, kind, n
                            FROM (SELECT h3_parent(h3, {res}) AS h3, month, kind, CAST(SUM(n) AS INTEGER) AS n
                                  FROM permits_r{finer} GROUP BY 1, 2, 3)""")
            created.append(f"permits_r{res}")
            finer = res

    return {name: con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] for name in created}

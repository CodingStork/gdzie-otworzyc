"""Agregacja wielorozdzielcza: z tabel w rozdzielczości H3 8 budujemy res 7 i 6.

H3 jest hierarchiczne: każdy heksagon ma jednego "rodzica" w rozdzielczości niższej,
więc zliczanie/sumowanie do grubszej siatki to zwykłe GROUP BY po identyfikatorze rodzica.
Backend czyta potem wyłącznie gotowe tabele (res 8 dla małych obszarów, 7 i 6 dla dużych).
"""
import duckdb
import h3
from duckdb.sqltypes import INTEGER, VARCHAR

POP_COLS = ["pop_total", "pop_f", "pop_m", "pop_lt15", "pop_1564", "pop_ge65"]
COARSE_RESOLUTIONS = (7, 6)


def table_exists(con: duckdb.DuckDBPyConnection, name: str) -> bool:
    n = con.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?", [name]).fetchone()[0]
    return n > 0


def _register_h3_parent(con: duckdb.DuckDBPyConnection) -> None:
    """Udostępnia w SQL funkcję h3_parent(h3, res) — rodzic komórki w rozdzielczości res."""
    try:
        con.create_function("h3_parent", lambda cell, res: h3.cell_to_parent(cell, res), [VARCHAR, INTEGER], VARCHAR)
    except duckdb.Error:
        pass  # funkcja jest już zarejestrowana w tym połączeniu


def build_aggregates(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Tworzy tabele *_r7 i *_r6. Pomija te, dla których brakuje tabeli źródłowej (res 8)."""
    _register_h3_parent(con)
    created: list[str] = []

    if table_exists(con, "hex_pop_r8"):
        sums = ", ".join(f"SUM({c}) AS {c}" for c in POP_COLS)
        for res in COARSE_RESOLUTIONS:
            con.execute(f"""CREATE OR REPLACE TABLE hex_pop_r{res} AS
                            SELECT h3_parent(h3, {res}) AS h3, {sums} FROM hex_pop_r8 GROUP BY 1""")
            created.append(f"hex_pop_r{res}")

    if table_exists(con, "poi"):
        # poi ma jeden wiersz na obiekt, więc w res 8 zliczamy; wyższe poziomy sumują zliczenia res 8.
        con.execute("""CREATE OR REPLACE TABLE poi_counts_r8 AS
                       SELECT h3, type_id, CAST(COUNT(*) AS INTEGER) AS n FROM poi GROUP BY h3, type_id""")
        created.append("poi_counts_r8")
        for res in COARSE_RESOLUTIONS:
            con.execute(f"""CREATE OR REPLACE TABLE poi_counts_r{res} AS
                            SELECT h3_parent(h3, {res}) AS h3, type_id, CAST(SUM(n) AS INTEGER) AS n
                            FROM poi_counts_r8 GROUP BY 1, 2""")
            created.append(f"poi_counts_r{res}")

    if table_exists(con, "permits_r8"):
        for res in COARSE_RESOLUTIONS:
            con.execute(f"""CREATE OR REPLACE TABLE permits_r{res} AS
                            SELECT h3_parent(h3, {res}) AS h3, month, kind, CAST(SUM(n) AS INTEGER) AS n
                            FROM permits_r8 GROUP BY 1, 2, 3""")
            created.append(f"permits_r{res}")

    return {name: con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] for name in created}

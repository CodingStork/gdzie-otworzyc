"""Budowanie małych baz DuckDB do testów (zamiast prawdziwych, wielogigabajtowych danych).

Zasada: tabela źródłowa powstaje tylko wtedy, gdy podano dla niej dane (poza hex_pop_r8,
która jest zawsze) — dzięki temu testy mogą sprawdzać zachowanie przy BRAKU tabeli.
"""
from pathlib import Path

import duckdb
import h3

from etl.aggregate import build_aggregates

# Proporcje podkategorii ludności zbliżone do krajowych (jak po imputacji w ETL).
POP_SHARES = {"pop_f": 0.515, "pop_m": 0.483, "pop_lt15": 0.153, "pop_1564": 0.651, "pop_ge65": 0.187}


def make_db(
    path: Path,
    pop: dict[str, float] | None = None,
    pois: list[tuple[str, float, float]] = (),
    permits: list[tuple[float, float, str, str, int]] = (),
    places: list[tuple[str, str, float, float]] = (),
    meta: list[tuple[str, str, str, int]] = (),
) -> Path:
    """pop: h3 (res 8) → pop_total; pois: (type_id, lat, lng); permits: (lat, lng, 'YYYY-MM-01', kind, n);
    places: (name, kind, lat, lng); meta: (source, url, 'YYYY-MM-DD HH:MM:SS', rows)."""
    con = duckdb.connect(str(path))

    cols = ", ".join(f"{c} DOUBLE" for c in ["pop_total", *POP_SHARES])
    con.execute(f"CREATE TABLE hex_pop_r8 (h3 VARCHAR PRIMARY KEY, {cols})")
    for cell, total in (pop or {}).items():
        con.execute("INSERT INTO hex_pop_r8 VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [cell, total, *(total * s for s in POP_SHARES.values())])

    if pois:
        con.execute("CREATE TABLE poi (osm_id VARCHAR, type_id VARCHAR, name VARCHAR, lat DOUBLE, lng DOUBLE, h3 VARCHAR)")
        con.executemany("INSERT INTO poi VALUES (?, ?, ?, ?, ?, ?)",
                        [[f"n{i}", type_id, f"Firma {i}", lat, lng, h3.latlng_to_cell(lat, lng, 8)]
                         for i, (type_id, lat, lng) in enumerate(pois)])

    if permits:
        con.execute("CREATE TABLE permits_r8 (h3 VARCHAR, month DATE, kind VARCHAR, n INTEGER)")
        for lat, lng, month, kind, n in permits:
            con.execute("INSERT INTO permits_r8 VALUES (?, ?, ?, ?)", [h3.latlng_to_cell(lat, lng, 8), month, kind, n])

    if places:
        con.execute("CREATE TABLE places (name VARCHAR, kind VARCHAR, lat DOUBLE, lng DOUBLE, h3 VARCHAR)")
        for name, kind, lat, lng in places:
            con.execute("INSERT INTO places VALUES (?, ?, ?, ?, ?)", [name, kind, lat, lng, h3.latlng_to_cell(lat, lng, 8)])

    if meta:
        con.execute("CREATE TABLE meta (source VARCHAR PRIMARY KEY, url VARCHAR, downloaded_at TIMESTAMP, rows BIGINT)")
        con.executemany("INSERT INTO meta VALUES (?, ?, CAST(? AS TIMESTAMP), ?)", [list(m) for m in meta])

    build_aggregates(con)
    con.close()
    return path

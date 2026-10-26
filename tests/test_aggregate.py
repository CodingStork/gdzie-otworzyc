import duckdb
import h3
import pytest

from etl.aggregate import build_aggregates, table_exists

POP_COLS = ["pop_total", "pop_f", "pop_m", "pop_lt15", "pop_1564", "pop_ge65"]


def _db_with_children():
    """7 heksagonów res 8 będących dziećmi jednego rodzica res 7 (pop_total = 1..7)."""
    con = duckdb.connect()
    parent7 = h3.latlng_to_cell(52.23, 21.01, 7)
    children = sorted(h3.cell_to_children(parent7, 8))
    assert len(children) == 7
    con.execute("CREATE TABLE hex_pop_r8 (h3 VARCHAR, " + ", ".join(f"{c} DOUBLE" for c in POP_COLS) + ")")
    for i, c in enumerate(children, start=1):
        con.execute("INSERT INTO hex_pop_r8 VALUES (?, ?, ?, ?, ?, ?, ?)", [c, i, i, 0, 0, 0, 0])
    return con, parent7


def test_population_summed_to_parents():
    con, parent7 = _db_with_children()
    out = build_aggregates(con)
    assert con.execute("SELECT h3, pop_total FROM hex_pop_r7").fetchall() == [(parent7, 28.0)]
    r6 = con.execute("SELECT h3, pop_total FROM hex_pop_r6").fetchall()
    assert r6 == [(h3.cell_to_parent(parent7, 6), 28.0)]
    assert out["hex_pop_r7"] == 1 and out["hex_pop_r6"] == 1


def test_missing_source_tables_are_skipped():
    con, _ = _db_with_children()
    out = build_aggregates(con)          # brak poi i permits_r8 → bez wyjątku
    assert not table_exists(con, "poi_counts_r8")
    assert not table_exists(con, "permits_r7")
    assert set(out) == {"hex_pop_r7", "hex_pop_r6"}


def test_poi_counts_per_hex_and_type():
    con, parent7 = _db_with_children()
    a, b = sorted(h3.cell_to_children(parent7, 8))[:2]
    con.execute("CREATE TABLE poi (osm_id VARCHAR, type_id VARCHAR, name VARCHAR, lat DOUBLE, lng DOUBLE, h3 VARCHAR)")
    con.execute("INSERT INTO poi VALUES ('n1','beauty','A',0,0,?), ('n2','beauty','B',0,0,?), ('n3','cafe','C',0,0,?)",
                [a, a, b])
    out = build_aggregates(con)
    rows = set(con.execute("SELECT h3, type_id, n FROM poi_counts_r8").fetchall())
    assert rows == {(a, "beauty", 2), (b, "cafe", 1)}
    # na wyższych poziomach liczby sumują się do rodzica
    assert con.execute("SELECT type_id, n FROM poi_counts_r7 ORDER BY type_id").fetchall() == [("beauty", 2), ("cafe", 1)]
    assert out["poi_counts_r6"] == 2


def test_permits_aggregated_to_parents():
    con, parent7 = _db_with_children()
    a, b = sorted(h3.cell_to_children(parent7, 8))[:2]
    con.execute("CREATE TABLE permits_r8 (h3 VARCHAR, month DATE, kind VARCHAR, n INTEGER)")
    con.execute("INSERT INTO permits_r8 VALUES (?, DATE '2026-01-01', 'sf', 2), (?, DATE '2026-01-01', 'sf', 3)", [a, b])
    build_aggregates(con)
    assert con.execute("SELECT h3, n FROM permits_r7").fetchall() == [(parent7, 5)]
    assert con.execute("SELECT COUNT(*) FROM permits_r6").fetchone()[0] == 1


def test_build_aggregates_is_idempotent():
    con, _ = _db_with_children()
    build_aggregates(con)
    build_aggregates(con)   # drugi raz nie rzuca (UDF już zarejestrowana, tabele nadpisane)
    assert con.execute("SELECT COUNT(*) FROM hex_pop_r7").fetchone()[0] == 1

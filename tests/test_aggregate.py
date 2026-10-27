import duckdb
import h3
import pytest

from etl.aggregate import build_aggregates, table_exists

POP_COLS = ["pop_total", "pop_f", "pop_m", "pop_lt15", "pop_1564", "pop_ge65"]


def _db_with_children():
    """7 heksagonów res 9 będących dziećmi jednego rodzica res 8 (pop_total = 1..7)."""
    con = duckdb.connect()
    parent8 = h3.latlng_to_cell(52.23, 21.01, 8)
    children = sorted(h3.cell_to_children(parent8, 9))
    assert len(children) == 7
    con.execute("CREATE TABLE hex_pop_r9 (h3 VARCHAR, " + ", ".join(f"{c} DOUBLE" for c in POP_COLS) + ")")
    for i, c in enumerate(children, start=1):
        con.execute("INSERT INTO hex_pop_r9 VALUES (?, ?, ?, 0, 0, 0, 0)", [c, i, i])
    return con, parent8


def test_aggregates_from_res9_with_latlng():
    con, parent8 = _db_with_children()
    out = build_aggregates(con)
    (cell, total, lat, lng), = con.execute("SELECT h3, pop_total, lat, lng FROM hex_pop_r8").fetchall()
    assert (cell, total) == (parent8, 28.0)
    assert (lat, lng) == pytest.approx(h3.cell_to_latlng(parent8))       # środek rodzica
    assert con.execute("SELECT COUNT(*) FROM hex_pop_r5").fetchone()[0] == 1
    assert con.execute("SELECT SUM(pop_total) FROM hex_pop_r5").fetchone()[0] == 28.0
    assert out["hex_pop_r8"] == 1 and out["hex_pop_r5"] == 1


def test_res9_table_gets_latlng():
    con, _ = _db_with_children()
    build_aggregates(con)
    rows = con.execute("SELECT h3, lat, lng FROM hex_pop_r9").fetchall()
    assert len(rows) == 7
    for cell, lat, lng in rows:
        assert (lat, lng) == pytest.approx(h3.cell_to_latlng(cell))


def test_missing_source_tables_are_skipped():
    con, _ = _db_with_children()
    out = build_aggregates(con)          # brak poi i permits_r9 → bez wyjątku
    assert not table_exists(con, "poi_counts_r9")
    assert not table_exists(con, "permits_r8")
    assert set(out) == {"hex_pop_r9", "hex_pop_r8", "hex_pop_r7", "hex_pop_r6", "hex_pop_r5"}


def test_poi_counts_per_hex_and_type():
    con, parent8 = _db_with_children()
    a, b = sorted(h3.cell_to_children(parent8, 9))[:2]
    (alat, alng), (blat, blng) = h3.cell_to_latlng(a), h3.cell_to_latlng(b)
    con.execute("CREATE TABLE poi (osm_id VARCHAR, type_id VARCHAR, name VARCHAR, lat DOUBLE, lng DOUBLE, h3 VARCHAR)")
    con.execute("INSERT INTO poi VALUES ('n1','beauty','A',?,?,'x'), ('n2','beauty','B',?,?,'x'), ('n3','cafe','C',?,?,'x')",
                [alat, alng, alat, alng, blat, blng])
    out = build_aggregates(con)
    rows = set(con.execute("SELECT h3, type_id, n FROM poi_counts_r9").fetchall())
    assert rows == {(a, "beauty", 2), (b, "cafe", 1)}      # res 9 liczone z lat/lng punktów, nie z kolumny poi.h3
    # na wyższych poziomach liczby sumują się do rodzica
    assert con.execute("SELECT type_id, n FROM poi_counts_r8 ORDER BY type_id").fetchall() == [("beauty", 2), ("cafe", 1)]
    assert out["poi_counts_r5"] == 2
    lat, lng = con.execute("SELECT lat, lng FROM poi_counts_r8 LIMIT 1").fetchone()
    assert (lat, lng) == pytest.approx(h3.cell_to_latlng(parent8))


def test_permits_aggregated_to_parents():
    con, parent8 = _db_with_children()
    a, b = sorted(h3.cell_to_children(parent8, 9))[:2]
    con.execute("CREATE TABLE permits_r9 (h3 VARCHAR, month DATE, kind VARCHAR, n INTEGER)")
    con.execute("INSERT INTO permits_r9 VALUES (?, DATE '2026-01-01', 'sf', 2), (?, DATE '2026-01-01', 'sf', 3)", [a, b])
    build_aggregates(con)
    assert con.execute("SELECT h3, n FROM permits_r8").fetchall() == [(parent8, 5)]
    assert con.execute("SELECT COUNT(*) FROM permits_r5").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM permits_r9 WHERE lat IS NOT NULL").fetchone()[0] == 2


def test_build_aggregates_is_idempotent():
    con, _ = _db_with_children()
    build_aggregates(con)
    build_aggregates(con)   # drugi raz nie rzuca (UDF już zarejestrowana, tabele nadpisane, lat/lng już są)
    assert con.execute("SELECT COUNT(*) FROM hex_pop_r8").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM hex_pop_r9").fetchone()[0] == 7

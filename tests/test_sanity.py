import duckdb
import pytest

from etl.aggregate import build_aggregates
from etl.sanity import THRESHOLDS, check

SMALL = dict(THRESHOLDS, pop_min=100, pop_max=200, hairdressers_min=2, places_min=2, permits_sf_12m_min=3,
             missing_geom_max_share=0.5, building_weights_min=2)


def _good_db():
    con = duckdb.connect()
    con.execute("CREATE TABLE hex_pop_r9 (h3 VARCHAR, pop_total DOUBLE, pop_f DOUBLE, pop_m DOUBLE, pop_lt15 DOUBLE, pop_1564 DOUBLE, pop_ge65 DOUBLE)")
    con.execute("INSERT INTO hex_pop_r9 VALUES ('891e23c459bffff', 150, 1, 1, 1, 1, 1)")
    con.execute("CREATE TABLE poi (osm_id VARCHAR, type_id VARCHAR, name VARCHAR, lat DOUBLE, lng DOUBLE, h3 VARCHAR)")
    con.execute("INSERT INTO poi VALUES ('n1','hairdresser','a',0,0,'891e23c459bffff'), ('n2','hairdresser','b',0,0,'891e23c459bffff')")
    con.execute("CREATE TABLE places (name VARCHAR, kind VARCHAR, lat DOUBLE, lng DOUBLE, h3 VARCHAR)")
    con.execute("INSERT INTO places VALUES ('A','city',0,0,'x'), ('B','city',0,0,'x')")
    con.execute("CREATE TABLE obreb_geom (obreb_id VARCHAR, name VARCHAR, lat DOUBLE, lng DOUBLE, status VARCHAR)")
    con.execute("INSERT INTO obreb_geom VALUES ('1',NULL,0,0,'region'), ('2',NULL,0,0,'missing')")
    con.execute("CREATE TABLE permits_r9 (h3 VARCHAR, month DATE, kind VARCHAR, n INTEGER)")
    con.execute("INSERT INTO permits_r9 VALUES ('891e23c459bffff', DATE '2026-09-01', 'sf', 3), "
                "('891e23c459bffff', DATE '2024-01-01', 'sf', 100)")     # stare pozwolenia nie liczą się do 12 mies.
    con.execute("CREATE TABLE building_weights (cell_e INTEGER, cell_n INTEGER, h3 VARCHAR, w DOUBLE)")
    con.execute("INSERT INTO building_weights VALUES (1, 1, 'x', 5), (2, 2, 'y', 6), (3, 3, 'z', 7)")
    con.execute("CREATE TABLE meta (source VARCHAR PRIMARY KEY, url VARCHAR, downloaded_at TIMESTAMP, rows BIGINT)")
    con.execute("INSERT INTO meta VALUES ('dasymetria', '', now(), 920)")        # 92‰ → 0,92 ludności przez budynki
    build_aggregates(con)
    return con


def test_good_database_has_no_problems():
    assert check(_good_db(), SMALL) == []


def test_population_total_out_of_range():
    con = _good_db()
    con.execute("UPDATE hex_pop_r9 SET pop_total = 500")
    problems = check(con, SMALL)
    assert len(problems) >= 1 and any("ludno" in p.lower() for p in problems)


def test_too_few_hairdressers_and_places():
    con = _good_db()
    con.execute("DELETE FROM poi")
    con.execute("DELETE FROM places")
    problems = check(con, SMALL)
    assert any("hairdresser" in p for p in problems) and any("places" in p for p in problems)


def test_too_many_missing_obreby():
    con = _good_db()
    con.execute("INSERT INTO obreb_geom VALUES ('3',NULL,NULL,NULL,'missing'), ('4',NULL,NULL,NULL,'missing')")
    assert any("obręb" in p for p in check(con, dict(SMALL, missing_geom_max_share=0.05)))


def test_recent_permits_below_threshold():
    con = _good_db()
    assert any("sf" in p for p in check(con, dict(SMALL, permits_sf_12m_min=10)))


def test_missing_tables_are_reported_not_raised():
    con = duckdb.connect()
    problems = check(con, SMALL)
    assert any("hex_pop_r9" in p for p in problems) and any("poi" in p for p in problems)


def test_too_low_dasymetry_share():
    con = _good_db()
    con.execute("UPDATE meta SET rows = 400 WHERE source = 'dasymetria'")
    assert any("dasymetr" in p.lower() for p in check(con, SMALL))


def test_too_few_building_weights():
    con = _good_db()
    con.execute("DELETE FROM building_weights")
    assert any("building_weights" in p for p in check(con, SMALL))


def test_empty_r5_table_reported():
    con = _good_db()
    con.execute("DELETE FROM hex_pop_r5")
    assert any("hex_pop_r5" in p for p in check(con, SMALL))


def test_default_thresholds_match_plan():
    assert (THRESHOLDS["pop_min"], THRESHOLDS["pop_max"]) == (36_900_000, 37_200_000)
    assert THRESHOLDS["hairdressers_min"] == 8000 and THRESHOLDS["places_min"] == 40_000
    assert THRESHOLDS["missing_geom_max_share"] == 0.05 and THRESHOLDS["permits_sf_12m_min"] == 50_000
    assert THRESHOLDS["dasymetry_share_min"] == 0.85 and THRESHOLDS["building_weights_min"] == 1_000_000


def test_permits_without_geocoding_are_reported():
    con = _good_db()
    con.execute("CREATE TABLE permits_raw (source_id VARCHAR, source VARCHAR, kind VARCHAR, date DATE, obreb_id VARCHAR, terc VARCHAR)")
    con.execute("INSERT INTO permits_raw VALUES ('a','p','sf',DATE '2026-01-01','1',''), ('b','p','sf',DATE '2026-01-01','2',''), "
                "('c','p','sf',DATE '2026-01-01','3',''), ('d','p','sf',DATE '2026-01-01','4',''), ('e','p','sf',DATE '2026-01-01','5','')")   # obręby 3–5 bez geokodowania
    assert any("geokodowan" in p for p in check(con, SMALL))
    con.execute("INSERT INTO obreb_geom VALUES ('3',NULL,0,0,'region'), ('4',NULL,0,0,'region'), ('5',NULL,0,0,'region')")
    assert not any("geokodowan" in p for p in check(con, SMALL))


def test_missing_latlng_columns_reported():
    """Kolumny lat/lng dodaje krok aggregate; sama ludność (krok population) bez nich psuje /api/view."""
    con = _good_db()
    con.execute("ALTER TABLE hex_pop_r9 DROP COLUMN lat")
    assert any("lat" in p and "hex_pop_r9" in p for p in check(con, SMALL))

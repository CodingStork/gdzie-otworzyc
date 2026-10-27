import duckdb
import pytest
from fastapi.testclient import TestClient

from backend.app import config
from backend.app.db import reset_connection
from backend.app.main import app
from etl.aggregate import table_exists
from etl.run_all import STEPS, run
from tests.conftest import CENTER, disk


def _db_with_hex_pop_only(data_dir):
    data_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(data_dir / "app.duckdb"))
    con.execute("CREATE TABLE hex_pop_r8 (h3 VARCHAR, pop_total DOUBLE, pop_f DOUBLE, pop_m DOUBLE, "
                "pop_lt15 DOUBLE, pop_1564 DOUBLE, pop_ge65 DOUBLE)")
    for cell in disk(k=2):
        con.execute("INSERT INTO hex_pop_r8 VALUES (?, 10, 5, 5, 1, 7, 2)", [cell])
    con.close()


def test_steps_order():
    assert STEPS == ("download", "osm", "buildings", "population", "permits", "geocode", "permits_hex", "aggregate")


def test_run_aggregate_builds_coarse_tables(tmp_path):
    _db_with_hex_pop_only(tmp_path)
    run(["aggregate"], data_dir=tmp_path)
    con = duckdb.connect(str(tmp_path / "app.duckdb"))
    assert table_exists(con, "hex_pop_r6") and table_exists(con, "hex_pop_r7")
    assert con.execute("SELECT SUM(pop_total) FROM hex_pop_r6").fetchall()[0][0] == 10 * len(disk(k=2))


def test_unknown_step_raises(tmp_path):
    with pytest.raises(ValueError, match="nieznany"):
        run(["nie_ma_takiego"], data_dir=tmp_path)


def test_existing_result_is_skipped_without_force(tmp_path):
    # brak pliku spisu w data/raw: gdyby krok się wykonał, rzuciłby FileNotFoundError
    _db_with_hex_pop_only(tmp_path)
    run(["population"], data_dir=tmp_path)


def test_geocode_without_permits_raw_fails_clearly(tmp_path):
    _db_with_hex_pop_only(tmp_path)
    with pytest.raises(RuntimeError, match="permits"):
        run(["geocode"], data_dir=tmp_path)


def test_permits_hex_then_aggregate(tmp_path):
    _db_with_hex_pop_only(tmp_path)
    con = duckdb.connect(str(tmp_path / "app.duckdb"))
    con.execute("CREATE TABLE permits_raw (source_id VARCHAR, source VARCHAR, kind VARCHAR, date DATE, obreb_id VARCHAR, terc VARCHAR)")
    con.execute("INSERT INTO permits_raw VALUES ('a','pozwolenie','sf',DATE '2026-01-05','O1','')")
    con.execute("CREATE TABLE obreb_geom (obreb_id VARCHAR PRIMARY KEY, name VARCHAR, lat DOUBLE, lng DOUBLE, status VARCHAR)")
    con.execute("INSERT INTO obreb_geom VALUES ('O1', 'x', ?, ?, 'region')", list(CENTER))
    con.close()
    run(["permits_hex", "aggregate"], data_dir=tmp_path)
    con = duckdb.connect(str(tmp_path / "app.duckdb"))
    assert con.execute("SELECT SUM(n) FROM permits_r8").fetchall()[0][0] == 1
    assert con.execute("SELECT SUM(n) FROM permits_r6").fetchall()[0][0] == 1


def test_api_meta_lists_sources_and_attribution(make_client):
    client = make_client(pop={}, meta=[("census", "https://x/census.zip", "2026-10-01 12:00:00", 374423),
                                       ("osm", "https://x/poland.pbf", "2026-10-20 08:30:00", 136584)])
    j = client.get("/api/meta").json()
    assert j["attribution"] == config.ATTRIBUTION
    assert {s["source"] for s in j["sources"]} == {"census", "osm"}
    osm = next(s for s in j["sources"] if s["source"] == "osm")
    assert osm == {"source": "osm", "url": "https://x/poland.pbf", "downloaded_at": "2026-10-20T08:30:00", "rows": 136584}


def test_api_meta_without_table_is_empty_list(make_client):
    j = make_client(pop={}).get("/api/meta").json()
    assert j["sources"] == [] and j["attribution"] == config.ATTRIBUTION


def test_api_meta_db_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "nie_ma.duckdb")
    reset_connection()
    r = TestClient(app).get("/api/meta")
    assert r.status_code == 503 and "etl.run_all" in r.text


def test_incomplete_geocoding_fails_loudly(tmp_path, monkeypatch):
    """Przerwane geokodowanie (np. blokada ULDK) nie może wyglądać jak sukces ani zasilać permits_r8 połową danych."""
    from etl import run_all as run_all_module
    _db_with_hex_pop_only(tmp_path)
    con = duckdb.connect(str(tmp_path / "app.duckdb"))
    con.execute("CREATE TABLE permits_raw (source_id VARCHAR, source VARCHAR, kind VARCHAR, date DATE, obreb_id VARCHAR, terc VARCHAR)")
    con.execute("INSERT INTO permits_raw VALUES ('a','pozwolenie','sf',DATE '2026-01-05','160602_4.0001','')")
    con.close()
    monkeypatch.setattr(run_all_module, "geocode_missing",
                        lambda con, uldk, **kw: {"region": 0, "commune": 0, "missing": 0, "error": 1})
    with pytest.raises(RuntimeError, match="(?i)geokodowanie"):
        run(["geocode"], data_dir=tmp_path)
    con = duckdb.connect(str(tmp_path / "app.duckdb"))
    assert not table_exists(con, "meta") or con.execute("SELECT COUNT(*) FROM meta WHERE source='uldk'").fetchall()[0][0] == 0

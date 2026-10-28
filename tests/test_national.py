"""Krok ETL `national`: gotowa mapa Polski (warstwy res 8, piramida max, stała skala w national_meta, wznawialność)."""
import duckdb
import h3
import numpy as np
import pytest

from backend.app.analysis.kernel import to_metric
from backend.app.analysis.layers import expected_layers, layers_for
from backend.app.analysis.surface import huff_expected, round_significant
from backend.app.catalog import DEMANDS, TYPES
from etl.aggregate import table_exists
from etl.national import build_national
from tests.conftest import CENTER, disk
from tests.factories import make_db

LAT, LNG = CENTER
POIS = [("beauty", LAT, LNG), ("beauty", LAT + 0.02, LNG - 0.03), ("hairdresser", LAT, LNG + 0.005)]
PERMITS = [(LAT, LNG, "2026-09-01", "sf", 5), (LAT + 0.01, LNG, "2026-08-01", "sf", 3), (LAT, LNG, "2025-09-01", "mf", 2)]


def quiet(*_):
    pass


@pytest.fixture
def built(tmp_path):
    """Mała baza (Warszawa, ~470 komórek res 9) z policzoną gotową mapą Polski."""
    pop = {c: 1000.0 for c in disk(k=12)}
    path = make_db(tmp_path / "n.duckdb", pop=pop, pois=POIS, permits=PERMITS)
    con = duckdb.connect(str(path))
    summary = build_national(con, log=quiet)
    yield con, summary
    con.close()


def test_every_catalog_layer_exists_with_meta(built):
    con, summary = built
    expected = expected_layers()
    assert summary["layers"] == len(expected) == con.execute("SELECT COUNT(*) FROM national_meta").fetchone()[0]
    columns = {r[0] for r in con.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'national_r8'").fetchall()}
    assert set(expected) <= columns
    # każda para (typ, sugerowany czynnik) ma warstwę „Gdzie otworzyć”, każdy typ — zagęszczenie, każdy czynnik — popyt
    for t in TYPES.values():
        assert layers_for(t.id, None)[0]["competition"] in columns
        for d in t.suggested_demands:
            layers = layers_for(t.id, d)[0]
            assert layers["open"] in columns and layers["demand"] in columns
    for d in DEMANDS:
        assert layers_for(None, d)[0]["demand"] in columns


def test_open_value_matches_direct_huff(built):
    """Wartość „Gdzie otworzyć” w punkcie res 8 = huff_expected liczony wprost na komórkach res 9 (zasięg salonu: 1,5 km)."""
    con, _ = built
    layer = layers_for("beauty", "pop_f")[0]["open"]
    rows = con.execute(f'SELECT lat, lng, "{layer}" FROM national_r8 WHERE "{layer}" > 0 ORDER BY h3').fetchall()
    assert rows
    pop = con.execute("SELECT lat, lng, pop_f FROM hex_pop_r9 WHERE pop_total > 0").fetchall()
    pop_xy = to_metric(np.array([r[0] for r in pop]), np.array([r[1] for r in pop]))
    poi = con.execute("SELECT lat, lng FROM poi WHERE type_id = 'beauty'").fetchall()
    poi_xy = to_metric(np.array([r[0] for r in poi]), np.array([r[1] for r in poi]))
    for lat, lng, value in rows[::max(1, len(rows) // 6)]:
        expected = huff_expected(to_metric([lat], [lng]), pop_xy, np.array([r[2] for r in pop]), poi_xy, 1500.0)[0]
        assert value == pytest.approx(float(round_significant(np.array([expected]))[0]), rel=1e-3)


def test_pyramid_takes_max_of_children(built):
    con, _ = built
    layer = layers_for("beauty", "pop_f")[0]["open"]
    for res, finer in ((7, 8), (6, 7), (5, 6)):
        parent_max = con.execute(f'SELECT MAX("{layer}") FROM national_r{res}').fetchone()[0]
        child_max = con.execute(f'SELECT MAX("{layer}") FROM national_r{finer}').fetchone()[0]
        assert parent_max == child_max
    # konkretna komórka res 7 = max swoich dzieci z res 8
    parent, value = con.execute(f'SELECT h3, "{layer}" FROM national_r7 ORDER BY "{layer}" DESC LIMIT 1').fetchone()
    children = [c for c, in con.execute("SELECT h3 FROM national_r8").fetchall() if h3.cell_to_parent(c, 7) == parent]
    assert len(children) > 1
    assert max(con.execute(f'SELECT "{layer}" FROM national_r8 WHERE h3 = ?', [c]).fetchone()[0] for c in children) == value


def test_trend_pyramid_keeps_sign_of_largest_magnitude(tmp_path):
    """Trend ma znak: przy agregacji liczy się wartość o największym module (nie zwykłe max)."""
    pop = {c: 1000.0 for c in disk(k=4)}
    # dużo budów w starym roku, mało w ostatnim → trend ujemny
    permits = [(LAT, LNG, "2025-03-01", "sf", 20), (LAT, LNG, "2026-03-01", "sf", 2), (LAT, LNG, "2026-09-01", "sf", 1)]
    con = duckdb.connect(str(make_db(tmp_path / "t.duckdb", pop=pop, permits=permits)))
    build_national(con, log=quiet)
    low = con.execute('SELECT MIN("trend__new_sf") FROM national_r8').fetchone()[0]
    assert low < 0
    assert con.execute('SELECT MIN("trend__new_sf") FROM national_r5').fetchone()[0] == low
    assert con.execute('SELECT MAX("trend__new_sf") FROM national_r5').fetchone()[0] < 0   # ujemny nie zamienia się na zero
    con.close()


def test_meta_has_percentiles_reach_and_months(built):
    con, _ = built
    layer = layers_for("beauty", "pop_f")[0]["open"]
    p5, p99, reach, months = con.execute("SELECT p5, p99, reach_km, months FROM national_meta WHERE layer = ?", [layer]).fetchone()
    values = np.array([r[0] for r in con.execute(f'SELECT "{layer}" FROM national_r8').fetchall()], dtype=float)
    positive = values[values > 0]
    assert p5 == pytest.approx(np.percentile(positive, 5), rel=1e-4) and p99 == pytest.approx(np.percentile(positive, 99), rel=1e-4)
    assert 0 < p5 <= p99 and reach == 1.5 and months is None
    new_sf_layer = layers_for(None, "new_sf")[0]["demand"]
    assert con.execute("SELECT reach_km, months FROM national_meta WHERE layer = ?", [new_sf_layer]).fetchone() == (10.0, 24)


def test_targets_include_neighbour_ring(built):
    """Punkty: komórki res 8 z ludnością i ich sąsiedzi — firmę można otworzyć tuż obok osiedla."""
    con, _ = built
    populated = con.execute("SELECT COUNT(*) FROM hex_pop_r8 WHERE pop_total > 0").fetchone()[0]
    assert con.execute("SELECT COUNT(*) FROM national_r8").fetchone()[0] > populated


def test_resumable_per_layer_and_force(built):
    con, _ = built
    again = build_national(con, log=quiet)
    assert again["computed_now"] == 0                              # wszystko policzone — nic do roboty
    con.execute("DELETE FROM national_meta WHERE layer = 'comp__beauty'")
    resumed = build_national(con, log=quiet)
    assert resumed["computed_now"] == 1 and resumed["layers"] == len(expected_layers())
    assert con.execute('SELECT MAX("comp__beauty") FROM national_r8').fetchone()[0] > 0
    forced = build_national(con, force=True, log=quiet)
    assert forced["computed_now"] == len(expected_layers())


def test_requires_aggregate_first(tmp_path):
    con = duckdb.connect(str(tmp_path / "x.duckdb"))
    with pytest.raises(RuntimeError, match="aggregate"):
        build_national(con, log=quiet)
    assert not table_exists(con, "national_meta")
    con.close()


def test_layer_computed_for_other_reach_is_recomputed(built):
    """Zmiana zasięgu typu w katalogu (bandwidth_km) unieważnia gotową warstwę, choć jej nazwa się nie zmienia."""
    con, _ = built
    con.execute("UPDATE national_meta SET reach_km = 99 WHERE layer = 'open__beauty__pop_f'")
    resumed = build_national(con, log=quiet)
    assert resumed["computed_now"] == 1
    assert con.execute("SELECT reach_km FROM national_meta WHERE layer = 'open__beauty__pop_f'").fetchone()[0] == 1.5
    assert con.execute("SELECT COUNT(*) FROM national_meta WHERE layer = 'open__beauty__pop_f'").fetchone()[0] == 1


# ---------------------------------------------------------------- luki w danych (v3.3) ----

TOWN = (52.23, 21.01)      # miasteczko bez salonów
CITY = (51.10, 17.03)      # miasto z salonami


@pytest.fixture
def two_cities(tmp_path):
    """Miasteczko (bez salonów) i miasto (100 salonów), po ~470 komórek res 9 po 1000 mieszkańców; luki policzone."""
    pop = {c: 1000.0 for c in disk(TOWN, k=12)} | {c: 1000.0 for c in disk(CITY, k=12)}
    pois = [("beauty", CITY[0] + (i % 10) * 0.002, CITY[1] + (i // 10) * 0.002) for i in range(100)]
    con = duckdb.connect(str(make_db(tmp_path / "gap.duckdb", pop=pop, pois=pois, gaps=True)))
    build_national(con, log=quiet)
    yield con
    con.close()


def test_rel_layer_is_expected_and_in_pyramid(two_cities):
    con = two_cities
    assert "rel__beauty__pop_f" in expected_layers()
    for res in (8, 7, 6, 5):
        columns = {r[0] for r in con.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = 'national_r{res}'").fetchall()}
        assert "rel__beauty__pop_f" in columns
    assert con.execute("SELECT COUNT(*) FROM national_meta WHERE layer = 'rel__beauty__pop_f'").fetchone()[0] == 1


def test_rel_is_zero_in_gap_and_most_of_open_in_city_centre(two_cities):
    """Miasteczko: wszyscy klienci w luce → rel = 0, choć E > 0. Środek miasta z salonami: większość klientów wiarygodna."""
    con = two_cities
    q = 'SELECT "open__beauty__pop_f", "rel__beauty__pop_f" FROM national_r8 WHERE lat BETWEEN ? AND ? AND lng BETWEEN ? AND ? ORDER BY 1 DESC LIMIT 1'
    open_town, rel_town = con.execute(q, [TOWN[0] - 0.01, TOWN[0] + 0.01, TOWN[1] - 0.015, TOWN[1] + 0.015]).fetchone()
    assert open_town > 0 and rel_town == 0
    open_city, rel_city = con.execute(q, [CITY[0] + 0.005, CITY[0] + 0.015, CITY[1] + 0.005, CITY[1] + 0.02]).fetchone()   # wśród salonów
    assert open_city > 0 and 0.5 * open_city < rel_city <= open_city


def test_rel_pyramid_takes_max(two_cities):
    con = two_cities
    assert con.execute('SELECT MAX("rel__beauty__pop_f") FROM national_r5').fetchone()[0] == \
        con.execute('SELECT MAX("rel__beauty__pop_f") FROM national_r8').fetchone()[0]


def test_missing_rel_layer_is_computed_without_force(two_cities):
    """Baza z v3.2 miała warstwy „open” bez „rel” — ponowne uruchomienie doliczy tylko brakujące."""
    con = two_cities
    con.execute("DELETE FROM national_meta WHERE layer LIKE 'rel__%'")
    resumed = build_national(con, log=quiet)
    assert resumed["computed_now"] == len([l for l in expected_layers() if l.startswith("rel__")])


def test_without_gap_tables_rel_equals_open(tmp_path):
    """Stara baza bez tabeli gap_share: wszędzie 0 luk, czyli rel = E."""
    pop = {c: 1000.0 for c in disk(k=4)}
    con = duckdb.connect(str(make_db(tmp_path / "old.duckdb", pop=pop, pois=POIS)))
    build_national(con, log=quiet)
    rows = con.execute('SELECT "open__beauty__pop_f", "rel__beauty__pop_f" FROM national_r8 WHERE "open__beauty__pop_f" > 0').fetchall()
    assert rows and all(o == pytest.approx(r, rel=1e-3) for o, r in rows)
    con.close()

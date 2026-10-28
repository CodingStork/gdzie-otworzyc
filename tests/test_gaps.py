"""Krok ETL `gaps`: komórki, w których w danych jest podejrzanie mało firm (luki w OSM / Overture)."""
import duckdb
import h3
import numpy as np

from etl.aggregate import build_aggregates
from etl.gaps import build_gaps, gap_flags, share_by_parent
from tests.conftest import disk
from tests.factories import make_db

RATE = 1 / 2000          # średnio 1 firma na 2000 mieszkańców


def _town(n_cells=20, pop_each=500.0):
    """Miasteczko: komórki co 100 m w rzędzie (rząd długi na 2 km) (razem 10 000 mieszkańców, wszystkie w promieniu 2 km)."""
    xy = np.column_stack([np.arange(n_cells) * 100.0, np.zeros(n_cells)])
    return xy, np.full(n_cells, pop_each)


def test_town_without_firms_is_a_gap():
    xy, w = _town()                                    # oczekiwane ok. 5 firm
    assert gap_flags(xy, w, np.empty((0, 2)), RATE).all()


def test_town_with_enough_firms_is_not_a_gap():
    xy, w = _town()
    firms = np.array([[500.0, 0.0], [1500.0, 0.0]])    # 2 firmy przy ~5 oczekiwanych: 2 > ¼ · 5
    assert not gap_flags(xy, w, firms, RATE).any()


def test_one_firm_is_still_a_gap_when_five_expected():
    xy, w = _town()
    assert gap_flags(xy, w, np.array([[500.0, 0.0]]), RATE).all()     # 1 ≤ ¼ · ~5


def test_village_is_not_assessed():
    xy, w = _town(n_cells=4)                           # 2000 mieszkańców → oczekiwana 1 firma < 3
    assert not gap_flags(xy, w, np.empty((0, 2)), RATE).any()


def test_far_firms_do_not_count():
    xy, w = _town()
    far = np.array([[30_000.0, 0.0]] * 10)             # dużo firm, ale 30 km dalej
    assert gap_flags(xy, w, far, RATE).all()


def test_share_by_parent_is_population_weighted():
    # rodzic 0: dzieci 300 (w luce) i 100 (nie) → 0,75; rodzic 1: jedno dziecko w luce → 1
    parent = np.array([0, 0, 1])
    share = share_by_parent(parent, np.array([300.0, 100.0, 50.0]), np.array([True, False, True]), 2)
    assert np.allclose(share, [0.75, 1.0])


def _two_cities_db(path):
    """Miasteczko A (61 000 mieszkańców, zero salonów) i miasto B (tyle samo mieszkańców, 100 salonów)."""
    a, b = (52.23, 21.01), (51.10, 17.03)
    pop = {c: 1000.0 for c in disk(a, k=4)} | {c: 1000.0 for c in disk(b, k=4)}
    pois = [("beauty", b[0] + (i % 10) * 0.0005, b[1] + (i // 10) * 0.0005) for i in range(100)]
    return make_db(path, pop=pop, pois=pois, gaps=True), a, b


def test_build_gaps_marks_town_without_firms(tmp_path):
    path, a, b = _two_cities_db(tmp_path / "g.duckdb")
    con = duckdb.connect(str(path))
    rate = con.execute("SELECT rate FROM gap_rates WHERE type_id = 'beauty'").fetchone()[0]
    assert abs(rate - 100 / 122_000) < 1e-9
    res9 = dict(con.execute("SELECT h3, share FROM gap_share WHERE type_id = 'beauty' AND res = 9").fetchall())
    assert res9[h3.latlng_to_cell(*a, 9)] == 1.0       # miasteczko bez salonów
    assert h3.latlng_to_cell(*b, 9) not in res9        # miasto z salonami
    res8 = dict(con.execute("SELECT h3, share FROM gap_share WHERE type_id = 'beauty' AND res = 8").fetchall())
    assert res8[h3.latlng_to_cell(*a, 8)] == 1.0 and h3.latlng_to_cell(*b, 8) not in res8
    con.close()


def test_build_gaps_without_poi_creates_empty_tables(tmp_path):
    con = duckdb.connect(str(make_db(tmp_path / "e.duckdb", pop={c: 10.0 for c in disk(k=1)}, gaps=True)))
    assert con.execute("SELECT COUNT(*) FROM gap_share").fetchone()[0] == 0
    con.close()

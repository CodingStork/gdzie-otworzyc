"""Testy ulic: ETL (punkty wzdłuż dróg z nazwą) i `street_label` (nazwa lokalizacji w top-5)."""
from pathlib import Path

import duckdb
import pytest

from backend.app import config
from backend.app.analysis.service import street_label
from etl.streets import build_streets_table, extract_streets, sample_line
from tests.conftest import CENTER

TINY = Path(__file__).parent / "fixtures" / "tiny_streets.osm"
LAT, LNG = CENTER
M_LAT = 1 / 111_320      # 1 m szerokości geograficznej w stopniach


def test_sample_line_spacing_and_midpoint():
    # 300 m na północ → 3 punkty po 100 m, w środkach odcinków (50, 150, 250 m)
    pts = sample_line([(50.0, 17.0), (50.0 + 300 * M_LAT, 17.0)], step_m=100)
    assert len(pts) == 3
    assert [round((lat - 50.0) / M_LAT) for lat, _ in pts] == [50, 150, 250]


def test_sample_line_short_way_gets_one_middle_point():
    pts = sample_line([(50.0, 17.0), (50.0 + 30 * M_LAT, 17.0)], step_m=100)
    assert len(pts) == 1 and round((pts[0][0] - 50.0) / M_LAT) == 15


def test_sample_line_follows_bends():
    # L-kształt: 100 m na północ, potem 100 m na wschód; środek całej linii (100 m) to zakręt
    north_100m = 100 / 110_540                # 1° szerokości ≈ 110 540 m (tak liczy sample_line)
    east_100m = 100 / (111_320 * 0.6428)      # cos 50° ≈ 0,6428
    pts = sample_line([(50.0, 17.0), (50.0 + north_100m, 17.0), (50.0 + north_100m, 17.0 + east_100m)], step_m=200)
    assert len(pts) == 1
    assert pts[0][0] == pytest.approx(50.0 + north_100m, abs=1e-5) and pts[0][1] == pytest.approx(17.0, abs=1e-5)


def test_extract_streets_filters_and_samples():
    streets = extract_streets(TINY)
    assert set(streets["name"]) == {"Długa", "Aleja Róż"}          # bez drogi serwisowej i ulicy bez nazwy
    assert (streets["name"] == "Długa").sum() == 3 and (streets["name"] == "Aleja Róż").sum() == 1
    dluga = streets[streets["name"] == "Długa"]
    assert dluga["lat"].between(49.9999, 50.0001).all() and dluga["lng"].between(17.0, 17.003).all()


def test_build_streets_table_sorted_by_lat():
    con = duckdb.connect()
    n = build_streets_table(TINY, con)
    assert n == 4 and con.execute("SELECT COUNT(*) FROM streets").fetchone()[0] == 4
    lats = [r[0] for r in con.execute("SELECT lat FROM streets").fetchall()]
    assert lats == sorted(lats)           # kolejność po szerokości = szybkie zapytania prostokątem


def _con(make_client, streets=(), places=()):
    make_client(streets=list(streets), places=list(places))
    return duckdb.connect(str(config.DB_PATH), read_only=True)


def test_label_street_and_place(make_client):
    con = _con(make_client, [("Długa", LAT, LNG)], [("Zaodrze", "suburb", LAT + 0.004, LNG)])
    assert street_label(con, LAT + 0.0003, LNG) == "ul. Długa, Zaodrze"


def test_label_no_ul_prefix_for_alley_square_etc(make_client):
    for name in ("Aleja Róż", "al. Wojska Polskiego", "Plac Solny", "PL. Zbawiciela", "Rondo Radosława",
                 "Osiedle Słoneczne", "os. Młodych", "Bulwar Nadodrzański", "skwer Kościuszki"):
        con = _con(make_client, [(name, LAT, LNG)])
        assert street_label(con, LAT, LNG) == name, name
        con.close()


def test_label_skips_place_already_in_street_name(make_client):
    con = _con(make_client, [("Zaodrze Wschodnie", LAT, LNG)], [("Zaodrze", "suburb", LAT, LNG)])
    assert street_label(con, LAT, LNG) == "ul. Zaodrze Wschodnie"


def test_label_street_too_far_falls_back_to_place(make_client):
    con = _con(make_client, [("Długa", LAT + 0.003, LNG)], [("Zaodrze", "suburb", LAT, LNG)])   # ulica ~330 m dalej
    assert street_label(con, LAT, LNG) == "Zaodrze"


def test_label_picks_nearest_street(make_client):
    con = _con(make_client, [("Daleka", LAT + 0.0012, LNG), ("Bliska", LAT + 0.0003, LNG)])
    assert street_label(con, LAT, LNG) == "ul. Bliska"


def test_label_without_anything_returns_coordinates(make_client):
    con = _con(make_client)
    assert street_label(con, LAT, LNG) == f"okolice {LAT:.3f}, {LNG:.3f}"

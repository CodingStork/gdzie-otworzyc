import math
from pathlib import Path

import duckdb
import pytest

from etl.buildings import build_building_weights, building_factor, extract_buildings, levels, polygon_area_m2

TINY = Path(__file__).parent / "fixtures" / "tiny.osm"


def test_building_factor():
    assert building_factor("house") == 1.0 and building_factor("yes") == 0.5 and building_factor("garage") == 0.0


def test_levels():
    assert levels({"building:levels": "3"}, "house") == 3
    assert levels({"building:levels": "2.5"}, "house") == 2
    assert levels({"building:levels": "abc"}, "apartments") == 5
    assert levels({}, "residential") == 2 and levels({"building:levels": "99"}, "yes") == 40


def test_polygon_area_square_10m():
    lat0, lng0 = 52.0, 21.0
    dlat, dlng = 10 / 110540, 10 / (111320 * math.cos(math.radians(lat0)))
    sq = [(lat0, lng0), (lat0, lng0 + dlng), (lat0 + dlat, lng0 + dlng), (lat0 + dlat, lng0), (lat0, lng0)]
    assert polygon_area_m2(sq) == pytest.approx(100, rel=0.01)


def test_extract_buildings_weights():
    df = extract_buildings(TINY)
    # yes 100·0,5, house 100, apartments 400·4; garaż (współczynnik 0) i budynek 3×3 m (za mały) pominięte
    assert sorted(df["w"].round()) == [50, 100, 1600]
    assert set(df.columns) == {"lat", "lng", "w"}


def test_build_building_weights_table():
    con = duckdb.connect()
    assert build_building_weights(TINY, con) >= 1
    row = con.execute("SELECT SUM(w), MIN(length(h3)) FROM building_weights").fetchone()
    assert row[0] == pytest.approx(1750, rel=0.01)

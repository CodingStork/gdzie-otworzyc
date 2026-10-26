from pathlib import Path

import duckdb
import h3
import pytest

from etl.osm_poi import build_poi_tables, extract

TINY = Path(__file__).parent / "fixtures" / "tiny.osm"


def test_extract_poi_matches_types():
    poi, _ = extract(TINY)
    assert sorted(poi["type_id"]) == ["barber", "beauty", "diy", "hairdresser"]
    assert set(poi.columns) == {"osm_id", "type_id", "name", "lat", "lng"}
    assert set(poi["osm_id"]) == {"n1", "n2", "w100"}


def test_extract_way_point_is_mean_of_nodes():
    poi, _ = extract(TINY)
    diy = poi[poi["type_id"] == "diy"].iloc[0]
    assert diy["lat"] == pytest.approx(50.0202, abs=1e-6)
    assert diy["lng"] == pytest.approx(17.0202, abs=1e-6)
    assert diy["name"] == "Market Dom"


def test_extract_places():
    _, places = extract(TINY)
    assert len(places) == 1
    row = places.iloc[0]
    assert (row["name"], row["kind"]) == ("Zaodrze", "suburb")
    assert row["lat"] == pytest.approx(50.03)


def test_build_poi_tables_writes_h3_res8():
    con = duckdb.connect()
    counts = build_poi_tables(TINY, con)
    assert counts == {"poi": 4, "places": 1}
    cells = [r[0] for r in con.execute("SELECT h3 FROM poi").fetchall()]
    assert len(cells) == 4 and all(h3.get_resolution(c) == 8 for c in cells)
    assert con.execute("SELECT h3 FROM places").fetchall()[0][0] == h3.latlng_to_cell(50.03, 17.03, 8)

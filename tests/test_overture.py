"""Testy ETL Overture Maps Places: mapowanie kategorii, deduplikacja względem OSM i budowa tabeli `poi`."""
import duckdb
import pandas as pd
import pytest

from backend.app.catalog import TYPES, match_overture
from etl.overture import build_overture_poi, dedupe, normalize_name

LAT, LNG = 51.1, 17.03          # Wrocław
M = 1 / 111_320                 # 1 m szerokości geograficznej w stopniach


def _df(rows):
    """rows: (type_id, name, dlat_m) — punkt przesunięty o dlat_m metrów na północ od LAT, LNG."""
    return pd.DataFrame([{"type_id": t, "name": n, "lat": LAT + d * M, "lng": LNG} for t, n, d in rows],
                        columns=["type_id", "name", "lat", "lng"])


def test_match_overture_categories():
    assert match_overture("beauty_salon") == ["beauty"]
    assert match_overture("nail_salon") == ["beauty", "nails"]          # jeden salon, dwa typy
    assert match_overture("barber") == ["hairdresser", "barber"]
    assert match_overture("pizza_restaurant") == ["restaurant"]
    assert match_overture("hvac_service") == ["installer"]
    assert match_overture("zoo") == [] and match_overture(None) == []


def test_every_type_has_overture_categories():
    assert all(t.overture for t in TYPES.values())


def test_normalize_name_ignores_case_diacritics_and_punctuation():
    assert normalize_name("  Salon „Różana” — Beauty! ") == "salon rozana beauty"
    assert normalize_name(None) == "" and normalize_name(float("nan")) == ""     # pandas oznacza brak nazwy jako NaN


def test_dedupe_same_type_within_50m_is_duplicate():
    osm = _df([("beauty", "Salon Ewa", 0)])
    assert len(dedupe(osm, _df([("beauty", "Zupełnie inna nazwa", 30)]))) == 0


def test_dedupe_other_type_is_kept():
    osm = _df([("beauty", "Salon Ewa", 0)])
    assert len(dedupe(osm, _df([("hairdresser", "Salon Ewa", 30)]))) == 1


def test_dedupe_similar_name_120m_is_duplicate():
    osm = _df([("beauty", "Salon Kosmetyczny Ewa", 0)])
    assert len(dedupe(osm, _df([("beauty", "Salon kosmetyczny EWA", 120)]))) == 0


def test_dedupe_different_name_120m_is_kept():
    osm = _df([("beauty", "Salon Ewa", 0)])
    assert len(dedupe(osm, _df([("beauty", "Studio Urody Marta", 120)]))) == 1


def test_dedupe_far_away_is_kept_even_with_same_name():
    osm = _df([("beauty", "Salon Ewa", 0)])
    assert len(dedupe(osm, _df([("beauty", "Salon Ewa", 400)]))) == 1


def test_dedupe_without_osm_points_keeps_everything():
    ov = _df([("beauty", "A", 0), ("beauty", "B", 10)])
    assert len(dedupe(_df([]), ov)) == 2


def test_dedupe_missing_names_use_distance_only():
    osm = _df([("beauty", None, 0)])
    osm["name"] = float("nan")          # tak pandas wczytuje NULL z bazy
    assert len(dedupe(osm, _df([("beauty", None, 120)]))) == 1         # bez nazw nie ma podstaw do zlania w 120 m
    assert len(dedupe(osm, _df([("beauty", None, 30)]))) == 0


def _raw(path, rows):
    """Surowy wyciąg Overture (kolumny jak w pliku data/raw/overture_places_pl.parquet)."""
    pd.DataFrame([{"id": str(i), "name": n, "cat": c, "lat": LAT + d * M, "lng": LNG}
                  for i, (n, c, d) in enumerate(rows)],
                 columns=["id", "name", "cat", "lat", "lng"]).to_parquet(path)
    return path


def _con_with_osm():
    con = duckdb.connect()
    # tak wygląda `poi` w bazie sprzed v3.1: identyfikator nazywa się osm_id, nie ma kolumny `source`
    con.execute("CREATE TABLE poi (osm_id VARCHAR, type_id VARCHAR, name VARCHAR, lat DOUBLE, lng DOUBLE, h3 VARCHAR)")
    con.execute("INSERT INTO poi VALUES ('n1', 'beauty', 'Salon Ewa', ?, ?, 'x')", [LAT, LNG])
    return con


def test_build_overture_poi_adds_rows_with_source(tmp_path):
    con = _con_with_osm()
    raw = _raw(tmp_path / "o.parquet", [("Salon Ewa", "beauty_salon", 20),      # duplikat OSM
                                         ("Paznokcie Ola", "nail_salon", 500),  # beauty + nails
                                         ("Zoo", "zoo", 10)])                   # kategoria spoza katalogu
    counts = build_overture_poi(raw, con)
    assert counts["before_dedup"] == 3 and counts["after_dedup"] == 2 and counts["by_type"] == {"beauty": 1, "nails": 1}
    rows = con.execute("SELECT type_id, source, source_id FROM poi ORDER BY source, type_id").fetchall()
    assert rows == [("beauty", "osm", "n1"), ("beauty", "overture", "1"), ("nails", "overture", "1")]
    assert con.execute("SELECT COUNT(*) FROM poi WHERE h3 IS NULL").fetchone()[0] == 0


def test_build_overture_poi_is_repeatable(tmp_path):
    con = _con_with_osm()
    raw = _raw(tmp_path / "o.parquet", [("Paznokcie Ola", "nail_salon", 500)])
    build_overture_poi(raw, con)
    build_overture_poi(raw, con)
    assert con.execute("SELECT COUNT(*) FROM poi WHERE source = 'overture'").fetchone()[0] == 2


def test_build_overture_poi_migrates_old_poi_table(tmp_path):
    """Baza sprzed v3.1 nie ma kolumny `source` (a identyfikator nazywał się osm_id) — krok sam ją uzupełnia."""
    con = _con_with_osm()
    build_overture_poi(_raw(tmp_path / "o.parquet", []), con)
    cols = {r[0] for r in con.execute("SELECT column_name FROM information_schema.columns WHERE table_name='poi'").fetchall()}
    assert {"source", "source_id"} <= cols and "osm_id" not in cols
    assert con.execute("SELECT source FROM poi").fetchall() == [("osm",)]


@pytest.mark.parametrize("n", [0, 1])
def test_build_overture_poi_empty_ok(tmp_path, n):
    con = _con_with_osm()
    raw = _raw(tmp_path / "o.parquet", [("Zoo", "zoo", 0)] * n)
    assert build_overture_poi(raw, con)["after_dedup"] == 0

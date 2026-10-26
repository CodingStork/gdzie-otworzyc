from pathlib import Path

import duckdb
import pandas as pd
import pytest

from etl.permits import (
    NOTIF_COLUMNS,
    PERMIT_COLUMNS,
    UnexpectedHeader,
    build_permits_raw,
    normalize_obreb_id,
    parse_notifications,
    parse_permits,
)

FIX = Path(__file__).parent / "fixtures"
PERMITS = FIX / "gunb_permits_sample.csv"
NOTIFS = FIX / "gunb_notifications_sample.csv"


def test_normalize_obreb_id():
    assert normalize_obreb_id("160602_4", "38") == "160602_4.0038"
    assert normalize_obreb_id("160602_4", "0038") == "160602_4.0038"
    assert normalize_obreb_id("160602_4", "12a") == "160602_4.0012"    # cyfry wiodące
    assert normalize_obreb_id("", "0038") is None
    assert normalize_obreb_id("160602_4", "") is None
    assert normalize_obreb_id("160602_4", "abc") is None


def test_duplicate_column_names_are_renamed():
    assert PERMIT_COLUMNS.count("cecha") == 0 and "cecha_1" in PERMIT_COLUMNS and "cecha_2" in PERMIT_COLUMNS
    assert "numer_gunb" in PERMIT_COLUMNS and "jednosta_numer_ew" in PERMIT_COLUMNS
    assert "numer_ewidencyjny_system" in NOTIF_COLUMNS and "rodzaj_zam_budowlanego" in NOTIF_COLUMNS


def test_parse_permits_keeps_only_new_residential():
    df = parse_permits(PERMITS)
    # odpadają: zmiana pozwolenia, kategoria XXVI, rozbudowa; zostają 6 wierszy (w tym duplikat i brak obrębu)
    assert sorted(df["source_id"]) == sorted([
        "ST-OP-TE/WNIOSEK/1/2024", "ST-OP-TE/WNIOSEK/2/2025", "ST-OP-TE/WNIOSEK/6/2024",
        "ST-OP-TE/WNIOSEK/7/2024", "ST-OP-TE/WNIOSEK/1/2024", "ST-OP-TE/WNIOSEK/9/2023"])
    assert set(df["source"]) == {"pozwolenie"}
    assert set(df.columns) == {"source_id", "source", "kind", "date", "obreb_id", "terc"}
    assert pd.api.types.is_datetime64_any_dtype(df["date"])


def test_parse_permits_fields():
    df = parse_permits(PERMITS).set_index("source_id")
    sf = df.loc["ST-OP-TE/WNIOSEK/2/2025"]
    assert sf["kind"] == "mf" and sf["date"] == pd.Timestamp("2025-01-10") and sf["obreb_id"] == "161101_1.0003"
    assert sf["terc"] == "1611011"
    first = df.loc["ST-OP-TE/WNIOSEK/6/2024"]
    assert first["kind"] == "sf" and first["obreb_id"] == "160602_4.0038"     # obręb "38" dopełniony zerami


def test_parse_permits_multiline_field_parses_as_one_row():
    df = parse_permits(PERMITS)
    assert (df["source_id"] == "ST-OP-TE/WNIOSEK/6/2024").sum() == 1


def test_parse_permits_missing_obreb_is_none_and_date_fallback():
    df = parse_permits(PERMITS).set_index("source_id")
    assert pd.isna(df.loc["ST-OP-TE/WNIOSEK/7/2024", "obreb_id"])
    # brak daty decyzji → data wpłynięcia wniosku
    assert df.loc["ST-OP-TE/WNIOSEK/9/2023", "date"] == pd.Timestamp("2023-05-05")


def test_parse_notifications():
    df = parse_notifications(NOTIFS)
    assert sorted(df["source_id"]) == ["ST-PM-TE/ZGŁOSZENIE/100/2023", "ST-PM-TE/ZGŁOSZENIE/101/2023",
                                       "ST-PM-TE/ZGŁOSZENIE/104/2023"]
    d = df.set_index("source_id")
    assert set(df["source"]) == {"zgloszenie"}
    assert d.loc["ST-PM-TE/ZGŁOSZENIE/101/2023", "kind"] == "mf"
    assert d.loc["ST-PM-TE/ZGŁOSZENIE/100/2023", "date"] == pd.Timestamp("2023-06-01")
    assert d.loc["ST-PM-TE/ZGŁOSZENIE/104/2023", "obreb_id"] == "221102_4.0007"


def test_changed_header_raises(tmp_path):
    bad = tmp_path / "bad.csv"
    text = PERMITS.read_text(encoding="utf-8-sig").replace("numer_gunb", "numer_gunb_NOWY", 1)
    bad.write_text(text, encoding="utf-8-sig")
    with pytest.raises(UnexpectedHeader) as e:
        parse_permits(bad)
    assert "numer_gunb_NOWY" in str(e.value) and "numer_gunb" in str(e.value)
    with pytest.raises(UnexpectedHeader):
        parse_notifications(PERMITS)     # plik pozwoleń przekazany jako zgłoszenia


def test_build_permits_raw_dedups_and_drops_missing_obreb():
    con = duckdb.connect()
    n = build_permits_raw([PERMITS], [NOTIFS], con)
    # pozwolenia: 1, 2, 6, 9 (7 bez obrębu odpada, duplikat 1 scalony) + zgłoszenia: 3
    assert n == 7
    rows = con.execute("SELECT source_id, source, kind, CAST(date AS VARCHAR), obreb_id, terc FROM permits_raw").fetchall()
    assert len({r[0] for r in rows}) == 7
    assert all(r[4] is not None for r in rows)
    assert con.execute("SELECT COUNT(*) FROM permits_raw WHERE source='zgloszenie'").fetchall()[0][0] == 3


def test_build_permits_raw_is_replaceable():
    con = duckdb.connect()
    build_permits_raw([PERMITS], [NOTIFS], con)
    assert build_permits_raw([PERMITS], [], con) == 4      # drugie wywołanie nadpisuje tabelę

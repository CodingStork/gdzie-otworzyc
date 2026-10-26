import duckdb
import h3
import pandas as pd
import pytest

from etl.population import (
    POP_COLUMNS,
    build_hex_pop,
    cells_to_hex,
    impute_subcategories,
    load_polish_cells,
    parse_grd_id,
)


def test_parse_grd_id():
    assert parse_grd_id("CRS3035RES1000mN2684000E4285000") == (4285000, 2684000)


def test_impute_uses_observed_share():
    df = pd.DataFrame({"T": [100, 10], "F": [60, -9999], "M": [40, -9999],
                       "Y_LT15": [10, -9999], "Y_1564": [70, 5], "Y_GE65": [20, -9999]})
    out = impute_subcategories(df)
    assert out.loc[1, "F"] == pytest.approx(6.0)     # 10 × 60/100
    assert out.loc[1, "Y_1564"] == 5                 # znane wartości bez zmian
    assert (out[["F", "M", "Y_LT15", "Y_GE65"]] >= 0).all().all()


def test_cells_to_hex_preserves_sum():
    df = pd.DataFrame({"E": [4285000, 5000000], "N": [3300000, 3200000], "T": [1000, 250],
                       "F": [500, 125], "M": [500, 125], "Y_LT15": [150, 40],
                       "Y_1564": [650, 160], "Y_GE65": [200, 50]})
    out = cells_to_hex(df, res=8, n=5)
    assert out["pop_total"].sum() == pytest.approx(1250)
    assert out["h3"].map(h3.get_resolution).eq(8).all()
    assert len(out) >= 2                     # komórka 1 km² rozkłada się na kilka heksagonów
    assert set(POP_COLUMNS.values()) <= set(out.columns)


def _write_census_parquet(path):
    """Mały plik w formacie Eurostatu: komórki PL, granica CZ-PL, DE (do odrzucenia), pusta komórka."""
    df = pd.DataFrame({
        "GRD_ID": [
            "CRS3035RES1000mN3300000E4885000",   # PL, zwykła
            "CRS3035RES1000mN3301000E4885000",   # PL, podkategorie ukryte
            "CRS3035RES1000mN3302000E4885000",   # CZ-PL (graniczna) — zostaje
            "CRS3035RES1000mN3100000E4300000",   # DE — odpada
            "CRS3035RES1000mN3303000E4885000",   # PL, T = 0 — odpada
        ],
        "T": [100, 20, 50, 999, 0],
        "M": [48, -9999, 25, 500, 0],
        "F": [52, -9999, 25, 499, 0],
        "Y_LT15": [15, -9999, 8, 100, 0],
        "Y_1564": [65, 13, 32, 600, 0],
        "Y_GE65": [20, -9999, 10, 299, 0],
        "CNTR_ID": ["PL", "PL", "CZ-PL", "DE", "PL"],
        "EMP": [1, 1, 1, 1, 1],   # kolumna zbędna — ma być pominięta
    })
    df.to_parquet(path)


def test_load_polish_cells_filters_country_and_empty(tmp_path):
    p = tmp_path / "c.parquet"
    _write_census_parquet(p)
    cells = load_polish_cells(p)
    assert list(cells["T"]) == [100, 20, 50]
    assert list(cells.columns) == ["E", "N", "T", "F", "M", "Y_LT15", "Y_1564", "Y_GE65"]
    assert cells.loc[0, "E"] == 4885000 and cells.loc[0, "N"] == 3300000


def test_build_hex_pop_creates_table_and_keeps_total(tmp_path):
    p = tmp_path / "c.parquet"
    _write_census_parquet(p)
    con = duckdb.connect()
    n = build_hex_pop(p, con)
    assert n == con.execute("SELECT COUNT(*) FROM hex_pop_r8").fetchone()[0] > 3
    total = con.execute("SELECT SUM(pop_total) FROM hex_pop_r8").fetchone()[0]
    assert total == pytest.approx(170)            # 100 + 20 + 50
    # imputacja: komórka z ukrytymi podkategoriami nie daje wartości ujemnych
    assert con.execute("SELECT MIN(pop_f) FROM hex_pop_r8").fetchone()[0] >= 0
    # klucz główny: h3 unikalne
    assert con.execute("SELECT COUNT(DISTINCT h3) FROM hex_pop_r8").fetchone()[0] == n

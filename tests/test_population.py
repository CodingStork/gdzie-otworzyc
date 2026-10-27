import duckdb
import h3
import pandas as pd
import pytest

from pyproj import Transformer

from etl.population import (
    POP_COLUMNS,
    build_hex_pop,
    cells_to_hex,
    dasymetric_to_hex,
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
    n = build_hex_pop(p, con)                    # brak building_weights → rozkład równomierny (z ostrzeżeniem)
    assert n == con.execute("SELECT COUNT(*) FROM hex_pop_r9").fetchone()[0] > 3
    total = con.execute("SELECT SUM(pop_total) FROM hex_pop_r9").fetchone()[0]
    assert total == pytest.approx(170)            # 100 + 20 + 50
    # imputacja: komórka z ukrytymi podkategoriami nie daje wartości ujemnych
    assert con.execute("SELECT MIN(pop_f) FROM hex_pop_r9").fetchone()[0] >= 0
    # klucz główny: h3 unikalne, rozdzielczość 9
    assert con.execute("SELECT COUNT(DISTINCT h3) FROM hex_pop_r9").fetchone()[0] == n
    assert con.execute("SELECT MIN(length(h3)), MAX(length(h3)) FROM hex_pop_r9").fetchone() == (15, 15)
    assert con.execute("SELECT rows FROM meta WHERE source = 'dasymetria'").fetchone()[0] == 0   # 0‰ przez budynki


def test_build_hex_pop_uses_building_weights(tmp_path):
    p = tmp_path / "c.parquet"
    _write_census_parquet(p)
    cells = load_polish_cells(p)
    row = cells.iloc[0]                           # komórka PL "zwykła" (T = 100)
    a = _hex_at(row["E"] + 500, row["N"] + 500)
    con = duckdb.connect()
    con.execute("CREATE TABLE building_weights (cell_e INTEGER, cell_n INTEGER, h3 VARCHAR, w DOUBLE)")
    con.execute("INSERT INTO building_weights VALUES (?, ?, ?, 10.0)", [int(row["E"]), int(row["N"]), a])
    build_hex_pop(p, con)
    assert con.execute("SELECT pop_total FROM hex_pop_r9 WHERE h3 = ?", [a]).fetchone()[0] == pytest.approx(100)
    assert con.execute("SELECT SUM(pop_total) FROM hex_pop_r9").fetchone()[0] == pytest.approx(170)
    assert con.execute("SELECT rows FROM meta WHERE source = 'dasymetria'").fetchone()[0] == 588   # 100 z 170 ≈ 588‰


_TO_WGS = Transformer.from_crs(3035, 4326, always_xy=True)


def _hex_at(e: float, n: float) -> str:
    """Heksagon res 9 w punkcie (E, N) układu EPSG:3035."""
    lng, lat = _TO_WGS.transform(e, n)
    return h3.latlng_to_cell(lat, lng, 9)


def _cell_df(t=1000):
    return pd.DataFrame({"E": [5000000], "N": [3200000], "T": [t], "F": [t / 2], "M": [t / 2],
                         "Y_LT15": [t * 0.1], "Y_1564": [t * 0.7], "Y_GE65": [t * 0.2]})


def test_dasymetric_follows_buildings():
    a, b = _hex_at(5000100, 3200100), _hex_at(5000900, 3200900)
    assert a != b
    w = pd.DataFrame({"cell_e": [5000000, 5000000], "cell_n": [3200000, 3200000], "h3": [a, b], "w": [300.0, 100.0]})
    out, share = dasymetric_to_hex(_cell_df(), w)
    got = out.set_index("h3")["pop_total"]
    assert got[a] == pytest.approx(750) and got[b] == pytest.approx(250) and share == 1.0
    assert out.set_index("h3")["pop_ge65"][a] == pytest.approx(150)    # podkategorie dzielone tak samo


def test_dasymetric_fallback_uniform_keeps_sum():
    # komórka bez budynków → rozkład równomierny, suma zachowana, udział 0
    no_w = pd.DataFrame({"cell_e": [], "cell_n": [], "h3": [], "w": []})
    out, share = dasymetric_to_hex(_cell_df(), no_w)
    assert out["pop_total"].sum() == pytest.approx(1000) and share == 0.0
    assert out["h3"].map(h3.get_resolution).eq(9).all()


def test_dasymetric_mixed_cells_share():
    cells = pd.concat([_cell_df(1000), _cell_df(1000).assign(E=5001000)], ignore_index=True)
    w = pd.DataFrame({"cell_e": [5000000], "cell_n": [3200000], "h3": [_hex_at(5000500, 3200500)], "w": [5.0]})
    out, share = dasymetric_to_hex(cells, w)
    assert out["pop_total"].sum() == pytest.approx(2000) and share == pytest.approx(0.5)

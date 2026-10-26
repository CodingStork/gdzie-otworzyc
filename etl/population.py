"""Ludność: siatka spisu 2021 (Eurostat, kwadraty 1 km, EPSG:3035) → heksagony H3 rozdzielczości 8.

Główna idea to INTERPOLACJA POWIERZCHNIOWA (areal interpolation): mamy liczby ludzi
w kwadratach, a chcemy je w heksagonach, które kwadratów nie pokrywają "równo".
Rozwiązanie: każdy kwadrat dzielimy na drobną siatkę punktów, każdy punkt dostaje
równy ułamek ludności kwadratu i trafia do heksagonu, w którym leży.
"""
import duckdb
import h3
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from pyproj import Transformer

# Kolumny spisu Eurostatu → nazwy w naszej bazie.
POP_COLUMNS = {
    "T": "pop_total", "F": "pop_f", "M": "pop_m",
    "Y_LT15": "pop_lt15", "Y_1564": "pop_1564", "Y_GE65": "pop_ge65",
}
SUBCATEGORIES = ["F", "M", "Y_LT15", "Y_1564", "Y_GE65"]

CELL_SIZE_M = 1000  # bok komórki siatki spisu


def parse_grd_id(grd_id: str) -> tuple[int, int]:
    """'CRS3035RES1000mN2684000E4285000' → (easting, northing) lewego dolnego rogu komórki.

    Komórka to kwadrat [E, E+1000] × [N, N+1000] w układzie EPSG:3035 (ETRS89-LAEA).
    """
    n_part, e_part = grd_id.split("N")[1].split("E")
    return int(e_part), int(n_part)


def load_polish_cells(parquet_path) -> pd.DataFrame:
    """Wczytuje z parqueta Eurostatu tylko komórki Polski z ludnością (T > 0).

    Komórki przy granicy mają CNTR_ID typu 'CZ-PL' — też je bierzemy, bo leżą
    częściowo w Polsce (filtr: 'PL' wśród części kodu rozdzielonego myślnikiem).
    """
    cols = ["GRD_ID", "CNTR_ID", *POP_COLUMNS.keys()]
    df = pq.read_table(parquet_path, columns=cols).to_pandas()  # tylko potrzebne kolumny
    is_pl = df["CNTR_ID"].str.split("-").map(lambda parts: "PL" in parts)
    df = df[is_pl & (df["T"] > 0)].reset_index(drop=True)
    # GRD_ID zawiera współrzędne: ...N<northing>E<easting>
    coords = df["GRD_ID"].str.extract(r"N(?P<N>\d+)E(?P<E>\d+)").astype("int64")
    df["E"], df["N"] = coords["E"], coords["N"]
    return df[["E", "N", *POP_COLUMNS.keys()]]


def impute_subcategories(df: pd.DataFrame) -> pd.DataFrame:
    """Uzupełnia ukryte podkategorie (wartości ujemne: -9999 brak danych, -8888 poufne).

    Eurostat ukrywa M/F/grupy wiekowe w bardzo małych komórkach (ochrona prywatności),
    ale łączna ludność T jest zawsze znana. Brakującą podkategorię szacujemy jako
    T × udział tej podkategorii w komórkach, gdzie jest znana (liczony z danych).
    """
    out = df.copy().astype({"T": "float64", **{c: "float64" for c in SUBCATEGORIES}})
    for col in SUBCATEGORIES:
        known = out[col] >= 0
        share = out.loc[known, col].sum() / out.loc[known, "T"].sum()
        out.loc[~known, col] = out.loc[~known, "T"] * share
    return out


def cells_to_hex(df: pd.DataFrame, res: int = 8, n: int = 5, chunk_cells: int = 20_000) -> pd.DataFrame:
    """Rozkłada ludność komórek 1 km na heksagony H3 (interpolacja powierzchniowa).

    Każdą komórkę dzielimy na n×n podkomórek (domyślnie 5×5 = co 200 m). Środek każdej
    podkomórki niesie 1/n² wartości komórki — to założenie o RÓWNOMIERNYM rozkładzie
    ludności wewnątrz komórki (uproszczenie: w rzeczywistości ludzie mieszkają
    w zabudowie, nie w lesie). Punkty przeliczamy z EPSG:3035 na WGS84 (lat/lng),
    bo H3 przyjmuje współrzędne geograficzne, i sumujemy wartości w heksagonach.
    Suma ludności jest zachowana (każdy punkt trafia do dokładnie jednego heksagonu).
    """
    transformer = Transformer.from_crs(3035, 4326, always_xy=True)
    offsets = (np.arange(n) + 0.5) * CELL_SIZE_M / n  # środki podkomórek w obrębie komórki
    off_e, off_n = np.meshgrid(offsets, offsets)
    off_e, off_n = off_e.ravel(), off_n.ravel()       # n² par przesunięć
    value_cols = list(POP_COLUMNS.keys())

    parts = []
    # Przetwarzamy porcjami, żeby nie trzymać naraz ~5 mln napisów H3 w pamięci.
    for start in range(0, len(df), chunk_cells):
        chunk = df.iloc[start:start + chunk_cells]
        e = (chunk["E"].to_numpy()[:, None] + off_e[None, :]).ravel()
        nn = (chunk["N"].to_numpy()[:, None] + off_n[None, :]).ravel()
        lng, lat = transformer.transform(e, nn)
        cells = [h3.latlng_to_cell(la, lo, res) for la, lo in zip(lat, lng)]
        values = np.repeat(chunk[value_cols].to_numpy(dtype="float64"), n * n, axis=0) / (n * n)
        part = pd.DataFrame(values, columns=list(POP_COLUMNS.values()))
        part["h3"] = cells
        parts.append(part.groupby("h3", sort=False).sum())

    out = pd.concat(parts).groupby("h3").sum().reset_index()
    return out[["h3", *POP_COLUMNS.values()]]


def build_hex_pop(parquet_path, con: duckdb.DuckDBPyConnection) -> int:
    """Cały krok: parquet → komórki PL → imputacja → heksagony → tabela hex_pop_r8."""
    cells = load_polish_cells(parquet_path)
    cells = impute_subcategories(cells)
    hexes = cells_to_hex(cells, res=8, n=5)

    # Kontrola: interpolacja nie może zgubić ani dodać ludzi.
    in_total, out_total = cells["T"].sum(), hexes["pop_total"].sum()
    if abs(in_total - out_total) > 0.001 * in_total:
        raise ValueError(f"Suma ludności zmieniła się: {in_total} → {out_total}")
    print(f"hex_pop_r8: {len(hexes)} heksagonów, ludność {out_total:,.0f}")

    con.execute("""
        CREATE OR REPLACE TABLE hex_pop_r8 (
            h3 VARCHAR PRIMARY KEY,
            pop_total DOUBLE, pop_f DOUBLE, pop_m DOUBLE,
            pop_lt15 DOUBLE, pop_1564 DOUBLE, pop_ge65 DOUBLE
        )""")
    con.register("hexes_df", hexes)
    con.execute("INSERT INTO hex_pop_r8 SELECT * FROM hexes_df")
    con.unregister("hexes_df")
    return len(hexes)

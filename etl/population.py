"""Ludność: siatka spisu 2021 (Eurostat, kwadraty 1 km, EPSG:3035) → heksagony H3 rozdzielczości 9.

Mamy liczby ludzi w kwadratach 1 km, a chcemy je w heksagonach (res 9, ~0,1 km²), które
kwadratów nie pokrywają "równo". Są dwie metody:

1. METODA DASYMETRYCZNA (główna): ludność kwadratu rozkładamy proporcjonalnie do wag budynków
   mieszkalnych z OpenStreetMap (tabela `building_weights`, patrz `buildings.py`). Ludzie
   mieszkają w domach, a nie w lesie — więc heksagon z blokami dostaje dużo, a z polem nic.
2. INTERPOLACJA POWIERZCHNIOWA (zapasowa): dla kwadratów, w których OSM nie ma żadnych budynków,
   kwadrat dzielimy na drobną siatkę punktów; każdy punkt dostaje równy ułamek ludności i trafia
   do heksagonu, w którym leży (założenie: ludność rozłożona równomiernie).

W obu metodach suma ludności jest zachowana.
"""
import duckdb
import h3
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from pyproj import Transformer

from etl.aggregate import table_exists
from etl.meta import record_meta

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


def cells_to_hex(df: pd.DataFrame, res: int = 9, n: int = 5, chunk_cells: int = 20_000) -> pd.DataFrame:
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


def dasymetric_to_hex(cells: pd.DataFrame, weights: pd.DataFrame, res: int = 9,
                      n_uniform: int = 10) -> tuple[pd.DataFrame, float]:
    """Rozkłada ludność komórek spisu na heksagony metodą dasymetryczną.

    `cells`: kolumny E, N, T, F, M, Y_LT15, Y_1564, Y_GE65 (jak z `impute_subcategories`);
    `weights`: cell_e, cell_n, h3, w — waga budynków komórki spisu (cell_e, cell_n) w heksagonie h3.

    Dla komórki z sumą wag Σw > 0 heksagon h dostaje ułamek w_h / Σw całej ludności komórki.
    Komórki bez budynków (Σw = 0 lub brak w tabeli) rozkładamy równomiernie (`cells_to_hex`,
    siatka n_uniform × n_uniform punktów). Zwraca (heksagony, udział ludności rozłożonej przez budynki 0–1).
    """
    value_cols = list(POP_COLUMNS.keys())
    w = pd.DataFrame({"E": weights["cell_e"].astype("int64"), "N": weights["cell_n"].astype("int64"),
                      "h3": weights["h3"], "w": weights["w"].astype("float64")})
    w = w[w["w"] > 0]
    w["w_sum"] = w.groupby(["E", "N"])["w"].transform("sum")

    # inner join: tylko komórki spisu, które mają budynki; każdy wiersz = (komórka, heksagon z budynkami)
    with_w = cells.merge(w, on=["E", "N"], how="inner")
    parts = []
    if not with_w.empty:
        fraction = (with_w["w"] / with_w["w_sum"]).to_numpy()
        values = with_w[value_cols].to_numpy(dtype="float64") * fraction[:, None]
        part = pd.DataFrame(values, columns=list(POP_COLUMNS.values()))
        part["h3"] = with_w["h3"].to_numpy()
        parts.append(part.groupby("h3").sum())

    marked = cells[["E", "N"]].merge(w[["E", "N"]].drop_duplicates(), on=["E", "N"], how="left", indicator=True)
    has_buildings = marked["_merge"].eq("both").to_numpy()      # które komórki spisu mają budynki
    rest = cells[~has_buildings]
    if not rest.empty:
        parts.append(cells_to_hex(rest, res=res, n=n_uniform).set_index("h3"))

    total = cells["T"].sum()
    share = float(cells.loc[has_buildings, "T"].sum() / total) if total > 0 else 0.0
    out = pd.concat(parts).groupby("h3").sum().reset_index() if parts else pd.DataFrame(
        columns=["h3", *POP_COLUMNS.values()])
    return out[["h3", *POP_COLUMNS.values()]], share


def build_hex_pop(parquet_path, con: duckdb.DuckDBPyConnection) -> int:
    """Cały krok: parquet → komórki PL → imputacja → ludność w heksagonach res 9 → tabela hex_pop_r9.

    Jeśli istnieje tabela `building_weights` (krok `buildings`), używamy metody dasymetrycznej;
    jeśli nie — rozkładamy równomiernie (z ostrzeżeniem). Udział ludności rozłożonej przez budynki
    zapisujemy w `meta` (source="dasymetria", rows = promile), żeby kontrola jakości mogła go sprawdzić.
    """
    cells = load_polish_cells(parquet_path)
    cells = impute_subcategories(cells)
    if table_exists(con, "building_weights"):
        weights = con.execute("SELECT cell_e, cell_n, h3, w FROM building_weights").df()
    else:
        print("UWAGA: brak tabeli building_weights — ludność rozłożona równomiernie (uruchom krok 'buildings')", flush=True)
        weights = pd.DataFrame({"cell_e": [], "cell_n": [], "h3": [], "w": []})
    hexes, share = dasymetric_to_hex(cells, weights, res=9)

    # Kontrola: rozkład nie może zgubić ani dodać ludzi.
    in_total, out_total = cells["T"].sum(), hexes["pop_total"].sum()
    if abs(in_total - out_total) > 0.001 * in_total:
        raise ValueError(f"Suma ludności zmieniła się: {in_total} → {out_total}")
    print(f"hex_pop_r9: {len(hexes)} heksagonów, ludność {out_total:,.0f}, "
          f"rozłożona przez budynki: {share:.1%}", flush=True)

    con.execute("""
        CREATE OR REPLACE TABLE hex_pop_r9 (
            h3 VARCHAR PRIMARY KEY,
            pop_total DOUBLE, pop_f DOUBLE, pop_m DOUBLE,
            pop_lt15 DOUBLE, pop_1564 DOUBLE, pop_ge65 DOUBLE
        )""")
    con.register("hexes_df", hexes)
    con.execute("INSERT INTO hex_pop_r9 SELECT * FROM hexes_df")
    con.unregister("hexes_df")
    record_meta(con, "dasymetria", "", int(round(share * 1000)))
    return len(hexes)

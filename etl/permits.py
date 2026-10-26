"""Rejestr pozwoleń i zgłoszeń budowy (GUNB RWDZ) → tabela `permits_raw`.

Dwa różne formaty CSV (pozwolenia na budowę i zgłoszenia), więc dwa parsery o wspólnym wyniku:
    source_id, source ("pozwolenie"|"zgloszenie"), kind ("sf"|"mf"), date, obreb_id, terc
kind: sf = budynek jednorodzinny (kategoria I), mf = wielorodzinny (kategoria XIII).
obreb_id to identyfikator obrębu ewidencyjnego, np. "160602_4.0038" — geokodujemy go później
(geocode_obreby.py), bo dokładnych działek są miliony, a obrębów tylko kilkadziesiąt tysięcy.
"""
import csv

import duckdb
import pandas as pd

# Nagłówki z docs/zrodla-danych.md. Kolumna `cecha` występuje w plikach dwa razy → cecha_1, cecha_2.
PERMIT_COLUMNS = [
    "numer_urzad", "numer_gunb", "nazwa_organu", "adres_organu", "data_wplywu_wniosku", "numer_decyzji_urzedu",
    "data_wydania_decyzji", "nazwa_inwestor", "wojewodztwo", "miasto", "terc", "cecha_1", "cecha_2", "ulica",
    "ulica_dalej", "nr_domu", "rodzaj_inwestycji", "kategoria", "nazwa_zamierzenia_bud", "nazwa_zam_budowlanego",
    "kubatura", "projektant_nazwisko", "projektant_imie", "projektant_numer_uprawnien", "jednosta_numer_ew",
    "obreb_numer", "numer_dzialki", "numer_arkusza_dzialki", "jednostka_stara_numeracja_z_wniosku",
    "stara_numeracja_obreb_z_wnioskiu", "stara_numeracja_dzialka_z_wniosku",
]
NOTIF_COLUMNS = [
    "numer_ewidencyjny_system", "numer_ewidencyjny_urzad", "data_wplywu_wniosku_do_urzedu", "nazwa_organu",
    "wojewodztwo_objekt", "obiekt_kod_pocztowy", "miasto", "terc", "cecha_1", "cecha_2", "ulica", "ulica_dalej",
    "nr_domu", "kategoria", "nazwa_zam_budowlanego", "rodzaj_zam_budowlanego", "kubatura", "stan",
    "jednostki_numer", "obreb_numer", "numer_dzialki", "numer_arkusza_dzialki", "nazwisko_projektanta",
    "imie_projektanta", "projektant_numer_uprawnien", "projektant_pozostali",
]
KIND_BY_CATEGORY = {"I": "sf", "XIII": "mf"}
OUTPUT_COLUMNS = ["source_id", "source", "kind", "date", "obreb_id", "terc"]
CHUNK_ROWS = 300_000
MIN_DATE = pd.Timestamp("2016-01-01")   # rejestr RWDZ obejmuje dane od 2016 r.


class UnexpectedHeader(ValueError):
    """Nagłówek CSV różni się od oczekiwanego (GUNB zmienił format?)."""


def normalize_obreb_id(jednostka: str, obreb: str) -> str | None:
    """('160602_4', '38') → '160602_4.0038'. Brak jednostki albo cyfr w numerze obrębu → None.

    Numer obrębu bywa zapisany z dopiskami (np. '12a') — bierzemy cyfry wiodące.
    """
    jednostka = (jednostka or "").strip()
    digits = ""
    for ch in (obreb or "").strip():
        if not ch.isdigit():
            break
        digits += ch
    if not jednostka or not digits:
        return None
    return f"{jednostka}.{digits.zfill(4)}"


def _check_header(path, expected: list[str]) -> None:
    """Porównuje pierwszy wiersz pliku z oczekiwanym nagłówkiem; rozbieżność → UnexpectedHeader."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        actual = next(csv.reader(f, delimiter=";", quotechar='"'))
    seen: dict[str, int] = {}
    renamed = []
    for name in actual:                       # duplikaty: cecha, cecha → cecha_1, cecha_2
        seen[name] = seen.get(name, 0) + 1
    counter: dict[str, int] = {}
    for name in actual:
        if seen[name] > 1:
            counter[name] = counter.get(name, 0) + 1
            name = f"{name}_{counter[name]}"
        renamed.append(name)
    if renamed != expected:
        missing = [c for c in expected if c not in renamed]
        extra = [c for c in renamed if c not in expected]
        raise UnexpectedHeader(f"{path}: nagłówek różni się od oczekiwanego. Brakuje: {missing}, nadmiarowe: {extra}")


def _read_chunks(path, columns: list[str], use: list[str]):
    """Czyta CSV porcjami, zwracając tylko kolumny `use` (jako tekst).

    Pola mogą zawierać znaki nowej linii w cudzysłowach, więc czytamy parserem CSV (pandas),
    a nie linia po linii. Nagłówek podstawiamy własny (zduplikowane nazwy kolumn).
    """
    _check_header(path, columns)
    yield from pd.read_csv(path, sep=";", dtype=str, keep_default_na=False, encoding="utf-8-sig", quotechar='"',
                           header=None, skiprows=1, names=columns, usecols=use, chunksize=CHUNK_ROWS)


def _finish(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """Typy wyjściowe: data jako datetime (nieczytelne daty → wiersz odrzucony), kind z kategorii."""
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d %H:%M:%S", errors="coerce")
    # Daty spoza 2016–dziś to literówki w rejestrze. Zostawione, przesunęłyby okno czasowe analizy
    # (liczone od najnowszej daty w danych) i wyzerowały wszystkie wyniki z pozwoleń.
    in_range = df["date"].between(MIN_DATE, pd.Timestamp.today().normalize())
    if (~in_range).any():
        print(f"pozwolenia: odrzucono {int((~in_range).sum())} wierszy z nieprawidłową datą", flush=True)
    df = df[in_range]
    df["kind"] = df["kategoria"].map(KIND_BY_CATEGORY)
    df["source"] = source
    df["obreb_id"] = [normalize_obreb_id(j, o) for j, o in zip(df["jednostka"], df["obreb"])]
    return df[OUTPUT_COLUMNS].reset_index(drop=True)


def parse_permits(path) -> pd.DataFrame:
    """Pozwolenia na budowę: kategoria I/XIII, „budowa nowego…”, bez zmian wcześniejszych pozwoleń."""
    use = ["numer_gunb", "data_wplywu_wniosku", "data_wydania_decyzji", "terc", "kategoria",
           "nazwa_zamierzenia_bud", "nazwa_zam_budowlanego", "jednosta_numer_ew", "obreb_numer"]
    parts = []
    for chunk in _read_chunks(path, PERMIT_COLUMNS, use):
        chunk = chunk[chunk["kategoria"].isin(KIND_BY_CATEGORY)]
        is_new = chunk["nazwa_zamierzenia_bud"].str.strip().str.lower().str.startswith("budowa nowego")
        # ~5% wierszy „budowa nowego” to zmiany już wydanych pozwoleń — liczyłyby ten sam dom drugi raz
        is_change = chunk["nazwa_zam_budowlanego"].str.lower().str.contains("zmian", regex=False)
        chunk = chunk[is_new & ~is_change]
        chunk = chunk.assign(
            source_id=chunk["numer_gunb"],
            # data decyzji; gdy pusta — data wpłynięcia wniosku
            date=chunk["data_wydania_decyzji"].where(chunk["data_wydania_decyzji"] != "", chunk["data_wplywu_wniosku"]),
            jednostka=chunk["jednosta_numer_ew"], obreb=chunk["obreb_numer"])
        parts.append(_finish(chunk, "pozwolenie"))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=OUTPUT_COLUMNS)


def parse_notifications(path) -> pd.DataFrame:
    """Zgłoszenia budowy (bez pozwolenia). UWAGA: znaczenia kolumn są zamienione względem pozwoleń —
    „budowa nowego…” jest w `rodzaj_zam_budowlanego`, a opis tekstowy w `nazwa_zam_budowlanego`."""
    use = ["numer_ewidencyjny_system", "data_wplywu_wniosku_do_urzedu", "terc", "kategoria",
           "rodzaj_zam_budowlanego", "jednostki_numer", "obreb_numer"]
    parts = []
    for chunk in _read_chunks(path, NOTIF_COLUMNS, use):
        chunk = chunk[chunk["kategoria"].isin(KIND_BY_CATEGORY)]
        chunk = chunk[chunk["rodzaj_zam_budowlanego"].str.strip().str.lower().str.startswith("budowa nowego")]
        chunk = chunk.assign(source_id=chunk["numer_ewidencyjny_system"], date=chunk["data_wplywu_wniosku_do_urzedu"],
                             jednostka=chunk["jednostki_numer"], obreb=chunk["obreb_numer"])
        parts.append(_finish(chunk, "zgloszenie"))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=OUTPUT_COLUMNS)


def build_permits_raw(permit_paths: list, notif_paths: list, con: duckdb.DuckDBPyConnection) -> int:
    """Wczytuje wszystkie pliki, usuwa duplikaty (po source_id) i wiersze bez obrębu; zapisuje `permits_raw`."""
    frames = [parse_permits(p) for p in permit_paths] + [parse_notifications(p) for p in notif_paths]
    frames = [f for f in frames if len(f)]
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=OUTPUT_COLUMNS)
    before = len(df)
    df = df.drop_duplicates(subset="source_id")
    deduped = len(df)
    df = df.dropna(subset=["obreb_id"])
    print(f"permits_raw: {before} wierszy po filtrach, {before - deduped} duplikatów, "
          f"{deduped - len(df)} odrzuconych (brak obrębu), zostaje {len(df)}")
    df = df.assign(date=df["date"].dt.date)
    con.register("permits_df", df)
    con.execute("""CREATE OR REPLACE TABLE permits_raw AS
                   SELECT source_id, source, kind, CAST(date AS DATE) AS date, obreb_id, terc FROM permits_df""")
    con.unregister("permits_df")
    return len(df)

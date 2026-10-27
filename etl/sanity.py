"""Kontrola jakości danych po ETL: czy tabele mają sensowne rozmiary i sumy.

Uruchomienie:  uv run python -m etl.sanity   (kod wyjścia 1, jeśli znaleziono problemy)

Progi pochodzą z wiedzy o danych: ludność Polski w spisie 2021 to ~37,1 mln, w OSM jest
ponad 8 tys. fryzjerów itd. Gdy próg nie przechodzi, najpierw szukamy przyczyny w ETL
(a nie podnosimy/obniżamy próg).
"""
import sys

import duckdb

from backend.app import config
from etl.aggregate import table_exists

THRESHOLDS = {
    "pop_min": 36_900_000,            # suma hex_pop_r9.pop_total
    "pop_max": 37_200_000,
    "hairdressers_min": 8000,         # liczba punktów OSM typu hairdresser
    "places_min": 40_000,             # liczba nazw miejscowości/osiedli
    "missing_geom_max_share": 0.05,   # maks. udział obrębów, których nie udało się geokodować
    "permits_sf_12m_min": 50_000,     # nowe domy jednorodzinne w ostatnich 12 miesiącach danych
    "dasymetry_share_min": 0.85,      # udział ludności rozłożonej przez budynki OSM (reszta: równomiernie)
    "building_weights_min": 1_000_000,  # wierszy w building_weights (komórka spisu × heksagon)
}
REQUIRED_TABLES = ["hex_pop_r9", "poi", "places", "obreb_geom", "permits_r9", "building_weights",
                   "poi_counts_r9", "hex_pop_r5", "poi_counts_r5", "permits_r5"]


def _scalar(con, sql: str):
    return con.execute(sql).fetchall()[0][0]


def check(con: duckdb.DuckDBPyConnection, thresholds: dict = THRESHOLDS) -> list[str]:
    """Zwraca listę problemów (pusta lista = dane wyglądają dobrze)."""
    problems = []
    missing = [t for t in REQUIRED_TABLES if not table_exists(con, t)]
    problems += [f"Brak tabeli {t}" for t in missing]

    def has(table):
        return table not in missing

    if has("hex_pop_r9"):
        total = _scalar(con, "SELECT COALESCE(SUM(pop_total), 0) FROM hex_pop_r9")
        if not thresholds["pop_min"] <= total <= thresholds["pop_max"]:
            problems.append(f"Suma ludności {total:,.0f} poza zakresem "
                            f"[{thresholds['pop_min']:,}; {thresholds['pop_max']:,}]")
    if has("building_weights"):
        n = _scalar(con, "SELECT COUNT(*) FROM building_weights")
        if n < thresholds["building_weights_min"]:
            problems.append(f"Za mało wierszy w building_weights: {n} (próg {thresholds['building_weights_min']:,})")
    if table_exists(con, "meta"):
        row = con.execute("SELECT rows FROM meta WHERE source = 'dasymetria'").fetchall()
        share = row[0][0] / 1000 if row else None
        if share is None:
            problems.append("Brak w meta udziału ludności rozłożonej przez budynki (dasymetria) — przelicz krok 'population'")
        elif share < thresholds["dasymetry_share_min"]:
            problems.append(f"Za mały udział dasymetrii: {share:.1%} ludności rozłożone przez budynki "
                            f"(próg {thresholds['dasymetry_share_min']:.0%})")
    elif has("hex_pop_r9"):
        problems.append("Brak tabeli meta — nie wiadomo, jaka część ludności została rozłożona przez budynki")
    if has("poi"):
        n = _scalar(con, "SELECT COUNT(*) FROM poi WHERE type_id = 'hairdresser'")
        if n < thresholds["hairdressers_min"]:
            problems.append(f"Za mało punktów poi typu hairdresser: {n} (próg {thresholds['hairdressers_min']})")
    if has("places"):
        n = _scalar(con, "SELECT COUNT(*) FROM places")
        if n < thresholds["places_min"]:
            problems.append(f"Za mało rekordów w places: {n} (próg {thresholds['places_min']})")
    if has("obreb_geom"):
        total = _scalar(con, "SELECT COUNT(*) FROM obreb_geom")
        bad = _scalar(con, "SELECT COUNT(*) FROM obreb_geom WHERE status = 'missing'")
        if total == 0 or bad / total > thresholds["missing_geom_max_share"]:
            problems.append(f"Zbyt wiele niezgeokodowanych obrębów: {bad} z {total} "
                            f"(próg {thresholds['missing_geom_max_share']:.0%})")
    if has("obreb_geom") and table_exists(con, "permits_raw"):
        # pokrycie geokodowania: obręby z pozwoleń, których nie ma w obreb_geom (np. przerwane przez blokadę ULDK)
        total = _scalar(con, "SELECT COUNT(DISTINCT obreb_id) FROM permits_raw")
        todo = _scalar(con, """SELECT COUNT(DISTINCT obreb_id) FROM permits_raw
                               WHERE obreb_id NOT IN (SELECT obreb_id FROM obreb_geom)""")
        if total and todo / total > thresholds["missing_geom_max_share"]:
            problems.append(f"Niedokończone geokodowanie: {todo} z {total} obrębów z pozwoleń bez wpisu w obreb_geom")
    if has("permits_r9"):
        # „ostatnie 12 miesięcy” liczone od najnowszych danych w tabeli, nie od dzisiaj
        n = _scalar(con, """SELECT COALESCE(SUM(n), 0) FROM permits_r9 WHERE kind = 'sf'
                            AND month > (SELECT MAX(month) FROM permits_r9) - INTERVAL 12 MONTH""")
        if n < thresholds["permits_sf_12m_min"]:
            problems.append(f"Za mało nowych domów (sf) w ostatnich 12 miesiącach: {n} (próg {thresholds['permits_sf_12m_min']})")
    for table in ("hex_pop_r5", "poi_counts_r5", "permits_r5"):
        if has(table) and _scalar(con, f"SELECT COUNT(*) FROM {table}") == 0:
            problems.append(f"Tabela {table} jest pusta")
    return problems


def main() -> int:
    if not config.DB_PATH.exists():
        print("Brak bazy danych — uruchom: uv run python -m etl.run_all")
        return 1
    con = duckdb.connect(str(config.DB_PATH), read_only=True)
    problems = check(con)
    for p in problems:
        print("PROBLEM:", p)
    if not problems:
        print("OK — dane przeszły kontrolę jakości")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

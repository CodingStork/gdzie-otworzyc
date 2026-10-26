"""Orkiestracja ETL: pobieranie → ludność → OSM → pozwolenia → geokodowanie → agregacja.

Uruchomienie:  uv run python -m etl.run_all [--only population,aggregate] [--force]

Kroki kosztowne (population, osm, permits) pomijają się, jeśli ich tabela już istnieje
(chyba że --force). Download i geocode są wznawialne (nie pobierają/nie geokodują drugi raz tego
samego). Kroki tanie i pochodne (permits_hex, aggregate) wykonują się zawsze, żeby tabele
zbiorcze odpowiadały aktualnym danym źródłowym. UWAGA: serwer aplikacji musi być zatrzymany —
ETL zapisuje do pliku bazy, który serwer trzyma otwarty tylko do odczytu.
"""
import argparse
import datetime
import time
from pathlib import Path

import duckdb
import httpx

from backend.app.config import DATA_DIR, USER_AGENT
from etl import download as dl
from etl.aggregate import build_aggregates, table_exists
from etl.geocode_obreby import ULDK_URL, UldkClient, build_permits_hex, geocode_missing
from etl.osm_poi import build_poi_tables
from etl.permits import build_permits_raw
from etl.population import build_hex_pop

STEPS = ("download", "population", "osm", "permits", "geocode", "permits_hex", "aggregate")


def _record_meta(con, source: str, url: str, rows: int, when: datetime.datetime | None = None) -> None:
    """Zapisuje w tabeli meta, skąd i kiedy pochodzą dane (pokazywane w stopce aplikacji)."""
    con.execute("""CREATE TABLE IF NOT EXISTS meta (
        source VARCHAR PRIMARY KEY, url VARCHAR, downloaded_at TIMESTAMP, rows BIGINT)""")
    con.execute("INSERT OR REPLACE INTO meta VALUES (?, ?, ?, ?)", [source, url, when or datetime.datetime.now(), rows])


def _mtime(path: Path) -> datetime.datetime:
    return datetime.datetime.fromtimestamp(path.stat().st_mtime)


def _count(con, table: str) -> int:
    return con.execute(f"SELECT COUNT(*) FROM {table}").fetchall()[0][0]


def run(steps: list[str] | None = None, force: bool = False, data_dir: Path = DATA_DIR) -> None:
    steps = list(steps) if steps else list(STEPS)
    unknown = [s for s in steps if s not in STEPS]
    if unknown:
        raise ValueError(f"nieznany krok ETL: {unknown}; dostępne: {list(STEPS)}")
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    raw = dl.raw_paths(data_dir / "raw")
    con = duckdb.connect(str(data_dir / "app.duckdb"))
    try:
        for step in STEPS:                       # zawsze w kolejności zależności
            if step not in steps:
                continue
            started = time.time()
            print(f"[{step}] start", flush=True)
            info = _run_step(step, con, raw, force, data_dir)
            print(f"[{step}] gotowe w {time.time() - started:.0f} s: {info}", flush=True)
    finally:
        con.close()


def _run_step(step: str, con, raw: dict, force: bool, data_dir: Path) -> object:
    if step == "download":
        dl.download_all(data_dir / "raw", force)
        return "pliki w data/raw"

    if step == "population":
        if table_exists(con, "hex_pop_r8") and not force:
            return "pominięto (hex_pop_r8 istnieje)"
        n = build_hex_pop(raw["census_parquet"], con)
        _record_meta(con, "census", dl.CENSUS_URL, n, _mtime(raw["census_zip"]))
        return f"{n} heksagonów"

    if step == "osm":
        if table_exists(con, "poi") and table_exists(con, "places") and not force:
            return "pominięto (poi i places istnieją)"
        counts = build_poi_tables(raw["osm_pbf"], con)
        _record_meta(con, "osm", dl.OSM_URL, counts["poi"], _mtime(raw["osm_pbf"]))
        return counts

    if step == "permits":
        if table_exists(con, "permits_raw") and not force:
            return "pominięto (permits_raw istnieje)"
        n = build_permits_raw(raw["gunb_permits"], raw["gunb_notifications"], con)
        newest = max(_mtime(p) for p in raw["gunb_permits"] + raw["gunb_notifications"])
        _record_meta(con, "gunb", dl.GUNB_BASE, n, newest)
        return f"{n} pozwoleń i zgłoszeń"

    if step == "geocode":
        if not table_exists(con, "permits_raw"):
            raise RuntimeError("Brak tabeli permits_raw — najpierw uruchom krok 'permits'")
        if force and table_exists(con, "obreb_geom"):
            con.execute("DELETE FROM obreb_geom WHERE status = 'missing'")   # ponów tylko te, których nie znaleziono
        with httpx.Client(timeout=httpx.Timeout(60.0, connect=30.0), follow_redirects=True,
                          headers={"User-Agent": USER_AGENT}) as client:
            counts = geocode_missing(con, UldkClient(client))
        _record_meta(con, "uldk", ULDK_URL, _count(con, "obreb_geom"))
        return counts

    if step == "permits_hex":
        if not (table_exists(con, "permits_raw") and table_exists(con, "obreb_geom")):
            raise RuntimeError("Brak tabel permits_raw/obreb_geom — uruchom kroki 'permits' i 'geocode'")
        return f"{build_permits_hex(con)} wierszy permits_r8"

    if step == "aggregate":
        return build_aggregates(con)
    raise AssertionError(step)


def main() -> None:
    parser = argparse.ArgumentParser(description="ETL aplikacji „Gdzie otworzyć?”")
    parser.add_argument("--only", help=f"kroki oddzielone przecinkami, z: {', '.join(STEPS)}")
    parser.add_argument("--force", action="store_true", help="wykonaj kroki mimo istniejących wyników")
    args = parser.parse_args()
    run(args.only.split(",") if args.only else None, force=args.force)


if __name__ == "__main__":
    main()

"""Overture Maps Places → firmy w tabeli `poi` (obok OpenStreetMap).

OSM ma dla usług (salony, fryzjerzy…) kilka razy mniej firm niż Overture, więc dopełniamy nim `poi`.
Overture Places to otwarty zbiór (licencja CDLA Permissive 2.0) w plikach Parquet na S3; DuckDB
czyta z nich wprost przez HTTP, więc pobieramy tylko Polskę (~125 MB, kilkanaście sekund).

Ten sam salon bywa w obu źródłach, więc przed dopisaniem usuwamy duplikaty (`dedupe`):
obiekt Overture odpada, gdy w pobliżu jest punkt OSM tego samego typu.
"""
import difflib
import re
import unicodedata
from pathlib import Path

import duckdb
import httpx
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from backend.app.analysis.kernel import to_metric
from backend.app.catalog import match_overture
from backend.app.config import USER_AGENT
from etl.osm_poi import _with_h3

STAC_URL = "https://stac.overturemaps.org/catalog.json"
S3_PLACES = "s3://overturemaps-us-west-2/release/{release}/theme=places/type=place/*"
BBOX = (14.1, 49.0, 24.2, 54.9)      # lng_min, lat_min, lng_max, lat_max — prostokąt obejmujący Polskę
MIN_CONFIDENCE = 0.5                 # Overture ocenia pewność istnienia miejsca; poniżej 0,5 jest dużo „śmieci”
DEDUP_SAME_M = 50                    # tego samego typu w tej odległości = ten sam obiekt
DEDUP_NAME_M = 150                   # …a w tej, jeśli nazwy są podobne
DEDUP_NAME_RATIO = 0.6               # próg podobieństwa nazw (difflib, 0–1)


def latest_release() -> str:
    """Numer najnowszego wydania Overture (np. „2026-10-21.0”) z katalogu STAC."""
    return httpx.get(STAC_URL, headers={"User-Agent": USER_AGENT}, timeout=30.0).json()["latest"]


def download_places(dest: Path, force: bool = False) -> tuple[Path, str]:
    """Zapisuje do `dest` (Parquet) miejsca w Polsce; zwraca (ścieżka, numer wydania).

    Filtry: adres w Polsce, miejsce działające (brak statusu = zakładamy, że działa) i pewność ≥ 0,5.
    Gdy plik już jest (i nie ma `force`), nic nie pobieramy — numer wydania czytamy z pliku `.release`.
    """
    dest = Path(dest)
    marker = dest.with_suffix(".release")
    if dest.exists() and not force:
        return dest, marker.read_text().strip() if marker.exists() else "nieznane"
    release = latest_release()
    dest.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs; SET s3_region = 'us-west-2';")
    west, south, east, north = BBOX
    part = dest.with_suffix(".part")
    con.execute(f"""COPY (
        SELECT id, names.primary AS name, basic_category, taxonomy.primary AS cat, confidence, operating_status,
               (bbox.ymin + bbox.ymax) / 2 AS lat, (bbox.xmin + bbox.xmax) / 2 AS lng,
               addresses[1].country AS country, addresses[1].locality AS locality
        FROM read_parquet('{S3_PLACES.format(release=release)}', hive_partitioning = 1)
        WHERE bbox.xmin BETWEEN {west} AND {east} AND bbox.ymin BETWEEN {south} AND {north}
          AND addresses[1].country = 'PL'
          AND COALESCE(operating_status, 'open') = 'open'
          AND confidence >= {MIN_CONFIDENCE}
    ) TO '{part.as_posix()}' (FORMAT parquet)""")
    con.close()
    part.replace(dest)
    marker.write_text(release)
    return dest, release


def normalize_name(name: str | None) -> str:
    """Nazwa do porównań: małe litery, bez polskich znaków i interpunkcji („Salon „Różana”!” → „salon rozana”)."""
    if not isinstance(name, str):          # brak nazwy: None albo NaN z pandas
        return ""
    plain = unicodedata.normalize("NFKD", name.casefold().replace("ł", "l"))
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return re.sub(r"[\W_]+", " ", plain).strip()


def dedupe(osm: pd.DataFrame, overture: pd.DataFrame) -> pd.DataFrame:
    """Zwraca wiersze Overture bez duplikatów punktów OSM (kolumny: type_id, name, lat, lng).

    Duplikat = punkt OSM tego samego typu w ≤ 50 m albo w ≤ 150 m z podobną nazwą. Odległości liczymy
    w metrach (EPSG:2180), sąsiadów szukamy drzewem k-d (cKDTree), osobno dla każdego typu.
    """
    if osm.empty or overture.empty:
        return overture
    keep = np.ones(len(overture), dtype=bool)
    position = {label: pos for pos, label in enumerate(overture.index)}    # etykieta wiersza → numer pozycji
    for type_id, ov_part in overture.groupby("type_id"):
        osm_part = osm[osm["type_id"] == type_id]
        if osm_part.empty:
            continue
        osm_xy = to_metric(osm_part["lat"].to_numpy(), osm_part["lng"].to_numpy())
        ov_xy = to_metric(ov_part["lat"].to_numpy(), ov_part["lng"].to_numpy())
        osm_names = [normalize_name(n) for n in osm_part["name"]]
        ov_names = [normalize_name(n) for n in ov_part["name"]]
        neighbours = cKDTree(osm_xy).query_ball_point(ov_xy, DEDUP_NAME_M)
        for i, (label, near) in enumerate(zip(ov_part.index, neighbours)):
            for j in near:
                dist = float(np.hypot(*(ov_xy[i] - osm_xy[j])))
                similar = bool(ov_names[i] and osm_names[j]
                               and difflib.SequenceMatcher(None, ov_names[i], osm_names[j]).ratio() >= DEDUP_NAME_RATIO)
                if dist <= DEDUP_SAME_M or similar:
                    keep[position[label]] = False
                    break
    return overture[keep]


def ensure_poi_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Starsze bazy mają `poi.osm_id` i nie mają `source` — przemianowujemy kolumnę i oznaczamy wiersze jako OSM."""
    cols = {r[0] for r in con.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'poi'").fetchall()}
    if "osm_id" in cols:
        con.execute("ALTER TABLE poi RENAME COLUMN osm_id TO source_id")
    if "source" not in cols:
        con.execute("ALTER TABLE poi ADD COLUMN source VARCHAR DEFAULT 'osm'")
        con.execute("UPDATE poi SET source = 'osm'")


def build_overture_poi(parquet: Path, con: duckdb.DuckDBPyConnection) -> dict:
    """Dopisuje do `poi` firmy z Overture (po deduplikacji względem OSM). Można powtarzać — stare wiersze Overture usuwa.

    Zwraca liczby: before_dedup / after_dedup (wiersze typ×obiekt) oraz by_type (po deduplikacji).
    """
    ensure_poi_schema(con)
    con.execute("DELETE FROM poi WHERE source = 'overture'")
    raw = con.execute(f"SELECT id, name, cat, lat, lng FROM read_parquet('{Path(parquet).as_posix()}')").df()
    rows = [(r.id, t, r.name, r.lat, r.lng) for r in raw.itertuples() for t in match_overture(r.cat)]
    ov = pd.DataFrame(rows, columns=["source_id", "type_id", "name", "lat", "lng"])
    osm = con.execute("SELECT type_id, name, lat, lng FROM poi WHERE source = 'osm'").df()
    kept = dedupe(osm, ov)
    by_type: dict[str, int] = {}
    if len(kept):
        kept = _with_h3(kept.assign(source="overture"))
        con.register("ov_in", kept[["source_id", "type_id", "name", "lat", "lng", "h3", "source"]])
        con.execute("INSERT INTO poi (source_id, type_id, name, lat, lng, h3, source) SELECT * FROM ov_in")
        con.unregister("ov_in")
        by_type = {t: int(n) for t, n in kept["type_id"].value_counts().items()}
    return {"before_dedup": len(ov), "after_dedup": len(kept), "by_type": by_type}

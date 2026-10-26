"""Pobieranie surowych plików (spis, OSM, GUNB) do katalogu data/raw/.

Pliki są duże (kilka GB), więc pobieramy strumieniowo, a do pliku docelowego
trafiają dopiero po pełnym pobraniu (najpierw `*.part`). Jeśli pobieranie
przerwano, kolejne uruchomienie dokończy plik od miejsca przerwania (nagłówek Range).
"""
import zipfile
from pathlib import Path

import httpx

from backend.app.config import RAW_DIR, USER_AGENT

CENSUS_URL = "https://gisco-services.ec.europa.eu/census/2021/Eurostat_Census-GRID_2021_V3.zip"
OSM_URL = "https://download.geofabrik.de/europe/poland-latest.osm.pbf"
GUNB_BASE = "https://wyszukiwarka.gunb.gov.pl/pliki_pobranie/"

GUNB_VOIVODESHIPS = (
    "dolnoslaskie", "kujawsko-pomorskie", "lubelskie", "lubuskie", "lodzkie", "mazowieckie",
    "malopolskie", "opolskie", "podkarpackie", "podlaskie", "pomorskie", "slaskie",
    "swietokrzyskie", "warminsko-mazurskie", "wielkopolskie", "zachodniopomorskie",
)
# Zgłoszenia budowy (bez pozwolenia) — dwa pliki ogólnopolskie.
GUNB_NOTIFICATION_FILES = ("wynik_zgloszenia_2016_2021.zip", "wynik_zgloszenia_2022_up.zip")

CHUNK = 1024 * 1024  # 1 MB


def _new_client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=httpx.Timeout(60.0, connect=30.0),  # 60 s na odczyt kolejnego kawałka
        follow_redirects=True,
    )


def download(url: str, dest: Path, force: bool = False, client: httpx.Client | None = None) -> Path:
    """Pobiera `url` do `dest`. Jeśli plik już jest (i nie ma `force`), nic nie robi."""
    dest = Path(dest)
    if dest.exists() and not force:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    if force and part.exists():
        part.unlink()

    own_client = client is None
    client = client or _new_client()
    try:
        done = part.stat().st_size if part.exists() else 0
        headers = {"User-Agent": USER_AGENT}
        if done:
            headers["Range"] = f"bytes={done}-"  # wznowienie przerwanego pobierania
        with client.stream("GET", url, headers=headers, follow_redirects=True) as resp:
            if resp.status_code == 416:  # .part jest już kompletny
                part.replace(dest)
                return dest
            resp.raise_for_status()
            mode = "ab" if resp.status_code == 206 else "wb"  # 200 = serwer ignoruje Range
            with open(part, mode) as f:
                for chunk in resp.iter_bytes(CHUNK):
                    f.write(chunk)
        part.replace(dest)
    finally:
        if own_client:
            client.close()
    return dest


def extract_member(zip_path: Path, member_suffix: str, dest: Path) -> Path:
    """Wypakowuje z ZIP-a pierwszy plik, którego nazwa kończy się `member_suffix`."""
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if n.endswith(member_suffix)]
        if not names:
            raise FileNotFoundError(f"W {zip_path} nie ma pliku *{member_suffix}")
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with z.open(names[0]) as src, open(dest, "wb") as out:
            while chunk := src.read(CHUNK):
                out.write(chunk)
    return dest


def download_all(raw_dir: Path = RAW_DIR, force: bool = False) -> dict[str, Path | list[Path]]:
    """Pobiera wszystkie źródła. Zwraca ścieżki gotowych plików (po wypakowaniu)."""
    raw_dir = Path(raw_dir)
    with _new_client() as client:
        # Spis ludności: z ZIP-a (cała UE) potrzebujemy tylko jednego pliku parquet.
        census_zip = download(CENSUS_URL, raw_dir / "census.zip", force, client)
        census_parquet = raw_dir / "census.parquet"
        if force or not census_parquet.exists():
            extract_member(census_zip, "V3.parquet", census_parquet)

        osm_pbf = download(OSM_URL, raw_dir / "poland-latest.osm.pbf", force, client)

        permits = []
        for woj in GUNB_VOIVODESHIPS:
            zip_path = download(f"{GUNB_BASE}wynik_{woj}.zip", raw_dir / "gunb" / f"wynik_{woj}.zip", force, client)
            csv_path = raw_dir / "gunb" / f"wynik_{woj}.csv"
            if force or not csv_path.exists():
                extract_member(zip_path, ".csv", csv_path)
            permits.append(csv_path)

        notifications = []
        for name in GUNB_NOTIFICATION_FILES:
            zip_path = download(GUNB_BASE + name, raw_dir / "gunb" / name, force, client)
            csv_path = zip_path.with_suffix(".csv")
            if force or not csv_path.exists():
                extract_member(zip_path, ".csv", csv_path)
            notifications.append(csv_path)

    return {
        "census_parquet": census_parquet,
        "osm_pbf": osm_pbf,
        "gunb_permits": permits,
        "gunb_notifications": notifications,
    }


def raw_paths(raw_dir: Path = RAW_DIR) -> dict:
    """Ścieżki plików po wypakowaniu (bez pobierania) — te same, które zwraca download_all."""
    raw_dir = Path(raw_dir)
    return {
        "census_zip": raw_dir / "census.zip",
        "census_parquet": raw_dir / "census.parquet",
        "osm_pbf": raw_dir / "poland-latest.osm.pbf",
        "gunb_permits": [raw_dir / "gunb" / f"wynik_{woj}.csv" for woj in GUNB_VOIVODESHIPS],
        "gunb_notifications": [raw_dir / "gunb" / name.replace(".zip", ".csv") for name in GUNB_NOTIFICATION_FILES],
    }

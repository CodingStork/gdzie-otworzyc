"""Geokodowanie obrębów ewidencyjnych przez ULDK (GUGiK) → `obreb_geom`, a potem `permits_r8`.

Pozwolenia mają numer działki, ale działek są miliony, a ULDK odpowiada ~0,35 s na zapytanie.
Dlatego geokodujemy OBRĘBY (jednostki ewidencyjne, ~50 tys.): pobieramy kształt obrębu, a jako jego
położenie bierzemy `representative_point()` — punkt zawsze leżący WEWNĄTRZ kształtu (zwykły
środek ciężkości bywa poza figurą wklęsłą). Dokładność = obręb (miasto: osiedle, wieś: cała wieś).
Wyniki trafiają do tabeli-cache `obreb_geom`, więc przerwany ETL można po prostu uruchomić ponownie.
"""
import time
from concurrent.futures import ThreadPoolExecutor

import duckdb
import h3
import httpx
import pandas as pd
import shapely.wkt

from backend.app.config import USER_AGENT

ULDK_URL = "https://uldk.gugik.gov.pl/"
RETRY_SLEEPS = (1, 2, 4)   # przerwy [s] przed kolejnymi próbami


class UldkError(Exception):
    """Błąd sieci/serwera ULDK mimo ponowień (wynik nieznany — nie zapisujemy go w cache)."""


def parse_uldk_response(text: str) -> tuple[str, str, str] | None:
    """Odpowiedź ULDK → (id, nazwa, wkt) albo None.

    Pierwsza linia '0' = sukces, '-1 …' = błąd/brak. Druga linia ma 3 pola (`id|nazwa|wkt`, dla
    obrębu i gminy) albo 2 pola (`id|wkt`, dla działki; nazwa wtedy pusta). WKT może zaczynać się
    od 'SRID=4326;' — to odcinamy.
    """
    lines = text.strip().splitlines()
    if len(lines) < 2 or lines[0].strip() != "0":
        return None
    fields = lines[1].strip().split("|")
    if len(fields) == 3:
        obreb_id, name, wkt = fields
    elif len(fields) == 2:
        (obreb_id, wkt), name = fields, ""
    else:
        return None
    if wkt.startswith("SRID="):
        wkt = wkt.split(";", 1)[1]
    return obreb_id, name, wkt


def wkt_to_latlng(wkt: str) -> tuple[float, float]:
    """Punkt reprezentatywny kształtu jako (lat, lng). W WKT z ULDK x = długość, y = szerokość."""
    point = shapely.wkt.loads(wkt).representative_point()
    return point.y, point.x


class UldkClient:
    def __init__(self, client: httpx.Client, base_url: str = ULDK_URL):
        self.client = client
        self.base_url = base_url
        self._commune_cache: dict[str, tuple[str, float, float] | None] = {}

    def _query(self, request: str, object_id: str, result: str) -> tuple[str, float, float] | None:
        """Jedno zapytanie z ponowieniami (błędy sieci i 5xx). Zwraca (nazwa, lat, lng) albo None."""
        params = {"request": request, "id": object_id, "result": result, "srid": "4326"}
        for attempt in range(len(RETRY_SLEEPS) + 1):
            try:
                # Przekierowań NIE śledzimy: ULDK przekierowuje zablokowanych klientów na stronę-pułapkę
                # ze śmieciową odpowiedzią — to ma być błąd (do ponowienia później), a nie „brak wyniku”.
                resp = self.client.get(self.base_url, params=params, headers={"User-Agent": USER_AGENT},
                                       follow_redirects=False)
                if resp.status_code >= 500:
                    raise httpx.HTTPError(f"HTTP {resp.status_code}")
                resp.raise_for_status()
                break
            except httpx.HTTPError as e:
                if attempt == len(RETRY_SLEEPS):
                    raise UldkError(f"{request} {object_id}: {e}") from e
                time.sleep(RETRY_SLEEPS[attempt])
        parsed = parse_uldk_response(resp.text)
        if parsed is not None:
            _, name, wkt = parsed
            try:
                lat, lng = wkt_to_latlng(wkt)
            except Exception as e:   # śmieciowa geometria
                raise UldkError(f"{request} {object_id}: nieczytelna geometria") from e
            return name, lat, lng
        # Za "brak wyniku" uznajemy tylko wyraźną odpowiedź „-1 brak wyników”; wszystko inne to błąd.
        first_line = resp.text.strip().splitlines()[0] if resp.text.strip() else ""
        if first_line.startswith("-1") and "brak wynik" in first_line.lower():
            return None
        raise UldkError(f"{request} {object_id}: nieoczekiwana odpowiedź: {resp.text[:80]!r}")

    def region(self, obreb_id: str) -> tuple[str, float, float] | None:
        """Obręb ewidencyjny, np. '160602_4.0038' → (nazwa, lat, lng)."""
        return self._query("GetRegionById", obreb_id, "teryt,region,geom_wkt")

    def commune(self, jednostka_id: str) -> tuple[str, float, float] | None:
        """Gmina (jednostka ewidencyjna), np. '160602_4' → (nazwa, lat, lng). Wyniki cache'ujemy."""
        if jednostka_id not in self._commune_cache:
            self._commune_cache[jednostka_id] = self._query("GetCommuneById", jednostka_id, "teryt,commune,geom_wkt")
        return self._commune_cache[jednostka_id]


def _resolve(uldk: UldkClient, obreb_id: str) -> tuple[str, str | None, float | None, float | None] | None:
    """(status, nazwa, lat, lng) dla obrębu; None przy błędzie sieci (wtedy nic nie zapisujemy)."""
    try:
        found = uldk.region(obreb_id)
        if found:
            return "region", *found
        # Fallback: obręb nieznany ULDK → środek gminy (część identyfikatora przed kropką).
        found = uldk.commune(obreb_id.split(".")[0])
        if found:
            return "commune", *found
        return "missing", None, None, None
    except UldkError:
        return None


def geocode_missing(con: duckdb.DuckDBPyConnection, uldk: UldkClient, workers: int = 5, batch: int = 200) -> dict[str, int]:
    """Geokoduje obręby z `permits_raw`, których nie ma jeszcze w `obreb_geom`.

    Zapytania HTTP idą równolegle (workers wątków), ale do bazy pisze tylko wątek główny, po każdej
    porcji `batch` obrębów — przerwanie programu traci najwyżej jedną porcję.
    """
    con.execute("""CREATE TABLE IF NOT EXISTS obreb_geom (
        obreb_id VARCHAR PRIMARY KEY, name VARCHAR, lat DOUBLE, lng DOUBLE, status VARCHAR)""")
    todo = [r[0] for r in con.execute(
        """SELECT DISTINCT obreb_id FROM permits_raw
           WHERE obreb_id NOT IN (SELECT obreb_id FROM obreb_geom) ORDER BY 1""").fetchall()]
    counts = {"region": 0, "commune": 0, "missing": 0, "error": 0}
    started = time.time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for start in range(0, len(todo), batch):
            ids = todo[start:start + batch]
            rows = []
            for obreb_id, res in zip(ids, pool.map(lambda i: _resolve(uldk, i), ids)):
                if res is None:
                    counts["error"] += 1
                    continue
                counts[res[0]] += 1
                rows.append((obreb_id, res[1], res[2], res[3], res[0]))
            if rows:
                con.executemany("INSERT INTO obreb_geom VALUES (?, ?, ?, ?, ?)", rows)
            if not rows:
                # Cała porcja zakończyła się błędem: serwer prawdopodobnie nas blokuje. Przerywamy, żeby
                # go nie męczyć i niczego nie zapisać błędnie — kolejne uruchomienie dokończy pracę.
                print("ULDK nie odpowiada poprawnie (możliwa blokada) — przerywam; spróbuj ponownie za jakiś czas", flush=True)
                break
            done = start + len(ids)
            elapsed = time.time() - started
            print(f"geokodowanie obrębów: {done}/{len(todo)} ({counts}), pozostało ~{elapsed / done * (len(todo) - done) / 60:.0f} min",
                  flush=True)
    return counts


def build_permits_hex(con: duckdb.DuckDBPyConnection) -> int:
    """Pozwolenia → heksagony H3 res 8: tabela permits_r8(h3, month, kind, n).

    Każdy obręb wpada do jednego heksagonu (ten, w którym leży jego punkt reprezentatywny);
    pozwolenia zliczamy w miesiącach i rodzajach budynków (sf/mf). Obręby bez geokodowania
    (status 'missing') pomijamy.
    """
    geo = con.execute("SELECT obreb_id, lat, lng FROM obreb_geom WHERE status != 'missing'").df()
    geo["h3"] = [h3.latlng_to_cell(lat, lng, 8) for lat, lng in zip(geo["lat"], geo["lng"])]
    con.register("geo_df", geo[["obreb_id", "h3"]])
    con.execute("""CREATE OR REPLACE TABLE permits_r8 AS
        SELECT g.h3, CAST(date_trunc('month', p.date) AS DATE) AS month, p.kind, CAST(COUNT(*) AS INTEGER) AS n
        FROM permits_raw p JOIN geo_df g ON p.obreb_id = g.obreb_id
        GROUP BY 1, 2, 3""")
    con.unregister("geo_df")
    return con.execute("SELECT COUNT(*) FROM permits_r8").fetchall()[0][0]

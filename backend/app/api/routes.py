"""Endpointy REST aplikacji (prefiks /api)."""
import math
from functools import lru_cache

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.analysis.service import SurfaceParams, cached_surface, point_details
from backend.app.analysis.national import (
    NATIONAL_MISSING_MESSAGE, PX_RANGE, NationalMissing, cached_national,
)
from backend.app.catalog import DEFAULT_MONTHS, DEMANDS, MONTHS_OPTIONS, TYPES, catalog_json
from backend.app.config import ATTRIBUTION, USER_AGENT
from backend.app.db import DatabaseMissing, cursor
from backend.app.services.geocode import Geocoder, GeocoderUnavailable
from etl.aggregate import table_exists

router = APIRouter(prefix="/api")

# Prostokąt obejmujący Polskę — punkt spoza niego odrzucamy.
LAT_RANGE = (49.0, 55.0)
LNG_RANGE = (14.0, 24.2)
DB_MISSING_MESSAGE = "Baza danych nie istnieje. Uruchom: uv run python -m etl.run_all"


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=422, detail=message)


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/catalog")
def catalog() -> dict:
    """Typy działalności (pogrupowane) i czynniki popytu do wypełnienia formularza."""
    return catalog_json()


def _parse_bbox(bbox: str) -> tuple[float, float, float, float]:
    """„minLng,minLat,maxLng,maxLat” → krotka liczb; błędny zapis lub odwrócone granice → 422."""
    try:
        min_lng, min_lat, max_lng, max_lat = (float(x) for x in bbox.split(","))
    except ValueError:
        raise _bad_request("Nieprawidłowy bbox")
    if not all(math.isfinite(v) for v in (min_lng, min_lat, max_lng, max_lat)) \
            or not (min_lng < max_lng and min_lat < max_lat):
        raise _bad_request("Nieprawidłowy bbox")
    return min_lng, min_lat, max_lng, max_lat


RADIUS_KM = (1, 30)
REACH_KM = (0.1, 20)


def _check_selection(type_id: str, demand: str, months: int) -> None:
    """Wspólna walidacja wyboru użytkownika (typ, czynnik popytu, okres) dla /surface i /point."""
    if not type_id and not demand:
        raise _bad_request("Wybierz typ działalności albo czynnik popytu")
    if type_id and type_id not in TYPES:
        raise _bad_request("Nieznany typ działalności")
    if demand and demand not in DEMANDS:
        raise _bad_request("Nieznany czynnik popytu")
    if months not in MONTHS_OPTIONS:
        raise _bad_request("Okres musi wynosić 12, 24 lub 36 miesięcy")


def _check_in_poland(lat: float, lng: float, what: str) -> None:
    if not (math.isfinite(lat) and math.isfinite(lng)
            and LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LNG_RANGE[0] <= lng <= LNG_RANGE[1]):
        raise _bad_request(f"{what} poza Polską")


VIEW_MAX_KM = 60       # największy bok „widocznego obszaru” liczonego na żywo


def _view_params(west: float, south: float, east: float, north: float) -> tuple[float, float, tuple]:
    """Prostokąt widoku → (lat środka, lng środka, bbox); bok większy niż 60 km albo poza Polską → 422."""
    if not all(math.isfinite(v) for v in (west, south, east, north)) or not (west < east and south < north):
        raise _bad_request("Nieprawidłowy prostokąt widoku")
    mid_lat, mid_lng = (south + north) / 2, (west + east) / 2
    _check_in_poland(mid_lat, mid_lng, "Widok")
    width_km = (east - west) * 111.32 * math.cos(math.radians(mid_lat))
    height_km = (north - south) * 110.54
    if max(width_km, height_km) > VIEW_MAX_KM:
        raise _bad_request(f"Widoczny obszar może mieć bok najwyżej {VIEW_MAX_KM} km — przybliż mapę")
    return mid_lat, mid_lng, (west, south, east, north)


@router.get("/surface")
def surface(
    type_id: str = Query(default="", alias="type"),
    demand: str = Query(default=""),
    lat: float | None = Query(default=None),
    lng: float | None = Query(default=None),
    radius_km: float | None = Query(default=None),
    reach_km: float = Query(),
    months: int = 24,
    west: float | None = Query(default=None),
    south: float | None = Query(default=None),
    east: float | None = Query(default=None),
    north: float | None = Query(default=None),
) -> dict:
    """Mapa okolicy: wartości na siatce w okręgu wokół miejsca (`lat`, `lng`, `radius_km`) albo w prostokącie widoku mapy
    (`west`, `south`, `east`, `north`, bok ≤ 60 km). Puste `type` / `demand` = brak wyboru."""
    _check_selection(type_id, demand, months)
    if not REACH_KM[0] <= reach_km <= REACH_KM[1]:
        raise _bad_request("Zasięg klienta (reach_km) musi mieścić się w zakresie 0,1–20 km (wartości poniżej 0,3 km są podnoszone do 0,3 km)")
    view = [west, south, east, north]
    bbox = None
    if any(v is not None for v in view):
        if any(v is None for v in view):
            raise _bad_request("Podaj wszystkie cztery granice widoku: west, south, east, north")
        lat, lng, bbox = _view_params(*view)
        radius_km = 1.0                     # promień okręgu opisanego policzy serwis z prostokąta
    else:
        if lat is None or lng is None or radius_km is None:
            raise _bad_request("Podaj miejsce (lat, lng) i promień obszaru albo granice widoku")
        _check_in_poland(lat, lng, "Miejsce")
        if not RADIUS_KM[0] <= radius_km <= RADIUS_KM[1]:
            raise _bad_request("Promień obszaru musi mieścić się w zakresie 1–30 km")
    params = SurfaceParams(type_id or None, demand or None, lat, lng, radius_km, reach_km, months, bbox)
    try:
        return cached_surface(params)
    except DatabaseMissing:
        raise HTTPException(status_code=503, detail=DB_MISSING_MESSAGE)


@router.get("/national")
def national(
    type_id: str = Query(default="", alias="type"),
    demand: str = Query(default=""),
    west: float = Query(),
    south: float = Query(),
    east: float = Query(),
    north: float = Query(),
    px: int = Query(default=1000),
) -> dict:
    """Gotowa mapa Polski (tryb „Cała Polska”): warstwy policzone w ETL dla typowego zasięgu, stała skala kolorów.
    `px` = szerokość mapy w pikselach (steruje rozdzielczością)."""
    _check_selection(type_id, demand, DEFAULT_MONTHS)
    if not all(math.isfinite(v) for v in (west, south, east, north)) or not (west < east and south < north):
        raise _bad_request("Nieprawidłowy prostokąt widoku")
    if not PX_RANGE[0] <= px <= PX_RANGE[1]:
        raise _bad_request(f"Szerokość mapy (px) musi mieścić się w zakresie {PX_RANGE[0]}–{PX_RANGE[1]}")
    try:
        return cached_national(type_id or None, demand or None, west, south, east, north, px)
    except DatabaseMissing:
        raise HTTPException(status_code=503, detail=DB_MISSING_MESSAGE)
    except NationalMissing:
        raise HTTPException(status_code=503, detail=NATIONAL_MISSING_MESSAGE)


@router.get("/point")
def point(
    lat: float = Query(),
    lng: float = Query(),
    type_id: str = Query(default="", alias="type"),
    demand: str = Query(default=""),
    reach_km: float = Query(),
    months: int = 24,
) -> dict:
    """Szczegóły klikniętego punktu: liczby w okręgu zasięgu, model Huffa, najbliższe firmy."""
    _check_selection(type_id, demand, months)
    if not REACH_KM[0] <= reach_km <= REACH_KM[1]:
        raise _bad_request("Zasięg klienta (reach_km) musi mieścić się w zakresie 0,1–20 km (wartości poniżej 0,3 km są podnoszone do 0,3 km)")
    _check_in_poland(lat, lng, "Punkt")
    try:
        return point_details(cursor(), lat, lng, type_id or None, demand or None, reach_km, months)
    except DatabaseMissing:
        raise HTTPException(status_code=503, detail=DB_MISSING_MESSAGE)


POI_LIMIT = 5000


@router.get("/poi")
def poi(type_id: str = Query(alias="type"), bbox: str = Query()) -> dict:
    """Punkty firm danego typu w widocznym fragmencie mapy (bbox = minLng,minLat,maxLng,maxLat)."""
    if type_id not in TYPES:
        raise _bad_request("Nieznany typ działalności")
    min_lng, min_lat, max_lng, max_lat = _parse_bbox(bbox)
    try:
        con = cursor()
    except DatabaseMissing:
        raise HTTPException(status_code=503, detail=DB_MISSING_MESSAGE)
    if not table_exists(con, "poi"):
        return {"items": [], "truncated": False}
    rows = con.execute(
        "SELECT lat, lng, name, source FROM poi WHERE type_id = ? AND lat BETWEEN ? AND ? AND lng BETWEEN ? AND ? LIMIT ?",
        [type_id, min_lat, max_lat, min_lng, max_lng, POI_LIMIT + 1]).fetchall()
    return {"items": [{"lat": lat, "lng": lng, "name": name, "source": source} for lat, lng, name, source in rows[:POI_LIMIT]],
            "truncated": len(rows) > POI_LIMIT}


@router.get("/meta")
def meta() -> dict:
    """Skąd i kiedy pochodzą dane (stopka aplikacji) oraz tekst atrybucji."""
    try:
        con = cursor()
    except DatabaseMissing:
        raise HTTPException(status_code=503, detail=DB_MISSING_MESSAGE)
    sources = []
    if table_exists(con, "meta"):
        for source, url, downloaded_at, rows in con.execute(
                "SELECT source, url, downloaded_at, rows FROM meta ORDER BY source").fetchall():
            sources.append({"source": source, "url": url, "downloaded_at": downloaded_at.isoformat(), "rows": rows})
    return {"sources": sources, "attribution": ATTRIBUTION}


@lru_cache(maxsize=1)
def get_geocoder() -> Geocoder:
    """Jeden wspólny geokoder (z pamięcią podręczną i limitem zapytań) dla całej aplikacji."""
    return Geocoder(httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=10.0))


@router.get("/geocode")
def geocode(q: str = "", geocoder: Geocoder = Depends(get_geocoder)) -> list[dict]:
    """Podpowiedzi adresów: [{name, lat, lng}]."""
    try:
        return geocoder.search(q)
    except GeocoderUnavailable:
        raise HTTPException(status_code=502, detail="Wyszukiwarka adresów chwilowo niedostępna")

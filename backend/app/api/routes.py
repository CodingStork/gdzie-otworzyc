"""Endpointy REST aplikacji (prefiks /api)."""
from fastapi import APIRouter, HTTPException, Query

from backend.app.analysis.service import AnalysisParams, run_analysis
from backend.app.catalog import DEMANDS, MONTHS_OPTIONS, TYPES, catalog_json
from backend.app.db import DatabaseMissing, cursor
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


@router.get("/analyze")
def analyze(
    type_id: str = Query(alias="type"),
    demand: str = Query(),
    lat: float | None = None,
    lng: float | None = None,
    radius_km: float | None = None,
    bandwidth_km: float | None = Query(default=None, gt=0, le=50),
    months: int = 24,
    scope: str = "local",
) -> dict:
    """Heatmapa „klienci na 1 konkurenta” dla typu działalności i czynnika popytu."""
    if type_id not in TYPES:
        raise _bad_request("Nieznany typ działalności")
    if demand not in DEMANDS:
        raise _bad_request("Nieznany czynnik popytu")
    if months not in MONTHS_OPTIONS:
        raise _bad_request("Okres musi wynosić 12, 24 lub 36 miesięcy")
    if scope not in ("local", "poland"):
        raise _bad_request("Nieznany zakres analizy")
    if scope == "local":
        if radius_km is None or not 1 <= radius_km <= 50:
            raise _bad_request("Promień musi mieścić się w zakresie 1–50 km")
        if lat is None or lng is None:
            raise _bad_request("Wybierz punkt na mapie albo wyszukaj adres")
        if not (LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LNG_RANGE[0] <= lng <= LNG_RANGE[1]):
            raise _bad_request("Punkt poza Polską")
    params = AnalysisParams(type_id, demand, lat, lng, radius_km, scope, bandwidth_km, months)
    try:
        return run_analysis(cursor(), params)
    except DatabaseMissing:
        raise HTTPException(status_code=503, detail=DB_MISSING_MESSAGE)


POI_LIMIT = 5000


@router.get("/poi")
def poi(type_id: str = Query(alias="type"), bbox: str = Query()) -> dict:
    """Punkty firm danego typu w widocznym fragmencie mapy (bbox = minLng,minLat,maxLng,maxLat)."""
    if type_id not in TYPES:
        raise _bad_request("Nieznany typ działalności")
    try:
        min_lng, min_lat, max_lng, max_lat = (float(x) for x in bbox.split(","))
    except ValueError:
        raise _bad_request("Nieprawidłowy bbox")
    if not (min_lng < max_lng and min_lat < max_lat):
        raise _bad_request("Nieprawidłowy bbox")
    try:
        con = cursor()
    except DatabaseMissing:
        raise HTTPException(status_code=503, detail=DB_MISSING_MESSAGE)
    if not table_exists(con, "poi"):
        return {"items": [], "truncated": False}
    rows = con.execute(
        "SELECT lat, lng, name FROM poi WHERE type_id = ? AND lat BETWEEN ? AND ? AND lng BETWEEN ? AND ? LIMIT ?",
        [type_id, min_lat, max_lat, min_lng, max_lng, POI_LIMIT + 1]).fetchall()
    return {"items": [{"lat": lat, "lng": lng, "name": name} for lat, lng, name in rows[:POI_LIMIT]],
            "truncated": len(rows) > POI_LIMIT}

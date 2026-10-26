"""Endpointy REST aplikacji (prefiks /api)."""
from fastapi import APIRouter

from backend.app.catalog import catalog_json

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/catalog")
def catalog() -> dict:
    """Typy działalności (pogrupowane) i czynniki popytu do wypełnienia formularza."""
    return catalog_json()

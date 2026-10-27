"""Punkt wejścia aplikacji FastAPI: API pod /api, a pod / statyczny frontend."""
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes import router
from backend.app.config import FRONTEND_DIR
from backend.app.db import DB_BUSY_MESSAGE, DatabaseBusy

app = FastAPI(title="Gdzie otworzyć?")
app.include_router(router)


@app.exception_handler(DatabaseBusy)
def database_busy(request, exc):
    """Każdy endpoint korzystający z bazy: zablokowana przez ETL → 503 z czytelnym komunikatem (zamiast 500)."""
    return JSONResponse(status_code=503, content={"detail": DB_BUSY_MESSAGE})


# Montowanie na końcu, żeby statyczne pliki nie przykryły ścieżek /api.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

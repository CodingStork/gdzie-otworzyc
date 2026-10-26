"""Punkt wejścia aplikacji FastAPI: API pod /api, a pod / statyczny frontend."""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes import router
from backend.app.config import FRONTEND_DIR

app = FastAPI(title="Gdzie otworzyć?")
app.include_router(router)
# Montowanie na końcu, żeby statyczne pliki nie przykryły ścieżek /api.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

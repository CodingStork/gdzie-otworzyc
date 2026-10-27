"""Konfiguracja: ścieżki do danych i stałe wspólne dla backendu i ETL."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Zmienna GO_DATA_DIR pozwala podmienić katalog z danymi (używane w testach).
DATA_DIR = Path(os.environ.get("GO_DATA_DIR", ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"        # surowe pobrane pliki (ZIP, PBF, CSV)
DB_PATH = DATA_DIR / "app.duckdb"  # jedna baza z gotowymi tabelami (heksagony H3)
FRONTEND_DIR = ROOT / "frontend"

USER_AGENT = "GdzieOtworzyc/0.1 (projekt studencki)"

ATTRIBUTION = (
    "© OpenStreetMap contributors © Esri | "
    "Firmy: © Overture Maps Foundation (CDLA Permissive 2.0) | "
    "Ludność: © EU, Eurostat GISCO (Census 2021, zmodyfikowane) | "
    "Pozwolenia: GUNB RWDZ | Geokodowanie: GUGiK ULDK"
)

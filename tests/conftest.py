import h3
import pytest
from fastapi.testclient import TestClient

from backend.app import config
from backend.app.db import reset_connection
from backend.app.main import app
from tests.factories import make_db

CENTER = (52.23, 21.01)   # Warszawa — środek syntetycznej siatki testowej


def disk(center=CENTER, k=12):
    """Heksagony res 8 w promieniu k pierścieni wokół środka (k=12 → ~9,6 km)."""
    return sorted(h3.grid_disk(h3.latlng_to_cell(*center, 8), k))


@pytest.fixture
def make_client(tmp_path, monkeypatch):
    """Fabryka klientów API: build(**kwargs do make_db) → TestClient z nową bazą testową."""
    counter = {"n": 0}

    def build(**kwargs):
        counter["n"] += 1
        db_path = make_db(tmp_path / f"test{counter['n']}.duckdb", **kwargs)
        monkeypatch.setattr(config, "DB_PATH", db_path)
        reset_connection()
        return TestClient(app)

    yield build
    reset_connection()   # zamyka plik bazy (na Windows inaczej nie da się go usunąć)


@pytest.fixture
def api_client(make_client):
    """Domyślna baza: ~470 heksagonów po 1000 mieszkańców + kilka salonów kosmetycznych."""
    pop = {c: 1000.0 for c in disk()}
    pois = [("beauty", 52.23, 21.01), ("beauty", 52.24, 21.02), ("beauty", 52.21, 20.99)]
    return make_client(pop=pop, pois=pois)

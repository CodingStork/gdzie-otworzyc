from fastapi.testclient import TestClient

from backend.app.main import app


def test_health():
    r = TestClient(app).get("/api/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_index_served():
    r = TestClient(app).get("/")
    assert r.status_code == 200 and "Gdzie otworzyć?" in r.text


def test_locked_db_returns_503(make_client):
    """Gdy ETL trzyma bazę w trybie zapisu, API odpowiada czytelnym 503, a po zwolnieniu blokady znów działa."""
    import subprocess
    import sys
    import time

    from backend.app import config
    from backend.app.db import DB_BUSY_MESSAGE, reset_connection
    from tests.conftest import CENTER, disk

    client = make_client(pop={c: 1.0 for c in disk(k=2)})
    reset_connection()                                             # zamknij połączenie, żeby inny proces mógł zapisywać
    child = subprocess.Popen(
        [sys.executable, "-c",
         f"import duckdb,time; c=duckdb.connect({str(config.DB_PATH)!r}); print('ready', flush=True); time.sleep(4)"],
        stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "ready"
        params = dict(demand="pop_total", bbox="20.97,52.2,21.05,52.26", zoom=13, bandwidth_km=1)
        for url, extra in (("/api/view", params), ("/api/meta", {}), ("/api/poi", dict(type="cafe", bbox="20,52,21,53"))):
            r = client.get(url, params=extra)
            assert r.status_code == 503 and r.json()["detail"] == DB_BUSY_MESSAGE, url
    finally:
        child.wait(timeout=15)
    # po zakończeniu procesu blokada znika; zepsute połączenie nie zostało zapamiętane
    assert client.get("/api/view", params=params).status_code == 200


def test_static_files_are_revalidated():
    """Przeglądarka nie może trzymać starego frontendu po aktualizacji aplikacji."""
    r = TestClient(app).get("/js/app.js")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-cache"

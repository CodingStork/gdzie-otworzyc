"""Testy E2E: prawdziwa przeglądarka (Playwright) klika w aplikację jak użytkownik.

Serwer FastAPI startuje w wątku na syntetycznej bazie (tests/e2e/synthetic.py). Testy pomijają się same, gdy nie ma
Playwrighta albo przeglądarki — instalacja: `uv sync`, potem raz `uv run playwright install chromium`.
Zmienne środowiskowe (tylko gdy sieć jest ograniczona, np. w chmurze):
  GO_CHROMIUM     — ścieżka do gotowej przeglądarki Chromium,
  GO_LEAFLET_DIR  — katalog z plikami Leaflet 1.9.4 (leaflet.js, leaflet.css, images/) zamiast unpkg.com.
Kafelki podkładu (Esri) są zawsze blokowane: testy nie zależą od internetu i są szybsze.
"""
import os
import socket
import threading
import time
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api", reason="brak Playwrighta — uruchom: uv sync")

from backend.app import config  # noqa: E402
from backend.app.db import reset_connection  # noqa: E402
from tests.e2e.synthetic import build  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def app_url(tmp_path_factory):
    """Adres aplikacji na syntetycznej bazie (serwer uvicorn w wątku, na czas modułu z testami)."""
    import uvicorn

    from backend.app.main import app
    db = build(tmp_path_factory.mktemp("e2e") / "app.duckdb")
    patch = pytest.MonkeyPatch()
    patch.setattr(config, "DB_PATH", db)
    reset_connection()
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/"
    server.should_exit = True
    thread.join(timeout=5)
    reset_connection()
    patch.undo()


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception:
            path = os.environ.get("GO_CHROMIUM") or "/opt/pw-browsers/chromium"
            if not Path(path).exists():
                pytest.skip("brak przeglądarki — uruchom raz: uv run playwright install chromium")
            b = p.chromium.launch(executable_path=path)
        yield b
        b.close()


def _route(page):
    leaflet = os.environ.get("GO_LEAFLET_DIR")
    if leaflet:
        page.route("https://unpkg.com/leaflet@1.9.4/dist/**",
                   lambda r: r.fulfill(path=str(Path(leaflet) / r.request.url.split("/dist/")[1])))
    page.route("https://server.arcgisonline.com/**", lambda r: r.abort())


@pytest.fixture
def make_page(browser):
    """make_page(url, intro=False, mobile=False) → strona z otwartą aplikacją; intro=False: animacje „już widziane”."""
    contexts = []

    def make(url, intro=False, mobile=False):
        options = dict(viewport={"width": 375, "height": 812}, is_mobile=True, has_touch=True) if mobile \
            else dict(viewport={"width": 1280, "height": 800})
        context = browser.new_context(**options)
        contexts.append(context)
        if not intro:
            context.add_init_script("['tools','circle','rect'].forEach(k => localStorage.setItem('gdzie-otworzyc-intro-v36-' + k, '1'))")
        page = context.new_page()
        page.errors = []
        page.on("pageerror", lambda e: page.errors.append(str(e)))
        page.api_calls = []
        page.on("request", lambda r: "/api/" in r.url and page.api_calls.append(r.url))
        _route(page)
        page.goto(url)
        page.wait_for_function("document.querySelectorAll('#type-select option').length > 1")
        return page

    yield make
    for c in contexts:
        c.close()

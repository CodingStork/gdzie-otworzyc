"""Scenariusze „jak użytkownik” (v3.6): prawdziwa przeglądarka klika w aplikację i sprawdza to, co człowiek widzi i czuje.

Każdy test odpowiada na pytanie, które zadał tester (Marcin, 2026-11-03), np. „czy po wybraniu klientów mapa liczy się sama,
choć nie kliknąłem Analizuj?”, „czy okrąg po kliknięciu jest widoczny przy każdym przybliżeniu?”, „czy ten sam kolor
nie oznacza bardzo różnych liczb?”. Dane są syntetyczne (tests/e2e/synthetic.py) — sprawdzamy zachowanie, nie wyniki.
"""
import math

import pytest

from tests.e2e.synthetic import BRZEG

CIRCLE_FRACTION = 0.2      # okrąg po kliknięciu: promień = 20% krótszego boku mapy (app.js: CIRCLE_SCREEN_FRACTION)


def view(lat, lng, z):
    return f"#z={z}&clat={lat}&clng={lng}"


def map_box(page):
    return page.locator("#map").bounding_box()


def click_map(page, fx=0.5, fy=0.5):
    b = map_box(page)
    page.mouse.click(b["x"] + b["width"] * fx, b["y"] + b["height"] * fy)


def center_of(page, selector):
    b = page.locator(selector).bounding_box()
    return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2


def surface_calls(page):
    return [u for u in page.api_calls if "/api/surface" in u]


def draw_circle(page, fx=0.4, fy=0.6):
    """Wybór narzędzia „Okrąg” i kliknięcie w mapę; czekamy, aż mapa płynnie wyśrodkuje okrąg."""
    page.click(".tool-button[data-tool=circle]")
    click_map(page, fx, fy)
    page.wait_for_selector(".circle-handle.edge")
    page.wait_for_timeout(900)


def analyze(page):
    page.click(".sel-ok")
    page.wait_for_selector("#summary-box:not([hidden])")
    page.wait_for_timeout(400)


# ---------------------------------------------------------------- start i narzędzia ----

def test_first_visit_points_at_tool_buttons(app_url, make_page):
    """Pierwsza wizyta: animacja wskazuje przyciski „Okrąg” i „Prostokąt” w lewym panelu (a nie klika gdzieś w mapę)."""
    page = make_page(app_url, intro=True)
    page.wait_for_selector("#app-intro:not([hidden])")
    assert page.get_attribute("#app-intro", "data-step") == "tools"
    caption = page.inner_text(".intro-caption p")
    assert "Okrąg" in caption and "Prostokąt" in caption
    x, y = center_of(page, ".tool-button[data-tool=circle]")
    tx = float(page.evaluate("getComputedStyle(document.getElementById('app-intro')).getPropertyValue('--t1x')").strip().rstrip("px"))
    assert abs(tx - x) < 2                                   # kursor jedzie do przycisku „Okrąg”
    page.click(".intro-ok")
    assert page.locator("#app-intro").is_hidden()
    assert page.errors == []


def test_tool_animation_clicks_inside_poland(app_url, make_page):
    """Po wybraniu okręgu animacja klika w środek mapy — przy starcie to Polska (do v3.5 klikała w Litwę)."""
    page = make_page(app_url, intro=True)
    page.click(".intro-ok")
    page.click(".tool-button[data-tool=circle]")
    page.wait_for_selector("#app-intro[data-step=circle]:not([hidden])")
    get = lambda name: float(page.evaluate(  # noqa: E731
        f"getComputedStyle(document.getElementById('app-intro')).getPropertyValue('--{name}')").strip().rstrip("px"))
    b = map_box(page)
    lat, lng = page.evaluate("([x, y]) => { const ll = window.gdzieOtworzyc.map.containerPointToLatLng([x, y]); return [ll.lat, ll.lng]; }",
                             [get("cx") - b["x"], get("cy") - b["y"]])
    assert 49.0 < lat < 54.9 and 14.1 < lng < 24.2, (lat, lng)


def test_click_without_tool_only_hints(app_url, make_page):
    """Kliknięcie w mapę bez wybranego narzędzia niczego nie zaznacza — mówi, co zrobić, a przyciski pulsują."""
    page = make_page(app_url)
    click_map(page)
    assert "Najpierw wybierz" in page.inner_text("#info")
    assert page.locator(".tool-button.attention").count() == 2
    assert page.locator(".circle-handle").count() == 0 and surface_calls(page) == []


# ---------------------------------------------------------------- okrąg ----

@pytest.mark.parametrize("zoom", [6, 11])
def test_circle_has_same_screen_size_and_is_centred(app_url, make_page, zoom):
    """Okrąg po kliknięciu zajmuje ok. 1/5 ekranu przy KAŻDYM przybliżeniu (po oddaleniu nie jest niewidoczną kropką)
    i mapa płynnie przesuwa się tak, że okrąg jest na środku."""
    page = make_page(app_url + view(*BRZEG, zoom))
    draw_circle(page, 0.35, 0.65)
    b = map_box(page)
    cx, cy = center_of(page, ".circle-handle.center")
    ex, ey = center_of(page, ".circle-handle.edge")
    assert abs(cx - (b["x"] + b["width"] / 2)) < 4 and abs(cy - (b["y"] + b["height"] / 2)) < 4
    radius_px = math.hypot(ex - cx, ey - cy)
    assert abs(radius_px / min(b["width"], b["height"]) - CIRCLE_FRACTION) < 0.02
    km = float(page.input_value(".sel-km").replace(",", "."))
    assert (km >= 100) if zoom == 6 else (km < 10)        # przy całej Polsce — województwo, w mieście — kilka km


def test_card_has_no_analyze_until_settings_and_choosing_settings_computes_nothing(app_url, make_page):
    """Bez branży i klientów karta nie udaje, że można analizować: zamiast „Analizuj” mówi, co wybrać, a pola pulsują.
    Wybór klientów NIE uruchamia liczenia — dopiero kliknięcie „Analizuj” (uwaga Marcina)."""
    page = make_page(app_url + view(*BRZEG, 11))
    draw_circle(page)
    assert page.locator(".sel-ok").is_hidden()
    assert "Wybierz po lewej" in page.inner_text(".selection-card")
    assert page.locator("select.attention").count() == 2
    page.select_option("#demand-select", "pop_m")
    page.wait_for_timeout(800)
    assert surface_calls(page) == []                       # nic się nie liczy samo
    assert page.locator(".sel-ok").is_visible() and page.locator("select.attention").count() == 0
    assert page.locator(".leaflet-fog-pane img").count() == 0


def test_edge_dot_changes_radius_and_typed_radius_changes_circle(app_url, make_page):
    page = make_page(app_url + view(*BRZEG, 11))
    draw_circle(page)
    before = float(page.input_value(".sel-km").replace(",", "."))
    ex, ey = center_of(page, ".circle-handle.edge")
    page.mouse.move(ex, ey)
    page.mouse.down()
    page.mouse.move(ex + 90, ey, steps=8)
    page.mouse.up()
    after = float(page.input_value(".sel-km").replace(",", "."))
    assert after > before * 1.3                             # kropka na krawędzi powiększa okrąg
    cx, _ = center_of(page, ".circle-handle.center")
    px_before = center_of(page, ".circle-handle.edge")[0] - cx
    page.fill(".sel-km", str(after / 2).replace(".", ","))
    page.keyboard.press("Enter")
    page.wait_for_timeout(300)
    px_after = center_of(page, ".circle-handle.edge")[0] - cx
    assert 0.4 < px_after / px_before < 0.6                 # wpisany promień zmienia okrąg na mapie


def test_centre_dot_moves_circle(app_url, make_page):
    page = make_page(app_url + view(*BRZEG, 11))
    draw_circle(page)
    cx, cy = center_of(page, ".circle-handle.center")
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(cx + 60, cy + 40, steps=8)
    page.mouse.up()
    nx, ny = center_of(page, ".circle-handle.center")
    ex, ey = center_of(page, ".circle-handle.edge")
    assert abs(nx - cx - 60) < 3 and abs(ny - cy - 40) < 3
    assert abs(ey - ny) < 3 and ex > nx                     # kropka krawędzi przesunęła się razem z okręgiem


def test_second_click_on_tool_drops_it_and_map_pans_again(app_url, make_page):
    """Przy prostokącie lewy przycisk rysuje — drugie kliknięcie „Prostokąt” odznacza narzędzie i mapę znów się przesuwa (Marcin)."""
    page = make_page(app_url + view(*BRZEG, 11))
    page.click(".tool-button[data-tool=rect]")
    assert page.get_attribute(".tool-button[data-tool=rect]", "aria-pressed") == "true"
    page.click(".tool-button[data-tool=rect]")
    assert page.locator(".tool-button[aria-pressed=true]").count() == 0
    before = page.evaluate("window.gdzieOtworzyc.map.getCenter().lng")
    b = map_box(page)
    page.mouse.move(b["x"] + b["width"] * 0.6, b["y"] + b["height"] * 0.5)
    page.mouse.down()
    page.mouse.move(b["x"] + b["width"] * 0.3, b["y"] + b["height"] * 0.5, steps=10)
    page.mouse.up()
    assert page.locator(".rect-handle").count() == 0
    assert page.evaluate("window.gdzieOtworzyc.map.getCenter().lng") > before + 0.01      # mapa przesunęła się


def test_typed_town_gets_5km_circle_and_rect_button_turns_it_into_square(app_url, make_page):
    """Miejscowość z wyszukiwarki: okrąg o średnicy 5 km; kliknięcie „Prostokąt” daje prostokąt podobnych wymiarów w tym miejscu."""
    page = make_page(app_url)
    page.route("**/api/geocode**", lambda r: r.fulfill(
        json=[{"name": "Brzeg, powiat brzeski, opolskie", "lat": BRZEG[0], "lng": BRZEG[1]}]))
    assert page.get_attribute("#search-input", "placeholder") == "lub wpisz miejscowość ręcznie"
    page.fill("#search-input", "Brzeg")
    page.click("#search-results li")
    page.wait_for_selector(".circle-handle.edge")
    page.wait_for_timeout(500)
    assert page.input_value(".sel-km") == "2,5"
    page.click(".tool-button[data-tool=rect]")
    page.wait_for_selector(".rect-handle")
    assert page.locator(".circle-handle").count() == 0
    page.wait_for_timeout(300)
    assert page.locator(".selection-card").count() == 1                 # stara karta okręgu zniknęła
    card = page.inner_text(".selection-card")
    assert "5 × 5 km" in card, card


# ---------------------------------------------------------------- analiza ----

def test_analysis_runs_once_and_fog_only_inside_circle(app_url, make_page):
    page = make_page(app_url + view(*BRZEG, 11))
    page.select_option("#type-select", "beauty")
    draw_circle(page, 0.5, 0.5)
    analyze(page)
    assert len(surface_calls(page)) == 1
    # Prostota (Marcin): w podsumowaniu tylko klienci i firmy, pod nimi źródła — bez werdyktu, rankingu i notatek.
    summary = page.inner_text("#summary")
    assert "Kobiety:" in summary and "OpenStreetMap" in summary and "Konkurencja" not in summary
    assert page.locator("#top-list, #notes").count() == 0
    # Piksel w rogu obrazu mgły (poza okręgiem) jest przezroczysty, środek — nie.
    alpha = page.evaluate("""() => {
      const img = document.querySelector('.leaflet-fog-pane img');
      const c = document.createElement('canvas'); c.width = img.naturalWidth; c.height = img.naturalHeight;
      const ctx = c.getContext('2d'); ctx.drawImage(img, 0, 0);
      const at = (x, y) => ctx.getImageData(x, y, 1, 1).data[3];
      return [at(1, 1), at(Math.floor(c.width / 2), Math.floor(c.height / 2))];
    }""")
    assert alpha[0] == 0 and alpha[1] > 0
    assert page.errors == []


def test_changing_settings_after_analysis_recomputes_same_area(app_url, make_page):
    page = make_page(app_url + view(*BRZEG, 11))
    page.select_option("#type-select", "beauty")
    draw_circle(page, 0.5, 0.5)
    analyze(page)
    first = surface_calls(page)[0]
    page.select_option("#demand-select", "pop_total")
    page.wait_for_timeout(1500)
    calls = surface_calls(page)
    assert len(calls) == 2
    pick = lambda url, key: url.split(f"{key}=")[1].split("&")[0]  # noqa: E731
    assert all(pick(first, k) == pick(calls[1], k) for k in ("lat", "lng", "radius_km"))


def test_zooming_in_rescales_colours_to_what_is_visible(app_url, make_page):
    """„Ten sam kolor, a liczby bardzo różne” (Bydgoszcz): po przybliżeniu skala liczy się z tego, co widać,
    bez nowych zapytań do serwera. Dymek: liczby w promieniu, bez wykładu — wyjaśnienie szacunku jest pod pytajnikiem."""
    page = make_page(app_url + view(*BRZEG, 10))
    page.select_option("#type-select", "beauty")
    draw_circle(page, 0.5, 0.5)
    analyze(page)
    legend = page.inner_text("#legend .stops")
    calls = len(page.api_calls)
    for _ in range(3):
        page.click(".leaflet-control-zoom-in")
        page.wait_for_timeout(700)
    page.wait_for_timeout(500)
    assert page.inner_text("#legend .stops") != legend
    assert len(page.api_calls) == calls                     # przemalowanie bez zapytań
    click_map(page, 0.52, 0.52)
    page.wait_for_selector(".point-popup")
    popup = page.inner_text(".point-popup")
    assert "W promieniu" in popup and "Kolor mapy" not in popup and "Najbliżsi" not in popup
    assert page.locator(".point-popup button.help[data-help=estimate]").count() == 1


# ---------------------------------------------------------------- prostokąt i duży obszar ----

def test_rectangle_drawn_by_dragging_then_analysed(app_url, make_page):
    page = make_page(app_url + view(*BRZEG, 11))
    page.click(".tool-button[data-tool=rect]")
    b = map_box(page)
    page.mouse.move(b["x"] + b["width"] * 0.3, b["y"] + b["height"] * 0.3)
    page.mouse.down()
    page.mouse.move(b["x"] + b["width"] * 0.7, b["y"] + b["height"] * 0.7, steps=10)
    page.mouse.up()
    page.wait_for_selector(".rect-handle")
    assert "×" in page.inner_text(".selection-card") and page.locator(".sel-ok").is_hidden()
    page.select_option("#type-select", "grocery")
    assert page.locator(".sel-ok").is_visible()
    analyze(page)
    assert "OpenStreetMap" in page.inner_text("#summary")
    assert "area=rect" in surface_calls(page)[0]


def test_big_circle_at_country_zoom_without_ranking(app_url, make_page):
    page = make_page(app_url + view(51.5, 18.2, 6))
    page.select_option("#type-select", "beauty")
    draw_circle(page, 0.5, 0.5)
    analyze(page)
    assert "Kobiety" in page.inner_text("#summary")
    assert page.errors == []


def test_reload_starts_from_factory_settings(app_url, make_page):
    """Odświeżenie strony = ustawienia fabryczne (Marcin): bez analizy, bez wybranej branży i narzędzia, adres bez stanu."""
    page = make_page(app_url + view(*BRZEG, 11))
    page.select_option("#type-select", "beauty")
    draw_circle(page, 0.5, 0.5)
    analyze(page)
    assert page.evaluate("location.hash") == ""
    page.reload()
    page.wait_for_function("document.querySelectorAll('#type-select option').length > 1")
    page.wait_for_timeout(500)
    assert page.input_value("#type-select") == "" and page.input_value("#demand-select") == ""
    assert page.locator("#summary-box").is_hidden() and page.locator(".tool-button[aria-pressed=true]").count() == 0
    assert len(surface_calls(page)) == 1                 # po odświeżeniu nic nowego się nie liczy


# ---------------------------------------------------------------- telefon ----

def test_phone_flow(app_url, make_page):
    """Telefon 375×812: narzędzie w zakładce „Ustawienia” (arkusz zwija się, żeby było widać mapę), karta mieści się na ekranie,
    zakładka „Ustawienia” pulsuje, gdy trzeba wybrać klientów, a po „Analizuj” otwierają się „Wnioski”."""
    page = make_page(app_url + view(*BRZEG, 11), mobile=True)
    page.click(".tool-button[data-tool=circle]")
    assert page.locator("#sidebar").is_hidden()            # arkusz zwinięty — mapa na cały ekran
    click_map(page, 0.5, 0.5)
    page.wait_for_selector(".selection-card")
    card = page.locator(".selection-card").bounding_box()
    assert card["x"] >= 0 and card["x"] + card["width"] <= 375
    assert page.locator("#tabs [data-tab=settings].attention").count() == 1
    page.click("#tabs [data-tab=settings]")
    page.select_option("#demand-select", "pop_f")
    page.click("#tabs [data-tab=settings]")                # zwija arkusz z powrotem
    page.click(".sel-ok")
    page.wait_for_selector("#summary-box:not([hidden])")
    assert page.get_attribute("body", "data-tab") == "insights"

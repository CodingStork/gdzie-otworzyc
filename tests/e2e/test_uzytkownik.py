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
    # Kropka w środku prostokąta przesuwa go w całości (rozmiar bez zmian), a ✕ wisi poza kartą, na wysokości tytułu.
    before = page.evaluate("window.gdzieOtworzyc.state.selection.bounds")
    x, y = center_of(page, ".rect-handle.center")
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 80, y + 40, steps=8)
    page.mouse.up()
    after = page.evaluate("window.gdzieOtworzyc.state.selection.bounds")
    assert after["west"] > before["west"] and after["north"] < before["north"]
    assert abs((after["east"] - after["west"]) - (before["east"] - before["west"])) < 1e-6
    card_box = page.locator(".selection-popup .leaflet-popup-content-wrapper").bounding_box()
    x_box = page.locator(".sel-cancel").bounding_box()
    title_box = page.locator(".sel-title").bounding_box()
    assert x_box["x"] >= card_box["x"] + card_box["width"] and abs(x_box["y"] - title_box["y"]) < 10


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


# ---------------------------------------------------------------- klienci, zasięg, dymek (v3.7) ----

def test_build_type_offers_only_construction_and_barber_only_people(app_url, make_page):
    """„Barber + nowe bloki” nie miało sensu (Marcin): budowy są tylko przy „Pracuję przy budowie”, przy innych branżach — ludzie.
    Przy budowach suwak zasięgu nie schodzi poniżej 1 km, bo tyle i tak liczy serwer (pozwolenie znamy z dokładnością do obrębu)."""
    page = make_page(app_url + view(*BRZEG, 11))
    page.select_option("#type-select", "beauty")
    demands = page.eval_on_selector_all("#demand-select option", "os => os.map(o => o.value)")
    assert "pop_f" in demands and not any(d.startswith("new_") for d in demands)
    page.select_option("#type-select", "build")
    demands = page.eval_on_selector_all("#demand-select option", "os => os.map(o => o.value)")
    assert set(demands) == {"", "new_sf", "new_mf", "new_all"} and page.input_value("#demand-select") == "new_all"
    page.eval_on_selector("#reach-input", "s => { s.value = 0; s.dispatchEvent(new Event('input')); }")
    assert float(page.inner_text("#reach-value").replace(",", ".")) >= 1
    layers = page.inner_text("#layer-options")
    assert "Gdzie się buduje" in layers and "Gdzie otworzyć" not in layers


def test_map_colour_equals_popup_number_and_reach_dot_changes_reach(app_url, make_page):
    """„W promieniu 1 km zero nowych bloków, a kolor mówi 2” (Marcin): mapa klientów to liczba w promieniu zasięgu — ta sama
    co w dymku. Dymek wisi nad okręgiem zasięgu, ma ✕ jak karta, a kropka na okręgu zmienia zasięg (suwak też)."""
    page = make_page(app_url + view(*BRZEG, 12))
    page.select_option("#type-select", "beauty")
    draw_circle(page, 0.5, 0.5)
    analyze(page)
    page.click(".tool-button[data-tool=circle]")                          # odznaczamy narzędzie: klik w mapę = szczegóły
    click_map(page, 0.5, 0.55)
    page.wait_for_selector(".point-popup .sel-cancel")
    assert "W promieniu" in page.inner_text(".point-popup")
    ring = page.locator(".circle-handle.edge.reach").bounding_box()
    popup = page.locator(".point-popup .leaflet-popup-content-wrapper").bounding_box()
    assert popup["y"] + popup["height"] < ring["y"] + 5 or popup["x"] > ring["x"] + 5      # dymek nie zasłania kropki zasięgu
    before = page.inner_text("#reach-value")
    x, y = center_of(page, ".circle-handle.edge.reach")
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 60, y, steps=8)
    page.mouse.up()
    page.wait_for_selector(".point-popup .sel-cancel")
    page.wait_for_timeout(800)
    assert page.inner_text("#reach-value") != before
    page.click(".point-popup .sel-cancel")
    page.wait_for_selector(".point-popup", state="detached", timeout=3000)   # ✕ zamyka dymek (po animacji)
    assert page.errors == []


# ---------------------------------------------------------------- telefon ----

PHONE_W, PHONE_H = 375, 812


def on_screen(page, selector, bottom=PHONE_H):
    """Element cały na ekranie telefonu (nad `bottom`, np. nad arkuszem z ustawieniami)."""
    b = page.locator(selector).first.bounding_box()
    return b["x"] >= 0 and b["y"] >= 0 and b["x"] + b["width"] <= PHONE_W and b["y"] + b["height"] <= bottom


def finger_drag(page, x0, y0, x1, y1, steps=12):
    """Przeciągnięcie palcem (zdarzenia dotyku, nie myszy) — tak, jak na telefonie."""
    cdp = page.context.new_cdp_session(page)
    cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x0, "y": y0}]})
    for i in range(1, steps + 1):
        point = {"x": x0 + (x1 - x0) * i / steps, "y": y0 + (y1 - y0) * i / steps}
        cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [point]})
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})


def test_phone_flow(app_url, make_page):
    """Telefon 375×812: narzędzie w zakładce „Ustawienia” (arkusz zwija się, żeby było widać mapę), karta mieści się na ekranie,
    zakładka „Ustawienia” pulsuje, gdy trzeba wybrać klientów, a po „Analizuj” otwierają się „Wnioski”.
    v3.9: karta mówi „w Ustawieniach” (nie „po lewej”), a po rozwinięciu arkusza okrąg z kartą zostają widoczne nad nim."""
    page = make_page(app_url + view(*BRZEG, 11), mobile=True)
    page.tap(".tool-button[data-tool=circle]")
    assert page.locator("#sidebar").is_hidden()            # arkusz zwinięty — mapa na cały ekran
    click_map(page, 0.5, 0.5)
    page.wait_for_selector(".selection-card")
    assert on_screen(page, ".selection-popup .leaflet-popup-content-wrapper") and on_screen(page, ".selection-card .sel-cancel")
    assert "w „Ustawieniach”" in page.inner_text(".selection-card")
    assert page.locator("#tabs [data-tab=settings].attention").count() == 1
    page.tap("#tabs [data-tab=settings]")
    page.wait_for_timeout(300)
    sheet_top = page.locator("#sidebar").bounding_box()["y"]
    assert on_screen(page, ".selection-popup .leaflet-popup-content-wrapper", bottom=sheet_top)
    assert on_screen(page, ".circle-handle.edge", bottom=sheet_top)
    page.select_option("#demand-select", "pop_f")
    page.tap("#tabs [data-tab=settings]")                  # zwija arkusz z powrotem
    page.tap(".sel-ok")
    page.wait_for_selector("#summary-box:not([hidden])")
    assert page.get_attribute("body", "data-tab") == "insights"
    assert page.evaluate("document.documentElement.scrollWidth") <= PHONE_W   # bez przewijania w poziomie
    assert page.errors == []


def test_phone_point_popup_fits_and_reach_dot_works_with_finger(app_url, make_page):
    """Dymek punktu na telefonie: ✕ w rogu dymku (poza nim wypadał za ekran), zasięg zmienia się palcem,
    a przeliczenie nie rozwija arkusza „Wnioski” na pół mapy."""
    page = make_page(app_url + view(*BRZEG, 12), mobile=True)
    page.select_option("#type-select", "beauty")
    page.tap(".tool-button[data-tool=circle]")
    click_map(page, 0.5, 0.5)
    page.wait_for_selector(".sel-ok")
    page.wait_for_timeout(900)
    page.tap(".sel-ok")
    page.wait_for_selector("#summary-box:not([hidden])")
    page.tap("#tabs [data-tab=insights]")                  # zwija „Wnioski” — mapa na cały ekran
    click_map(page, 0.5, 0.55)                             # stuknięcie w zbadany obszar = szczegóły punktu
    page.wait_for_selector(".point-popup .sel-cancel")
    assert on_screen(page, ".point-popup .leaflet-popup-content-wrapper") and on_screen(page, ".point-popup .sel-cancel")
    assert page.locator(".point-popup .sel-cancel").bounding_box()["width"] >= 36   # cel dla palca
    before = page.inner_text("#reach-value")
    x, y = center_of(page, ".circle-handle.edge.reach")
    finger_drag(page, x, y, x + 50, y)
    page.wait_for_selector(".point-popup .sel-cancel")
    page.wait_for_timeout(800)
    assert page.inner_text("#reach-value") != before
    assert "sheet-collapsed" in page.get_attribute("body", "class")
    page.tap(".point-popup .sel-cancel")
    page.wait_for_selector(".point-popup", state="detached", timeout=3000)
    assert page.errors == []


def test_phone_typed_town_and_rectangle_drawn_with_finger(app_url, make_page):
    """Telefon: miejscowość z wyszukiwarki — okrąg i karta mieszczą się nad arkuszem; prostokąt rysuje się palcem."""
    page = make_page(app_url, mobile=True)
    page.route("**/api/geocode**", lambda r: r.fulfill(
        json=[{"name": "Brzeg, powiat brzeski, opolskie", "lat": BRZEG[0], "lng": BRZEG[1]}]))
    page.fill("#search-input", "Brzeg")
    page.tap("#search-results li")
    page.wait_for_selector(".circle-handle.edge")
    page.wait_for_timeout(1500)
    assert on_screen(page, ".selection-popup .leaflet-popup-content-wrapper") and on_screen(page, ".circle-handle.edge")
    page.tap(".selection-card .sel-cancel")
    page.wait_for_selector(".selection-card", state="detached")
    page.tap("#tabs [data-tab=settings]")
    page.tap(".tool-button[data-tool=rect]")
    b = map_box(page)
    finger_drag(page, b["x"] + b["width"] * 0.25, b["y"] + b["height"] * 0.35, b["x"] + b["width"] * 0.75, b["y"] + b["height"] * 0.6)
    page.wait_for_selector(".rect-handle")
    page.wait_for_timeout(500)
    assert "×" in page.inner_text(".selection-card")
    assert on_screen(page, ".selection-popup .leaflet-popup-content-wrapper")
    assert page.errors == []


def test_phone_intro_says_below_attribution_is_one_line_and_buttons_fit_finger(app_url, make_page):
    """Telefon: animacja nie każe szukać przycisków „po lewej”, atrybucja źródeł nie zabiera mapie trzech linii (pełna po
    stuknięciu), przyciski przy mapie mają ok. 40 px."""
    page = make_page(app_url, intro=True, mobile=True)
    page.wait_for_selector("#app-intro:not([hidden])")
    caption = page.inner_text(".intro-caption p")
    assert "poniżej" in caption and "po lewej" not in caption
    page.tap(".intro-ok")
    attribution = ".leaflet-control-attribution"
    one_line = page.locator(attribution).bounding_box()["height"]
    assert one_line < 22
    page.tap(attribution, position={"x": 200, "y": 5})
    assert page.locator(attribution).bounding_box()["height"] > one_line
    for sel in (".leaflet-control-zoom-in", ".intro-button", ".theme-button"):
        assert page.locator(sel).bounding_box()["height"] >= 40, sel

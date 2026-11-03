// Mapa Leaflet: jasny podkład (Esri Light Gray) + mgła (obraz), okrąg obszaru, szczegóły punktu, etykiety i znaczniki top-5.
// Moduł zwraca obiekt MapView — jedyny sposób, w jaki reszta aplikacji dotyka mapy.
//
// Zasada dotycząca kliknięć: jedyne kliknięcie, które coś robi na mapie, to kliknięcie w SAMĄ MAPĘ
// (→ miejsce albo szczegóły). Dlatego mgła (obraz), okrąg i welon są nieinteraktywne, a znaczniki to elementy DOM/SVG,
// które reagują tylko na siebie.
import { fogColor } from './colors.js';

const ATTRIBUTION =
  '© OpenStreetMap contributors © Esri | Firmy: © Overture Maps Foundation | ' +
  'Ludność: © EU, Eurostat GISCO (Census 2021, zmodyfikowane) | Pozwolenia: GUNB RWDZ | Geokodowanie: GUGiK ULDK';
// Podkład: Esri „Light Gray Canvas” (jasnoszary, kafelki bez klucza API). Etykiety są osobną warstwą (Reference),
// żeby leżały NAD mgłą i były czytelne.
const ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/';
const MAX_ZOOM = 16; // Esri Light Gray ma kafelki do poziomu 16
const MIN_ZOOM = 5;

const UPSCALE = 4;   // obraz mgły jest 4 razy gęstszy niż siatka obliczeniowa (płynne przejścia zamiast kwadratów)

// Leaflet wstawia tekst podpowiedzi jako HTML — nazwy firm z OSM (edytowane przez wolontariuszy)
// przekazujemy więc jako element z textContent, żeby znaczniki w nazwie nie były wykonywane.
function plainText(text) {
  const span = document.createElement('span');
  span.textContent = text;
  return span;
}

// Skąd pochodzi firma — pokazujemy w podpowiedzi punktu (kolor ten sam dla obu źródeł).
export const SOURCE_NAMES = { osm: 'OpenStreetMap', overture: 'Overture Maps' };

const smoothstep = (f) => f * f * (3 - 2 * f);

// Rysuje mgłę: t (pozycje 0–1 na skali, NaN = poza okręgiem) interpolujemy między punktami siatki na gęstszą
// siatkę pikseli i DOPIERO TERAZ kolorujemy. Interpolowanie wartości (a nie gotowych kolorów) nie daje obwódek
// ani widocznych kwadratów; funkcja smoothstep wygładza też załamania na granicach komórek.
// Piksele poza okręgiem są przezroczyste (krawędź wygładzona na 1 piksel). Zwraca data URL obrazu PNG.
// `gap` (opcjonalnie): ta sama siatka co `t`, 1 = „mało danych o firmach”. Na takich komórkach rysujemy ukośne szare paski
// (okres `hatch.period` i grubość `hatch.width` w pikselach obrazu); kolor mgły pod paskami zostaje bez zmian.
// `center` = położenie środka okręgu przycinania jako ułamek szerokości i wysokości obrazu (domyślnie środek obrazu).
function renderFog(grid, t, radiusKm, colorOf, gap = null, hatch = { period: 10, width: 3 }, center = { x: 0.5, y: 0.5 }) {
  const { nx, ny, cell_m: cell } = grid;
  const w = nx * UPSCALE;
  const h = ny * UPSCALE;
  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d');
  const image = ctx.createImageData(w, h);
  const lut = Array.from({ length: 256 }, (_, i) => colorOf(i / 255));
  const radiusPx = radiusKm * 1000 / cell * UPSCALE;
  const cx = w * center.x;
  const cy = h * center.y;
  for (let py = 0; py < h; py++) {
    const gy = (py + 0.5) / UPSCALE - 0.5;
    const y0 = Math.floor(gy);
    const fy = smoothstep(gy - y0);
    for (let px = 0; px < w; px++) {
      const edge = radiusPx - Math.hypot(px + 0.5 - cx, py + 0.5 - cy);
      if (edge <= 0) continue;                           // poza okręgiem — zostaje przezroczysty
      const gx = (px + 0.5) / UPSCALE - 0.5;
      const x0 = Math.floor(gx);
      const fx = smoothstep(gx - x0);
      let sum = 0;
      let weight = 0;
      for (let dy = 0; dy < 2; dy++) {
        const yy = y0 + dy;
        if (yy < 0 || yy >= ny) continue;
        for (let dx = 0; dx < 2; dx++) {
          const xx = x0 + dx;
          if (xx < 0 || xx >= nx) continue;
          const value = t[yy * nx + xx];
          if (Number.isNaN(value)) continue;             // sąsiad spoza okręgu nie ciągnie wartości w dół
          const wgt = (dx ? fx : 1 - fx) * (dy ? fy : 1 - fy);
          sum += value * wgt;
          weight += wgt;
        }
      }
      if (weight <= 0) continue;
      const [r, g, b, a] = lut[Math.round((sum / weight) * 255)];
      const o = (py * w + px) * 4;
      image.data[o] = r;
      image.data[o + 1] = g;
      image.data[o + 2] = b;
      image.data[o + 3] = Math.round(a * 255 * Math.min(1, edge));
      if (gap && (px + py) % hatch.period < hatch.width && gap[Math.floor(py / UPSCALE) * nx + Math.floor(px / UPSCALE)] === 1) {
        // pasek: szary (#6b6b6b), półprzezroczysty — widoczny także tam, gdzie sama mgła jest prawie przezroczysta
        image.data[o] = 107;
        image.data[o + 1] = 107;
        image.data[o + 2] = 107;
        image.data[o + 3] = Math.round(0.55 * 255 * Math.min(1, edge));
      }
    }
  }
  ctx.putImageData(image, 0, 0);
  return canvas.toDataURL('image/png');
}

// Pierścień współrzędnych okręgu o promieniu w km (przybliżenie płaskie — wystarcza dla ≤ 30 km).
const CARD_ROOM_PX = 200;           // miejsce nad okręgiem na kartę zaznaczenia (przy dopasowaniu widoku po wyszukaniu)
// Kolory obrysów z CSS (--area, --rect): w trybie nocnym jaśniejsze, żeby było je widać na ciemnym podkładzie.
const cssColor = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const areaColor = () => cssColor('--area');
const rectColor = () => cssColor('--rect');
const isDarkTheme = () => document.documentElement.dataset.theme === 'dark';
// Podkład Esri Canvas: jasnoszary albo ciemnoszary (tryb nocny); etykiety osobno, nad mgłą.
const baseUrl = (dark) => `${ESRI}World_${dark ? 'Dark' : 'Light'}_Gray_Base/MapServer/tile/{z}/{y}/{x}`;
const labelsUrl = (dark) => `${ESRI}World_${dark ? 'Dark' : 'Light'}_Gray_Reference/MapServer/tile/{z}/{y}/{x}`;
const RECT_BAD_COLOR = '#e00000';   // prostokąt poza limitami (za duży / za mały)
const boundsObject = (b) => ({ west: b.getWest(), south: b.getSouth(), east: b.getEast(), north: b.getNorth() });

// Punkt odległy o `km` od (lat, lng) w kierunku `bearing` (stopnie, 0 = północ, 90 = wschód) — wzór na kuli o promieniu 6371 km.
// Dla okręgu o promieniu setek km (całe województwo) przybliżenie płaskie dawałoby wyraźnie spłaszczony kształt.
export function destination(lat, lng, km, bearing) {
  const r = Math.PI / 180;
  const d = km / 6371;
  const b = bearing * r;
  const p1 = lat * r;
  const p2 = Math.asin(Math.sin(p1) * Math.cos(d) + Math.cos(p1) * Math.sin(d) * Math.cos(b));
  const l2 = lng * r + Math.atan2(Math.sin(b) * Math.sin(d) * Math.cos(p1), Math.cos(d) - Math.sin(p1) * Math.sin(p2));
  return [p2 / r, l2 / r];
}

function circleRing(lat, lng, radiusKm, points = 120) {
  return Array.from({ length: points }, (_, i) => destination(lat, lng, radiusKm, (i / points) * 360));
}

// Pozycja Y w rzucie Mercatora (mapa Leaflet) — do ustawienia środka okręgu na obrazie mgły z siatki w Mercatorze.
const mercY = (lat) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI / 180) / 2));

export function initMap(elementId) {
  const map = L.map(elementId, { maxZoom: MAX_ZOOM, minZoom: MIN_ZOOM }).setView([52.07, 19.48], 6);

  // Podkład bez etykiet, żeby mgła leżała pod napisami miast.
  const baseLayer = L.tileLayer(baseUrl(isDarkTheme()), {
    attribution: ATTRIBUTION, maxZoom: MAX_ZOOM,
  }).addTo(map);

  // Panes ustalają kolejność rysowania (zIndex): mgła < okrąg i welon < szczegóły < etykiety < top-5.
  map.createPane('fog').style.zIndex = 410;
  map.createPane('area').style.zIndex = 420;
  map.createPane('details').style.zIndex = 430;
  map.createPane('selection').style.zIndex = 440;   // wybór w toku (okrąg podglądu, prostokąt) leży nad szczegółami
  const labels = map.createPane('labels');
  labels.style.zIndex = 450;
  labels.style.pointerEvents = 'none';
  const labelsLayer = L.tileLayer(labelsUrl(isDarkTheme()), {
    pane: 'labels', maxZoom: MAX_ZOOM,
  }).addTo(map);

  const areaLayer = L.layerGroup().addTo(map);
  const detailsLayer = L.layerGroup().addTo(map);
  // Okrąg, welon i szczegóły: SVG (nie canvas) i nieinteraktywne, żeby nie przechwytywały kliknięć w mapę.
  const areaRenderer = L.svg({ pane: 'area' });
  const detailsRenderer = L.svg({ pane: 'details' });
  const selectionRenderer = L.svg({ pane: 'selection' });
  const selectionLayer = L.layerGroup().addTo(map);   // pinezka, okrąg podglądu / prostokąt i uchwyty wyboru
  let selectionCircle = null;                          // obrys okręgu wyboru
  let circleControl = null;                            // zmiana promienia okręgu wyboru z zewnątrz (pole km w karcie)
  let selectionPopup = null;                           // karta wyboru (własny popup: nie zamyka go kliknięcie w mapę)
  let fogOverlay = null;
  let opacity = 0.85;
  const FADE_MS = 250;   // czas przenikania starej mgły w nową (musi się zgadzać z transition w style.css)

  // Gdy zmieni się rozmiar kontenera mapy (np. zwinięcie panelu na telefonie), Leaflet musi przeliczyć rozmiar.
  new ResizeObserver(() => map.invalidateSize()).observe(document.getElementById(elementId));

  let clickCb = null;
  let suppressClickUntil = 0;                          // po narysowaniu prostokąta przeglądarka wysyła jeszcze „click” — ignorujemy go
  map.on('click', (e) => {
    if (drawing || Date.now() < suppressClickUntil) return;
    if (clickCb) clickCb(e.latlng.lat, e.latlng.lng);
  });
  // Szerokość karty wyboru dopasowana do mapy: z lewej zostaje ok. 105 px na przyciski, 24 px to marginesy popupu, z prawej zapas
  // (mapa bywa wąska — na telefonie albo gdy oba panele są otwarte).
  const cardWidth = () => {
    const max = Math.max(160, Math.min(300, map.getSize().x - 145));
    return { maxWidth: max, minWidth: Math.min(max, 220) };
  };
  const isTouchUi = () => window.matchMedia('(pointer: coarse), (max-width: 767px)').matches;

  // ---- Prostokąt: rysowanie przeciągnięciem (Pointer Events: mysz, dotyk i rysik jednym kodem) ----
  // Tryb rysowania włącza wybór narzędzia „▭ Prostokąt” w lewym panelu (app.js): mapa przestaje się wtedy przesuwać
  // (dragging.disable) i przeciągnięcie rysuje ramkę; po puszczeniu tryb się wyłącza i przesuwanie wraca.
  let drawing = false;
  let rectDrawnCb = null;
  let drawFrom = null;                                 // { latlng, x, y } — początek przeciągnięcia
  let drawPreview = null;
  const helpButton = L.DomUtil.create('a', 'intro-button');   // „?” — pokazuje animację wprowadzającą jeszcze raz
  helpButton.href = '#';
  helpButton.setAttribute('role', 'button');
  helpButton.textContent = '?';
  helpButton.title = 'Jak zaznaczyć obszar na mapie?';
  let helpCb = null;
  const themeButton = L.DomUtil.create('a', 'theme-button');   // ☾ / ☀ — tryb nocny / dzienny
  themeButton.href = '#';
  themeButton.setAttribute('role', 'button');
  let themeCb = null;
  const toolbar = L.Control.extend({
    options: { position: 'topleft' },
    onAdd() {
      const bar = L.DomUtil.create('div', 'leaflet-bar rect-bar');
      bar.append(helpButton, themeButton);
      L.DomEvent.disableClickPropagation(bar);
      L.DomEvent.on(helpButton, 'click', (e) => { L.DomEvent.preventDefault(e); if (helpCb) helpCb(); });
      L.DomEvent.on(themeButton, 'click', (e) => { L.DomEvent.preventDefault(e); if (themeCb) themeCb(); });
      return bar;
    },
  });
  new toolbar().addTo(map);

  function startDraw() {
    drawing = true;
    map.dragging.disable();
    map.getContainer().classList.add('drawing');
  }
  function stopDraw() {
    drawing = false;
    drawFrom = null;
    if (drawPreview) { drawPreview.remove(); drawPreview = null; }
    map.dragging.enable();
    map.getContainer().classList.remove('drawing');
  }
  const container = map.getContainer();
  container.addEventListener('pointerdown', (e) => {
    if (!drawing || !e.isPrimary || (e.pointerType === 'mouse' && e.button !== 0)) return;
    if (e.target.closest('.leaflet-control, .leaflet-popup')) return;
    drawFrom = { latlng: map.mouseEventToLatLng(e), x: e.clientX, y: e.clientY };
    try { container.setPointerCapture(e.pointerId); } catch (err) { /* bez przechwycenia też działa, tylko ruch poza mapą nie jest widziany */ }   // ruch i puszczenie dochodzą do mapy także poza jej krawędzią
    drawPreview = L.rectangle([drawFrom.latlng, drawFrom.latlng], {
      renderer: selectionRenderer, interactive: false, color: rectColor(), weight: 2, dashArray: '6 4', fillColor: rectColor(), fillOpacity: 0.08,
    }).addTo(selectionLayer);
    e.preventDefault();
  });
  container.addEventListener('pointermove', (e) => {
    if (drawFrom) drawPreview.setBounds(L.latLngBounds(drawFrom.latlng, map.mouseEventToLatLng(e)));
  });
  container.addEventListener('pointerup', (e) => {
    if (!drawFrom) return;
    const from = drawFrom;
    suppressClickUntil = Date.now() + 400;
    drawFrom = null;
    if (drawPreview) { drawPreview.remove(); drawPreview = null; }
    if (Math.hypot(e.clientX - from.x, e.clientY - from.y) < 12) return;   // samo stuknięcie, nie przeciągnięcie: dalej rysujemy
    const bounds = L.latLngBounds(from.latlng, map.mouseEventToLatLng(e));
    stopDraw();
    if (rectDrawnCb) rectDrawnCb(boundsObject(bounds));
  });
  container.addEventListener('pointercancel', () => { drawFrom = null; if (drawPreview) { drawPreview.remove(); drawPreview = null; } });
  let drawCancelCb = null;
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && drawing) { stopDraw(); if (drawCancelCb) drawCancelCb(); } });

  // Prostokąt wyboru: ramka + 4 uchwyty w rogach (przeciągnięcie rogu zmienia prostokąt, przeciwległy róg stoi) + karta.
  let rectShape = null;
  let rectHandles = [];
  const cornerLatLngs = (b) => [[b.getNorth(), b.getWest()], [b.getNorth(), b.getEast()], [b.getSouth(), b.getEast()], [b.getSouth(), b.getWest()]];
  const cardAnchor = (b) => [b.getNorth(), (b.getWest() + b.getEast()) / 2];   // karta przy środku północnej krawędzi
  // Zamknięcie dymku (krzyżyk, Escape, kliknięcie w inne miejsce) usuwa szczegóły punktu.
  map.on('popupclose', () => detailsLayer.clearLayers());

  // Animowany lot opiera się na zdarzeniu końca przejścia CSS, które nie dochodzi, gdy karta jest w tle
  // albo rozmiar mapy zmienia się w trakcie. Dlatego: w tle → skok bez animacji; inaczej lot z awaryjnym domknięciem.
  function safeFlyTo(lat, lng, zoom) {
    if (document.hidden) { map.setView([lat, lng], zoom, { animate: false }); return; }
    map.flyTo([lat, lng], zoom);
    setTimeout(() => {
      if (map._animatingZoom) map.setView(map.getCenter(), map.getZoom(), { animate: false });
    }, 2000);
  }

  return {
    leaflet: map,
    onMapClick(cb) { clickCb = cb; },
    safeFlyTo,
    invalidateSize() { map.invalidateSize(); },
    getView() {
      const c = map.getCenter();
      return { zoom: Math.round(map.getZoom()), center: [c.lat, c.lng] };
    },

    // Mgła: t = pozycje 0–1 na skali (NaN poza okręgiem), grid z /api/surface.
    // colorOf: funkcja t → [r,g,b,a]; domyślnie paleta żółto-czerwona (dla trendu: paleta rozbieżna).
    // gap: opcjonalna tablica (1 = mało danych o firmach) na tej samej siatce — rysowana jako szare kreskowanie.
    // center: { lat, lng } środka okręgu przycinania (tylko gdy siatka nie jest wyśrodkowana na okręgu — siatka gotowej mapy w Mercatorze).
    setFog(grid, t, radiusKm, colorOf = fogColor, gap = null, center = null) {
      const bounds = [[grid.south, grid.west], [grid.north, grid.east]];
      const old = fogOverlay;
      // Paski mają mieć ok. 8 px NA EKRANIE, a obraz jest gęstszy niż ekran — przeliczamy okres na piksele obrazu.
      const screenW = Math.abs(map.latLngToContainerPoint([grid.south, grid.east]).x - map.latLngToContainerPoint([grid.south, grid.west]).x);
      const perScreenPx = (grid.nx * UPSCALE) / Math.max(1, screenW);
      const hatch = { period: Math.max(5, Math.round(8 * perScreenPx)), width: Math.max(2, Math.round(2.5 * perScreenPx)) };
      let frac = { x: 0.5, y: 0.5 };
      if (center && grid.projection === 'mercator') {
        frac = { x: (center.lng - grid.west) / (grid.east - grid.west),
          y: (mercY(grid.north) - mercY(center.lat)) / (mercY(grid.north) - mercY(grid.south)) };
      }
      const overlay = L.imageOverlay(renderFog(grid, t, radiusKm, colorOf, gap, hatch, frac), bounds, {
        pane: 'fog', interactive: false, opacity: 0,
      }).addTo(map);
      fogOverlay = overlay;
      // Nowa mgła wjeżdża z przezroczystości, a stara znika po FADE_MS — bez mrugania między „gotową mapą” a mapą na żywo.
      const target = opacity;
      requestAnimationFrame(() => { if (fogOverlay === overlay) overlay.setOpacity(target); });
      if (old) { old.setOpacity(0); setTimeout(() => old.remove(), FADE_MS + 50); }
      if (document.hidden) { overlay.setOpacity(target); if (old) old.remove(); }   // w tle przeglądarka nie odtwarza animacji
    },
    clearFog() {
      if (fogOverlay) { fogOverlay.remove(); fogOverlay = null; }
    },
    clearArea() { areaLayer.clearLayers(); },
    // Widoczny fragment mapy (do zapytań o gotową mapę i mapę na żywo) i szerokość mapy w pikselach.
    viewBounds() {
      const b = map.getBounds();
      return { west: b.getWest(), south: b.getSouth(), east: b.getEast(), north: b.getNorth(), px: map.getSize().x };
    },
    onViewChange(cb) { map.on('moveend', cb); },
    contains(lat, lng) { return map.getBounds().contains([lat, lng]); },
    setView(lat, lng, zoom) { map.setView([lat, lng], zoom, { animate: false }); },
    setFogOpacity(value) {
      opacity = value;
      if (fogOverlay) fogOverlay.setOpacity(value);
    },

    // Wybrane miejsce: pinezka i okrąg obszaru; z `veil` także przygaszenie wszystkiego poza okręgiem
    // (wielokąt świata z „dziurą” w kształcie okręgu). `fit` dopasowuje mapę do okręgu, bez animacji.
    setArea(lat, lng, radiusKm, { veil = false, fit = false } = {}) {
      areaLayer.clearLayers();
      const ring = circleRing(lat, lng, radiusKm);
      if (veil) {
        const world = [[-85, -180], [-85, 180], [85, 180], [85, -180]];
        L.polygon([world, ring], {
          renderer: areaRenderer, interactive: false, stroke: false, fillColor: '#101a3a', fillOpacity: 0.28,
        }).addTo(areaLayer);
      }
      const circle = L.polygon(ring, {
        renderer: areaRenderer, interactive: false, color: areaColor(), weight: 1.5,
        dashArray: veil ? null : '6 4', fill: false,
      }).addTo(areaLayer);
      L.marker([lat, lng], {
        icon: L.divIcon({ className: 'place-pin', iconSize: [14, 14], iconAnchor: [7, 7] }),
        interactive: false, keyboard: false,
      }).addTo(areaLayer);
      if (fit) {
        map.fitBounds(circle.getBounds(), { animate: false, padding: [20, 20] });
      }
    },

    // Szczegóły punktu: okrąg zasięgu, konkurenci [{lat,lng,name,source}] i dymek (bez heksagonów — laikowi nic nie mówią).
    // Zamknięcie dymku usuwa wszystko, co tu narysowano.
    // Szczegóły punktu: okrąg zasięgu klienta z kropką na krawędzi (przeciągnięcie zmienia zasięg — onReach(km) po puszczeniu),
    // konkurenci w zasięgu i dymek NAD okręgiem (zaczepiony w jego najdalszym punkcie na północy), żeby go nie zasłaniał.
    showDetails(lat, lng, reachKm, competitors, element, onReach) {
      map.closePopup();   // stary dymek (jego zamknięcie czyści stare szczegóły) — dopiero potem rysujemy nowe
      let radius = reachKm;
      const ring = L.polygon(circleRing(lat, lng, radius), {
        renderer: detailsRenderer, interactive: false, color: rectColor(), weight: 1.5, fillOpacity: 0.03,
      }).addTo(detailsLayer);
      const size = isTouchUi() ? 28 : 18;
      const edge = L.marker(destination(lat, lng, radius, 90), {
        draggable: true, keyboard: false, autoPan: false, title: 'Przeciągnij, żeby zmienić zasięg klienta',
        icon: L.divIcon({ className: 'circle-handle edge reach', iconSize: [size, size], iconAnchor: [size / 2, size / 2] }),
      }).addTo(detailsLayer);
      for (const p of competitors) {
        L.circleMarker([p.lat, p.lng], {
          renderer: detailsRenderer, radius: 4, color: '#fff', weight: 1, fillColor: rectColor(), fillOpacity: 0.95,
          bubblingMouseEvents: false,
        }).bindTooltip(plainText(`${p.name || 'bez nazwy'} (${SOURCE_NAMES[p.source] || 'OpenStreetMap'})`)).addTo(detailsLayer);
      }
      // Przyciski zoomu i „?” zasłaniają lewy margines mapy — dymek ma się mieścić obok nich. Zamyka go ✕ z treści (jak kartę).
      const narrow = window.innerWidth < 768;
      const popup = L.popup({
        className: 'point-popup', maxWidth: narrow ? 220 : 300, closeButton: false, offset: [0, -4],
        autoPanPaddingTopLeft: [60, 10], autoPanPaddingBottomRight: [10, 10],
      }).setLatLng(destination(lat, lng, radius, 0)).setContent(element).openOn(map);
      edge.on('drag', (e) => {
        radius = Math.min(20, Math.max(0.3, map.distance([lat, lng], e.latlng) / 1000));
        ring.setLatLngs(circleRing(lat, lng, radius));
        popup.setLatLng(destination(lat, lng, radius, 0));
      });
      edge.on('dragend', () => { if (onReach) onReach(radius); });
    },
    closeDetails() { map.closePopup(); },

    // Ile km ma odcinek `fraction` krótszego boku mapy, odmierzony poziomo od punktu (lat, lng) — okrąg po kliknięciu ma zawsze
    // ten sam rozmiar NA EKRANIE (ok. 1/5), niezależnie od przybliżenia: po oddaleniu obejmie województwo, w mieście — osiedla.
    kmForScreenFraction(lat, lng, fraction) {
      const size = map.getSize();
      const px = fraction * Math.min(size.x, size.y);
      const p = map.latLngToContainerPoint([lat, lng]);
      return map.distance([lat, lng], map.containerPointToLatLng([p.x + px, p.y])) / 1000;
    },
    // Płynne przesunięcie mapy tak, żeby punkt był na środku ekranu (bez zmiany przybliżenia).
    panTo(lat, lng) { map.panTo([lat, lng], { animate: !document.hidden, duration: 0.6 }); },
    // Gdy okrąg nie mieści się na ekranie (np. wpisano większy promień), mapa płynnie oddala się, żeby było go widać.
    fitCircleIfNeeded(lat, lng, radiusKm) {
      const bounds = L.latLngBounds(circleRing(lat, lng, radiusKm, 36));
      if (!map.getBounds().contains(bounds)) map.flyToBounds(bounds, { padding: [40, 40], duration: 0.6 });
    },
    // Płynny lot do okręgu (np. miejscowość z wyszukiwarki); w tle — bez animacji. Po dolocie Leaflet wysyła „moveend”.
    flyToCircle(lat, lng, radiusKm) {
      const bounds = L.latLngBounds(circleRing(lat, lng, radiusKm, 36));
      // U góry zostawiamy miejsce na kartę zaznaczenia, która wisi nad okręgiem — okrąg i karta mają się zmieścić razem.
      const padding = { paddingTopLeft: [40, CARD_ROOM_PX], paddingBottomRight: [40, 40] };
      if (document.hidden) map.fitBounds(bounds, { animate: false, ...padding });
      else map.flyToBounds(bounds, { ...padding, duration: 1 });
    },
    // Dopasowanie widoku do okręgu o danym promieniu (bez animacji) — np. przy otwarciu linku.
    fitCircle(lat, lng, radiusKm) {
      map.fitBounds(L.latLngBounds(circleRing(lat, lng, radiusKm, 36)), { animate: false, padding: [40, 40] });
    },

    // Okrąg wyboru: obrys, kropka w środku (przeciągnięcie przesuwa okrąg), kropka na krawędzi (przeciągnięcie zmienia promień)
    // i karta (element DOM z ui.areaCard) nad okręgiem. on.move(lat, lng) / on.radius(km) wołają się przy każdym ruchu kropek.
    // Karta jest własnym popupem (autoClose / closeOnClick wyłączone), żeby kliknięcie w mapę jej nie zamykało.
    showCircle(lat, lng, radiusKm, cardEl, on) {
      this.clearSelection();
      let center = [lat, lng];
      let radius = radiusKm;
      selectionCircle = L.polygon(circleRing(lat, lng, radius), {
        renderer: selectionRenderer, interactive: false, color: areaColor(), weight: 2, dashArray: '6 4',
        fillColor: areaColor(), fillOpacity: 0.06,
      }).addTo(selectionLayer);
      const size = isTouchUi() ? 28 : 18;                // na dotyk kropka jest większa, żeby dało się ją złapać palcem
      const handleIcon = (cls) => L.divIcon({ className: `circle-handle ${cls}`, iconSize: [size, size], iconAnchor: [size / 2, size / 2] });
      const middle = L.marker(center, { draggable: true, keyboard: false, autoPan: false, icon: handleIcon('center'), title: 'Przeciągnij, żeby przesunąć okrąg' })
        .addTo(selectionLayer);
      const edge = L.marker(destination(lat, lng, radius, 90), { draggable: true, keyboard: false, autoPan: false, icon: handleIcon('edge'),
        title: 'Przeciągnij, żeby zmienić promień' }).addTo(selectionLayer);
      selectionPopup = L.popup({
        className: 'selection-popup', closeButton: false, autoClose: false, closeOnClick: false,
        ...cardWidth(), offset: [0, -6], autoPan: false,   // karta nad okręgiem; mapa jest już wyśrodkowana na okręgu
      }).setLatLng(destination(lat, lng, radius, 0)).setContent(cardEl);
      const redraw = () => {
        selectionCircle.setLatLngs(circleRing(center[0], center[1], radius));
        selectionPopup.setLatLng(destination(center[0], center[1], radius, 0));
      };
      middle.on('drag', (e) => {
        center = [e.latlng.lat, e.latlng.lng];
        edge.setLatLng(destination(center[0], center[1], radius, 90));
        redraw();
        on.move(center[0], center[1]);
      });
      edge.on('drag', (e) => {
        radius = Math.min(on.maxKm, Math.max(on.minKm, map.distance(center, e.latlng) / 1000));
        redraw();
        on.radius(radius, false);
      });
      // Po puszczeniu app.js zaokrągla promień (on.radius(…, true) → setCircleRadius), a kropka wraca na wschodni punkt okręgu.
      edge.on('dragend', () => on.radius(radius, true));
      circleControl = {
        setRadius(km) { radius = km; redraw(); edge.setLatLng(destination(center[0], center[1], radius, 90)); },
      };
      map.addLayer(selectionPopup);
    },
    // Promień z pola w karcie (albo zaokrąglony po przeciągnięciu kropki) — bez zapytań do serwera.
    setCircleRadius(km) { if (circleControl) circleControl.setRadius(km); },
    // Po dołożeniu treści do karty (odpowiedź serwera) popup musi przeliczyć rozmiar i położenie.
    refreshSelectionCard() { if (selectionPopup) selectionPopup.update(); },
    clearSelection() {
      if (selectionPopup) { map.removeLayer(selectionPopup); selectionPopup = null; }
      selectionLayer.clearLayers();
      selectionCircle = null;
      circleControl = null;
      rectShape = null;
      rectHandles = [];
    },

    // Narzędzie „▭ Prostokąt” z lewego panelu: startRectDraw włącza rysowanie; onRectDrawn({west, south, east, north}) — narysowano;
    // onDrawCancel — Escape przerwał rysowanie.
    startRectDraw() { if (!drawing) startDraw(); },
    stopRectDraw() { if (drawing) stopDraw(); },
    isDrawing() { return drawing; },
    onHelpClick(cb) { helpCb = cb; },
    onThemeClick(cb) { themeCb = cb; },
    // Tryb nocny: ciemny podkład i etykiety, ikona przycisku pokazuje, na co się przełączy.
    setTheme(dark) {
      baseLayer.setUrl(baseUrl(dark));
      labelsLayer.setUrl(labelsUrl(dark));
      themeButton.textContent = dark ? '☀' : '☾';
      themeButton.title = dark ? 'Tryb dzienny' : 'Tryb nocny';
    },
    onRectDrawn(cb) { rectDrawnCb = cb; },
    onDrawCancel(cb) { drawCancelCb = cb; },

    // Prostokąt wyboru z uchwytami w rogach i kartą (cardEl). onChange(bounds) woła się przy każdym ruchu uchwytu.
    showRect(bounds, cardEl, onChange) {
      this.clearSelection();
      let box = L.latLngBounds([bounds.south, bounds.west], [bounds.north, bounds.east]);
      rectShape = L.rectangle(box, {
        renderer: selectionRenderer, interactive: false, color: rectColor(), weight: 2, dashArray: '6 4', fillColor: rectColor(), fillOpacity: 0.06,
      }).addTo(selectionLayer);
      const size = isTouchUi() ? 28 : 18;                // na dotyk uchwyt jest większy, żeby dało się go złapać palcem
      selectionPopup = L.popup({
        className: 'selection-popup', closeButton: false, autoClose: false, closeOnClick: false,
        ...cardWidth(), offset: [0, -8],
        autoPanPaddingTopLeft: [60, 10], autoPanPaddingBottomRight: [10, 10],
      }).setLatLng(cardAnchor(box)).setContent(cardEl);
      // Rogi 0–3: NW, NE, SE, SW. Uchwyt i przeciwległy róg (i + 2) są względem siebie „przekątną”; dwa pozostałe dzielą z uchwytem
      // szerokość albo długość geograficzną — dlatego po przeciągnięciu za przeciwległy róg prostokąt się odwraca, a nie psuje.
      const sharesLat = (i, j) => (i < 2) === (j < 2);
      const sharesLng = (i, j) => (i === 0 || i === 3) === (j === 0 || j === 3);
      rectHandles = cornerLatLngs(box).map((latlng, i) => {
        const handle = L.marker(latlng, {
          draggable: true, keyboard: false, autoPan: false,
          icon: L.divIcon({ className: 'rect-handle', iconSize: [size, size], iconAnchor: [size / 2, size / 2] }),
        }).addTo(selectionLayer);
        let fixed = null;                                // przeciwległy róg stoi w miejscu
        // Podczas ciągnięcia karta nie może przesuwać mapy (każda zmiana jej położenia uruchamia autoPan) — włączamy go z powrotem po puszczeniu.
        handle.on('dragstart', () => { fixed = rectHandles[(i + 2) % 4].getLatLng(); selectionPopup.options.autoPan = false; });
        handle.on('drag', (e) => {
          const d = e.latlng;
          box = L.latLngBounds(fixed, d);
          rectShape.setBounds(box);
          rectHandles.forEach((other, j) => {
            if (j !== i) other.setLatLng([sharesLat(i, j) ? d.lat : fixed.lat, sharesLng(i, j) ? d.lng : fixed.lng]);
          });
          selectionPopup.setLatLng(cardAnchor(box));
          onChange(boundsObject(box));
        });
        handle.on('dragend', () => {
          rectHandles.forEach((h, j) => h.setLatLng(cornerLatLngs(box)[j]));   // porządkujemy rogi po ewentualnym odwróceniu
          selectionPopup.options.autoPan = true;
          selectionPopup.update();                                              // karta znów mieści się na mapie (autoPan)
        });
        return handle;
      });
      // Kropka w środku: przeciągnięcie przesuwa cały prostokąt (jak kropka w środku okręgu).
      let start = null;
      const middle = L.marker(box.getCenter(), {
        draggable: true, keyboard: false, autoPan: false, title: 'Przeciągnij, żeby przesunąć prostokąt',
        icon: L.divIcon({ className: 'rect-handle center', iconSize: [size, size], iconAnchor: [size / 2, size / 2] }),
      }).addTo(selectionLayer);
      middle.on('dragstart', () => { start = { box, at: middle.getLatLng() }; selectionPopup.options.autoPan = false; });
      middle.on('drag', (e) => {
        const dLat = e.latlng.lat - start.at.lat;
        const dLng = e.latlng.lng - start.at.lng;
        const sw = start.box.getSouthWest();
        const ne = start.box.getNorthEast();
        box = L.latLngBounds([sw.lat + dLat, sw.lng + dLng], [ne.lat + dLat, ne.lng + dLng]);
        rectShape.setBounds(box);
        rectHandles.forEach((h, j) => h.setLatLng(cornerLatLngs(box)[j]));
        selectionPopup.setLatLng(cardAnchor(box));
        onChange(boundsObject(box));
      });
      middle.on('dragend', () => { selectionPopup.options.autoPan = true; selectionPopup.update(); });
      // Rogi przesuwają też środek.
      rectHandles.forEach((h) => h.on('drag', () => middle.setLatLng(box.getCenter())));
      map.addLayer(selectionPopup);
    },
    // Czerwona ramka, gdy prostokąt jest poza limitami.
    setRectInvalid(bad) {
      if (rectShape) rectShape.setStyle({ color: bad ? RECT_BAD_COLOR : rectColor(), weight: bad ? 3 : 2 });
    },

    // Wynik dla prostokąta: obramowanie i (z `veil`) przygaszenie wszystkiego poza nim; `fit` dopasowuje mapę (bez animacji).
    setRectArea(bounds, { veil = false, fit = false } = {}) {
      areaLayer.clearLayers();
      const box = L.latLngBounds([bounds.south, bounds.west], [bounds.north, bounds.east]);
      if (veil) {
        const world = [[-85, -180], [-85, 180], [85, 180], [85, -180]];
        L.polygon([world, cornerLatLngs(box)], {
          renderer: areaRenderer, interactive: false, stroke: false, fillColor: '#101a3a', fillOpacity: 0.28,
        }).addTo(areaLayer);
      }
      L.rectangle(box, {
        renderer: areaRenderer, interactive: false, color: areaColor(), weight: 1.5, dashArray: veil ? null : '6 4', fill: false,
      }).addTo(areaLayer);
      if (fit) map.fitBounds(box, { animate: false, padding: [20, 20] });
    },
  };
}

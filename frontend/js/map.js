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
function renderFog(grid, t, radiusKm, colorOf, gap = null, hatch = { period: 10, width: 3 }) {
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
  const cx = w / 2;
  const cy = h / 2;
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
const RECT_COLOR = '#253494';
const RECT_BAD_COLOR = '#e00000';   // prostokąt poza limitami (za duży / za mały)
const boundsObject = (b) => ({ west: b.getWest(), south: b.getSouth(), east: b.getEast(), north: b.getNorth() });

function circleRing(lat, lng, radiusKm, points = 120) {
  const dlat = radiusKm / 110.54;
  const dlng = radiusKm / (111.32 * Math.cos(lat * Math.PI / 180));
  return Array.from({ length: points }, (_, i) => {
    const a = (i / points) * 2 * Math.PI;
    return [lat + dlat * Math.sin(a), lng + dlng * Math.cos(a)];
  });
}

export function initMap(elementId) {
  const map = L.map(elementId, { maxZoom: MAX_ZOOM, minZoom: MIN_ZOOM }).setView([52.07, 19.48], 6);

  // Podkład bez etykiet, żeby mgła leżała pod napisami miast.
  L.tileLayer(ESRI + 'World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
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
  map.createPane('top').style.zIndex = 470;
  L.tileLayer(ESRI + 'World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}', {
    pane: 'labels', maxZoom: MAX_ZOOM,
  }).addTo(map);

  const topLayer = L.layerGroup().addTo(map);
  const areaLayer = L.layerGroup().addTo(map);
  const detailsLayer = L.layerGroup().addTo(map);
  // Okrąg, welon i szczegóły: SVG (nie canvas) i nieinteraktywne, żeby nie przechwytywały kliknięć w mapę.
  const areaRenderer = L.svg({ pane: 'area' });
  const detailsRenderer = L.svg({ pane: 'details' });
  const selectionRenderer = L.svg({ pane: 'selection' });
  const selectionLayer = L.layerGroup().addTo(map);   // pinezka, okrąg podglądu / prostokąt i uchwyty wyboru
  let selectionCircle = null;                          // okrąg podglądu (zmieniany suwakiem)
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
  const isNarrow = () => window.innerWidth < 768;
  const isTouchUi = () => window.matchMedia('(pointer: coarse), (max-width: 767px)').matches;

  // ---- Prostokąt: przycisk „▭ Prostokąt”, rysowanie przeciągnięciem (Pointer Events: mysz, dotyk i rysik jednym kodem) ----
  // Po kliknięciu przycisku mapa przestaje się przesuwać (dragging.disable) i przeciągnięcie rysuje ramkę; po puszczeniu tryb się
  // wyłącza i przesuwanie wraca. Dzięki przyciskowi zwykłe przeciągnięcie (także palcem na telefonie) nadal przesuwa mapę.
  let drawing = false;
  let drawStartCb = null;
  let rectDrawnCb = null;
  let drawFrom = null;                                 // { latlng, x, y } — początek przeciągnięcia
  let drawPreview = null;
  const rectButton = L.DomUtil.create('a', 'rect-button');
  rectButton.id = 'rect-button';
  rectButton.href = '#';
  rectButton.setAttribute('role', 'button');
  rectButton.textContent = '▭ Prostokąt';
  rectButton.title = 'Zaznacz obszar na mapie przeciągnięciem';
  const toolbar = L.Control.extend({
    options: { position: 'topleft' },
    onAdd() {
      const bar = L.DomUtil.create('div', 'leaflet-bar rect-bar');
      bar.append(rectButton);
      L.DomEvent.disableClickPropagation(bar);
      L.DomEvent.on(rectButton, 'click', (e) => { L.DomEvent.preventDefault(e); drawing ? stopDraw() : startDraw(); });
      return bar;
    },
  });
  new toolbar().addTo(map);

  function startDraw() {
    drawing = true;
    rectButton.classList.add('active');
    map.dragging.disable();
    map.getContainer().classList.add('drawing');
    if (drawStartCb) drawStartCb();
  }
  function stopDraw() {
    drawing = false;
    drawFrom = null;
    if (drawPreview) { drawPreview.remove(); drawPreview = null; }
    rectButton.classList.remove('active');
    map.dragging.enable();
    map.getContainer().classList.remove('drawing');
  }
  const container = map.getContainer();
  container.addEventListener('pointerdown', (e) => {
    if (!drawing || !e.isPrimary || (e.pointerType === 'mouse' && e.button !== 0)) return;
    if (e.target.closest('.leaflet-control, .leaflet-popup')) return;
    drawFrom = { latlng: map.mouseEventToLatLng(e), x: e.clientX, y: e.clientY };
    container.setPointerCapture(e.pointerId);          // ruch i puszczenie dochodzą do mapy także poza jej krawędzią
    drawPreview = L.rectangle([drawFrom.latlng, drawFrom.latlng], {
      renderer: selectionRenderer, interactive: false, color: RECT_COLOR, weight: 2, dashArray: '6 4', fillColor: RECT_COLOR, fillOpacity: 0.08,
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
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && drawing) stopDraw(); });

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
    setFog(grid, t, radiusKm, colorOf = fogColor, gap = null) {
      const bounds = [[grid.south, grid.west], [grid.north, grid.east]];
      const old = fogOverlay;
      // Paski mają mieć ok. 8 px NA EKRANIE, a obraz jest gęstszy niż ekran — przeliczamy okres na piksele obrazu.
      const screenW = Math.abs(map.latLngToContainerPoint([grid.south, grid.east]).x - map.latLngToContainerPoint([grid.south, grid.west]).x);
      const perScreenPx = (grid.nx * UPSCALE) / Math.max(1, screenW);
      const hatch = { period: Math.max(5, Math.round(8 * perScreenPx)), width: Math.max(2, Math.round(2.5 * perScreenPx)) };
      const overlay = L.imageOverlay(renderFog(grid, t, radiusKm, colorOf, gap, hatch), bounds, {
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
    // Tryb „Cała Polska” nie ma pinezki, okręgu ani welonu.
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
        renderer: areaRenderer, interactive: false, color: '#800026', weight: 1.5,
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
    showDetails(lat, lng, reachKm, competitors, element) {
      map.closePopup();   // stary dymek (jego zamknięcie czyści stare szczegóły) — dopiero potem rysujemy nowe
      L.polygon(circleRing(lat, lng, reachKm), {
        renderer: detailsRenderer, interactive: false, color: '#253494', weight: 1.5, fillOpacity: 0.03,
      }).addTo(detailsLayer);
      for (const p of competitors) {
        L.circleMarker([p.lat, p.lng], {
          renderer: detailsRenderer, radius: 4, color: '#fff', weight: 1, fillColor: '#253494', fillOpacity: 0.95,
          bubblingMouseEvents: false,
        }).bindTooltip(plainText(`${p.name || 'bez nazwy'} (${SOURCE_NAMES[p.source] || 'OpenStreetMap'})`)).addTo(detailsLayer);
      }
      // Na wąskim ekranie przyciski zoomu zasłaniają lewy margines mapy — dymek ma się mieścić obok nich.
      const narrow = window.innerWidth < 768;
      L.popup({
        className: 'point-popup', maxWidth: narrow ? 220 : 300,
        autoPanPaddingTopLeft: narrow ? [50, 10] : [10, 10], autoPanPaddingBottomRight: [10, 10],
      }).setLatLng([lat, lng]).setContent(element).openOn(map);
    },
    closeDetails() { map.closePopup(); },

    // Wybór kliknięciem: pinezka + przerywany okrąg podglądu + karta (element DOM z ui.selectionCard) przy punkcie.
    // Karta jest własnym popupem (autoClose / closeOnClick wyłączone), żeby kliknięcie w mapę jej nie zamykało — o tym decyduje app.js.
    showSelection(lat, lng, radiusKm, cardEl) {
      this.clearSelection();
      selectionCircle = L.polygon(circleRing(lat, lng, radiusKm), {
        renderer: selectionRenderer, interactive: false, color: '#800026', weight: 2, dashArray: '6 4',
        fillColor: '#800026', fillOpacity: 0.06,
      }).addTo(selectionLayer);
      L.marker([lat, lng], {
        icon: L.divIcon({ className: 'place-pin', iconSize: [14, 14], iconAnchor: [7, 7] }),
        pane: 'selection', interactive: false, keyboard: false,
      }).addTo(selectionLayer);
      selectionPopup = L.popup({
        className: 'selection-popup', closeButton: false, autoClose: false, closeOnClick: false,
        maxWidth: isNarrow() ? 250 : 300, minWidth: isNarrow() ? 220 : 260, offset: [0, -8],
        autoPanPaddingTopLeft: [50, 10], autoPanPaddingBottomRight: [10, 10],   // 50 px z lewej: przyciski zoomu i prostokąta
      }).setLatLng([lat, lng]).setContent(cardEl);
      map.addLayer(selectionPopup);
    },
    // Dopasowanie widoku do okręgu o danym promieniu (bez animacji).
    fitCircle(lat, lng, radiusKm) {
      map.fitBounds(L.latLng(lat, lng).toBounds(radiusKm * 2000), { animate: false, padding: [40, 40] });
    },
    // Suwak promienia: zmiana okręgu podglądu na żywo, bez zapytań do serwera.
    updateSelectionRadius(lat, lng, radiusKm) {
      if (selectionCircle) selectionCircle.setLatLngs(circleRing(lat, lng, radiusKm));
    },
    // Po dołożeniu treści do karty (odpowiedź serwera) popup musi przeliczyć rozmiar i położenie.
    refreshSelectionCard() { if (selectionPopup) selectionPopup.update(); },
    clearSelection() {
      if (selectionPopup) { map.removeLayer(selectionPopup); selectionPopup = null; }
      selectionLayer.clearLayers();
      selectionCircle = null;
      rectShape = null;
      rectHandles = [];
    },

    // Przycisk „▭ Prostokąt”: onDrawStart — użytkownik włączył rysowanie; onRectDrawn({west, south, east, north}) — skończył.
    onDrawStart(cb) { drawStartCb = cb; },
    onRectDrawn(cb) { rectDrawnCb = cb; },
    stopDraw() { if (drawing) stopDraw(); },

    // Prostokąt wyboru z uchwytami w rogach i kartą (cardEl). onChange(bounds) woła się przy każdym ruchu uchwytu.
    showRect(bounds, cardEl, onChange) {
      this.clearSelection();
      let box = L.latLngBounds([bounds.south, bounds.west], [bounds.north, bounds.east]);
      rectShape = L.rectangle(box, {
        renderer: selectionRenderer, interactive: false, color: RECT_COLOR, weight: 2, dashArray: '6 4', fillColor: RECT_COLOR, fillOpacity: 0.06,
      }).addTo(selectionLayer);
      const size = isTouchUi() ? 28 : 18;                // na dotyk uchwyt jest większy, żeby dało się go złapać palcem
      selectionPopup = L.popup({
        className: 'selection-popup', closeButton: false, autoClose: false, closeOnClick: false,
        maxWidth: isNarrow() ? 250 : 300, minWidth: isNarrow() ? 200 : 220, offset: [0, -8],
        autoPanPaddingTopLeft: [50, 10], autoPanPaddingBottomRight: [10, 10],
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
        handle.on('dragstart', () => { fixed = rectHandles[(i + 2) % 4].getLatLng(); });
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
        handle.on('dragend', () => rectHandles.forEach((h, j) => h.setLatLng(cornerLatLngs(box)[j])));   // porządkujemy rogi po ewentualnym odwróceniu
        return handle;
      });
      map.addLayer(selectionPopup);
    },
    // Czerwona ramka, gdy prostokąt jest poza limitami.
    setRectInvalid(bad) {
      if (rectShape) rectShape.setStyle({ color: bad ? RECT_BAD_COLOR : RECT_COLOR, weight: bad ? 3 : 2 });
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
        renderer: areaRenderer, interactive: false, color: '#800026', weight: 1.5, dashArray: veil ? null : '6 4', fill: false,
      }).addTo(areaLayer);
      if (fit) map.fitBounds(box, { animate: false, padding: [20, 20] });
    },

    // Numerowane znaczniki top-5 (DOM, nie canvas): klik w znacznik wywołuje onClick(place, i).
    setTopMarkers(list, onClick) {
      topLayer.clearLayers();
      list.forEach((place, i) => {
        const icon = L.divIcon({ className: 'top-pin', html: String(i + 1), iconSize: [22, 22], iconAnchor: [11, 11] });
        L.marker([place.lat, place.lng], { icon, pane: 'top', keyboard: false, bubblingMouseEvents: false })
          .on('click', () => onClick(place, i))
          .addTo(topLayer);
      });
    },
  };
}

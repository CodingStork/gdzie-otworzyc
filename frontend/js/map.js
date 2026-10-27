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

const DIM = 0.3;      // mnożnik przezroczystości przygaszonej mgły
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
function renderFog(grid, t, radiusKm, colorOf) {
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
    }
  }
  ctx.putImageData(image, 0, 0);
  return canvas.toDataURL('image/png');
}

// Pierścień współrzędnych okręgu o promieniu w km (przybliżenie płaskie — wystarcza dla ≤ 30 km).
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
  let fogOverlay = null;
  let opacity = 0.85;
  let dimmed = false;

  // Gdy zmieni się rozmiar kontenera mapy (np. zwinięcie panelu na telefonie), Leaflet musi przeliczyć rozmiar.
  new ResizeObserver(() => map.invalidateSize()).observe(document.getElementById(elementId));

  let clickCb = null;
  map.on('click', (e) => clickCb && clickCb(e.latlng.lat, e.latlng.lng));
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
    setFog(grid, t, radiusKm, colorOf = fogColor) {
      if (fogOverlay) fogOverlay.remove();
      const bounds = [[grid.south, grid.west], [grid.north, grid.east]];
      fogOverlay = L.imageOverlay(renderFog(grid, t, radiusKm, colorOf), bounds, {
        pane: 'fog', interactive: false, opacity: opacity * (dimmed ? DIM : 1),
      }).addTo(map);
    },
    clearFog() {
      if (fogOverlay) { fogOverlay.remove(); fogOverlay = null; }
    },
    setFogOpacity(value) {
      opacity = value;
      if (fogOverlay) fogOverlay.setOpacity(value * (dimmed ? DIM : 1));
    },
    // Przygaszenie mgły starego obszaru, gdy użytkownik wskazał nowe miejsce (do 30% zwykłej przezroczystości).
    dimFog(on) {
      dimmed = on;
      if (fogOverlay) fogOverlay.setOpacity(opacity * (on ? DIM : 1));
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

// Mapa Leaflet: jasny podkład (Esri Light Gray) + warstwy na heksagony, etykiety i punkty firm.
// Moduł zwraca obiekt MapView — jedyny sposób, w jaki reszta aplikacji dotyka mapy.
import { colorFor } from './colors.js';

const ATTRIBUTION =
  '© OpenStreetMap contributors © Esri | Ludność: © EU, Eurostat GISCO (Census 2021, zmodyfikowane) | ' +
  'Pozwolenia: GUNB RWDZ | Geokodowanie: GUGiK ULDK';
// Podkład: Esri „Light Gray Canvas” (jasnoszary, kafelki bez klucza API). Oryginalnie planowany CARTO Positron
// wymaga obecnie klucza API (zwraca znak wodny), stąd zamiana. Etykiety są osobną warstwą (Reference).
const ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/';
const MAX_ZOOM = 16; // Esri Light Gray ma kafelki do poziomu 16

export function initMap(elementId) {
  const map = L.map(elementId, { preferCanvas: true, maxZoom: MAX_ZOOM }).setView([52.07, 19.48], 6);

  // Podkład bez etykiet, żeby heksagony leżały pod napisami miast.
  L.tileLayer(ESRI + 'World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
    attribution: ATTRIBUTION, maxZoom: MAX_ZOOM,
  }).addTo(map);

  // Panes ustalają kolejność rysowania (zIndex): heksagony < etykiety < punkty firm.
  map.createPane('hexes').style.zIndex = 410;
  const labels = map.createPane('labels');
  labels.style.zIndex = 450;
  labels.style.pointerEvents = 'none';
  map.createPane('poi').style.zIndex = 460;
  L.tileLayer(ESRI + 'World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}', {
    pane: 'labels', maxZoom: MAX_ZOOM,
  }).addTo(map);

  // Każdy pane z własnym rendererem canvas (domyślny renderer rysuje tylko w overlayPane).
  const hexRenderer = L.canvas({ pane: 'hexes' });
  const hexLayer = L.layerGroup().addTo(map);
  const highlightLayer = L.layerGroup().addTo(map);
  const poiRenderer = L.canvas({ pane: 'poi' });
  const poiLayer = L.layerGroup().addTo(map);

  let pin = null;
  let circle = null;
  let clickCb = null;
  let hexClickCb = null;
  let opacity = 0.7;
  let hexPolygons = [];
  map.on('click', (e) => clickCb && clickCb(e.latlng.lat, e.latlng.lng));

  return {
    leaflet: map,
    onClick(cb) { clickCb = cb; },
    onHexClick(cb) { hexClickCb = cb; },
    setPin(lat, lng) {
      if (pin) pin.setLatLng([lat, lng]); else pin = L.marker([lat, lng]).addTo(map);
    },
    // Okrąg obszaru analizy; radiusKm = null usuwa okrąg (tryb „cała Polska”).
    setAreaCircle(lat, lng, radiusKm) {
      if (circle) { circle.remove(); circle = null; }
      if (radiusKm == null) return;
      circle = L.circle([lat, lng], {
        radius: radiusKm * 1000, color: '#253494', weight: 1.5, fillOpacity: 0.03, interactive: false,
      }).addTo(map);
    },
    clearPin() { if (pin) { pin.remove(); pin = null; } },
    fitArea() { if (circle) map.fitBounds(circle.getBounds()); },
    fitPoland() { map.fitBounds([[49.0, 14.1], [54.85, 24.15]]); },
    // rows: wiersze z API [h3, score, D, S, d, s, pct]; valueIndex wskazuje, którą kolumnę kolorować.
    setHexes(rows, valueIndex, breaks, colors) {
      hexLayer.clearLayers();
      highlightLayer.clearLayers();
      // Kształt heksagonu liczy przeglądarka z identyfikatora H3 (serwer nie wysyła geometrii).
      hexPolygons = rows.map((row) => {
        const polygon = L.polygon(h3.cellToBoundary(row[0]), {
          pane: 'hexes', renderer: hexRenderer, weight: 0.6, color: '#fff', opacity: 0.8,
          fillColor: colorFor(row[valueIndex], breaks, colors), fillOpacity: opacity,
          bubblingMouseEvents: false,   // klik w heksagon nie stawia nowej pinezki
        });
        polygon.on('click', () => hexClickCb && hexClickCb(row, polygon.getBounds().getCenter()));
        polygon.addTo(hexLayer);
        return polygon;
      });
    },
    clearHexes() { hexLayer.clearLayers(); highlightLayer.clearLayers(); hexPolygons = []; },
    setHexOpacity(value) {
      opacity = value;
      hexPolygons.forEach((p) => p.setStyle({ fillOpacity: value }));
    },
    showPopup(latlng, html) { L.popup({ className: 'hex-popup' }).setLatLng(latlng).setContent(html).openOn(map); },
    // Czerwony obrys wskazanego heksagonu (np. po kliknięciu w liście najlepszych miejsc).
    highlightHex(h3Id) {
      highlightLayer.clearLayers();
      if (!h3Id) return;
      L.polygon(h3.cellToBoundary(h3Id), {
        pane: 'poi', fill: false, color: '#d62728', weight: 3, interactive: false,
      }).addTo(highlightLayer);
    },
    // Punkty firm (konkurencja): małe, kontrastowe kółka nad heksagonami.
    setPoi(points) {
      poiLayer.clearLayers();
      for (const p of points) {
        L.circleMarker([p.lat, p.lng], {
          pane: 'poi', renderer: poiRenderer, radius: 4, color: '#fff', weight: 1,
          fillColor: '#D85A30', fillOpacity: 0.95,
        }).bindTooltip(p.name || 'bez nazwy').addTo(poiLayer);
      }
    },
    onMoveEnd(cb) { map.on('moveend', cb); },
    flyTo(lat, lng, zoom) { map.flyTo([lat, lng], zoom); },
    getBbox() { const b = map.getBounds(); return [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]; },
    getZoom() { return map.getZoom(); },
  };
}

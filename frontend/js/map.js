// Mapa Leaflet: jasny podkład (Esri Light Gray) + warstwy na heksagony, etykiety i punkty firm.
// Moduł zwraca obiekt MapView; pozostałe metody (heksagony, punkty) dochodzą w kolejnych taskach.

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

  let pin = null;
  let circle = null;
  let clickCb = null;
  map.on('click', (e) => clickCb && clickCb(e.latlng.lat, e.latlng.lng));

  return {
    leaflet: map,
    onClick(cb) { clickCb = cb; },
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
    flyTo(lat, lng, zoom) { map.flyTo([lat, lng], zoom); },
    getBbox() { const b = map.getBounds(); return [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]; },
    getZoom() { return map.getZoom(); },
  };
}

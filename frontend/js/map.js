// Mapa Leaflet: jasny podkład (Esri Light Gray) + warstwy na heksagony, etykiety, punkty firm i znaczniki top-5.
// Moduł zwraca obiekt MapView — jedyny sposób, w jaki reszta aplikacji dotyka mapy.
//
// Zasada dotycząca kliknięć (naprawa błędu z v1): jedyne kliknięcie, które coś robi na mapie, to kliknięcie
// w SAMĄ MAPĘ (→ dymek z liczbami). Leaflet rysuje warstwy canvas jako osobny <canvas> na całą mapę dla
// każdego pane'u — taki canvas przechwytuje kliknięcia, więc: heksagony (canvas) mają pointer-events: none
// (patrz style.css), a punkty firm i znaczniki to elementy SVG/DOM, które reagują tylko na siebie.
import { gradientColor } from './colors.js';

const ATTRIBUTION =
  '© OpenStreetMap contributors © Esri | Ludność: © EU, Eurostat GISCO (Census 2021, zmodyfikowane) | ' +
  'Pozwolenia: GUNB RWDZ | Geokodowanie: GUGiK ULDK';
// Podkład: Esri „Light Gray Canvas” (jasnoszary, kafelki bez klucza API). Oryginalnie planowany CARTO Positron
// wymaga obecnie klucza API (zwraca znak wodny), stąd zamiana. Etykiety są osobną warstwą (Reference).
const ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/';
const MAX_ZOOM = 16; // Esri Light Gray ma kafelki do poziomu 16
const MIN_ZOOM = 5;  // poniżej i tak pokazujemy najgrubszą siatkę (res 5)

const FADE_LOD_MS = 400;   // zmiana rozdzielczości heksagonów: nowa siatka „wypływa”, stara gaśnie
const FADE_PAN_MS = 150;   // samo przesunięcie mapy: krótkie wygładzenie

// Leaflet wstawia tekst podpowiedzi jako HTML — nazwy firm z OSM (edytowane przez wolontariuszy)
// przekazujemy więc jako element z textContent, żeby znaczniki w nazwie nie były wykonywane.
function plainText(text) {
  const span = document.createElement('span');
  span.textContent = text;
  return span;
}

export function initMap(elementId) {
  const map = L.map(elementId, { maxZoom: MAX_ZOOM, minZoom: MIN_ZOOM }).setView([52.07, 19.48], 6);

  // Podkład bez etykiet, żeby heksagony leżały pod napisami miast.
  L.tileLayer(ESRI + 'World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
    attribution: ATTRIBUTION, maxZoom: MAX_ZOOM,
  }).addTo(map);

  // Panes ustalają kolejność rysowania (zIndex): heksagony A/B < etykiety < punkty firm < znaczniki top-5.
  const paneA = map.createPane('hexesA');
  const paneB = map.createPane('hexesB');
  paneA.style.zIndex = 410;
  paneB.style.zIndex = 411;
  for (const pane of [paneA, paneB]) {
    pane.classList.add('hex-pane');
    pane.style.opacity = 0;
  }
  const labels = map.createPane('labels');
  labels.style.zIndex = 450;
  labels.style.pointerEvents = 'none';
  map.createPane('poi').style.zIndex = 460;
  map.createPane('top').style.zIndex = 470;
  L.tileLayer(ESRI + 'World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}', {
    pane: 'labels', maxZoom: MAX_ZOOM,
  }).addTo(map);

  // Dwa „sloty” na heksagony; rysujemy w nieaktywnym, potem płynnie je zamieniamy (crossfade).
  const slots = ['A', 'B'].map((name) => ({
    paneName: 'hexes' + name,
    pane: map.getPane('hexes' + name),
    renderer: L.canvas({ pane: 'hexes' + name }),
    group: L.layerGroup().addTo(map),
  }));
  let active = 0;           // indeks slotu aktualnie widocznego
  let opacity = 0.7;        // przezroczystość ustawiona suwakiem
  let hasHexes = false;
  let generation = 0;       // numer ostatniego rysowania — spóźnione sprzątanie starego slotu ignorujemy, gdy jest nowsze

  const topLayer = L.layerGroup().addTo(map);
  // Punkty firm: renderer SVG (nie canvas!) — reaguje tylko na kliknięcia w same kółka.
  const poiRenderer = L.svg({ pane: 'poi' });
  const poiLayer = L.layerGroup().addTo(map);

  // Gdy zmieni się rozmiar kontenera mapy (np. zwinięcie panelu na telefonie), Leaflet musi przeliczyć rozmiar.
  new ResizeObserver(() => map.invalidateSize()).observe(document.getElementById(elementId));

  let clickCb = null;
  let pointCircle = null;
  map.on('click', (e) => clickCb && clickCb(e.latlng.lat, e.latlng.lng));
  // Zamknięcie dymku (krzyżyk, Escape, kliknięcie w inne miejsce) usuwa okrąg zasięgu.
  map.on('popupclose', () => {
    if (pointCircle) { pointCircle.remove(); pointCircle = null; }
    document.body.classList.remove('popup-open');
  });
  // Na telefonie kontrolki (warstwy, legenda) zasłaniałyby dymek — na czas jego otwarcia się chowają (patrz style.css).
  map.on('popupopen', () => document.body.classList.add('popup-open'));

  // Animowany lot opiera się na zdarzeniu końca przejścia CSS, które nie dochodzi, gdy karta jest w tle
  // albo rozmiar mapy zmienia się w trakcie — mapa zostawała w stanie pośrednim (rozmazane etykiety).
  // Dlatego: w tle → skok bez animacji; w przeciwnym razie lot z awaryjnym domknięciem po 2 s.
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
    onMoveEnd(cb) { map.on('moveend', cb); },
    safeFlyTo,
    // Ustawienie widoku z linku: bez animacji.
    setView(lat, lng, zoom) { map.setView([lat, lng], zoom, { animate: false }); },
    invalidateSize() { map.invalidateSize(); },
    getView() {
      const b = map.getBounds();
      const c = map.getCenter();
      return { bbox: [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()], zoom: Math.round(map.getZoom()), center: [c.lat, c.lng] };
    },

    // rows: wiersze z API [h3, score, D, S, pct_score, pct_D, pct_S]; pctIndex wskazuje kolumnę percentyla do kolorowania.
    // fade: true przy zmianie rozdzielczości (dłuższe przejście), false przy samym przesunięciu.
    setHexes(rows, pctIndex, { fade = false } = {}) {
      const ms = fade ? FADE_LOD_MS : FADE_PAN_MS;
      const old = slots[active];
      const next = slots[1 - active];
      const mine = ++generation;
      next.group.clearLayers();
      for (const row of rows) {
        // Kształt heksagonu liczy przeglądarka z identyfikatora H3 (serwer nie wysyła geometrii).
        L.polygon(h3.cellToBoundary(row[0]), {
          pane: next.paneName, renderer: next.renderer, interactive: false,
          weight: 0.5, color: '#fff', opacity: 0.6, fillColor: gradientColor(row[pctIndex]), fillOpacity: 1,
        }).addTo(next.group);
      }
      // Nowa siatka zaczyna od przezroczystości 0 i w następnej klatce płynnie rośnie do wartości suwaka,
      // a stara jednocześnie gaśnie (transition w CSS: opacity).
      next.pane.style.transition = old.pane.style.transition = `opacity ${ms}ms`;
      next.pane.style.opacity = 0;
      active = 1 - active;
      requestAnimationFrame(() => {
        next.pane.style.opacity = rows.length ? opacity : 0;
        old.pane.style.opacity = 0;
      });
      hasHexes = rows.length > 0;
      // Po zakończeniu przejścia czyścimy stary slot (timeout zamiast transitionend: zdarzenie bywa gubione).
      setTimeout(() => { if (mine === generation) old.group.clearLayers(); }, ms + 80);
    },
    clearHexes() {
      generation++;
      for (const s of slots) { s.group.clearLayers(); s.pane.style.opacity = 0; }
      hasHexes = false;
    },
    setHexOpacity(value) {
      opacity = value;
      if (hasHexes) slots[active].pane.style.opacity = value;
    },

    // Dymek z liczbami + okrąg zasięgu. Zamknięcie dymku usuwa okrąg.
    showPoint(lat, lng, radiusKm, element) {
      map.closePopup();   // stary dymek (jego zamknięcie usuwa stary okrąg) — dopiero potem rysujemy nowy
      pointCircle = L.circle([lat, lng], {
        radius: radiusKm * 1000, color: '#253494', weight: 1.5, fillOpacity: 0.04, interactive: false,
      }).addTo(map);
      // Na wąskim ekranie przyciski zoomu zasłaniają lewy margines mapy — dymek ma się mieścić obok nich.
      const narrow = window.innerWidth < 768;
      L.popup({
        className: 'hex-popup', maxWidth: narrow ? 220 : 300,
        autoPanPaddingTopLeft: narrow ? [50, 10] : [10, 10], autoPanPaddingBottomRight: [10, 10],
      }).setLatLng([lat, lng]).setContent(element).openOn(map);
    },
    closePoint() { map.closePopup(); },

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

    // Punkty firm (konkurencja): małe, kontrastowe kółka nad heksagonami.
    setPoi(points) {
      poiLayer.clearLayers();
      for (const p of points) {
        L.circleMarker([p.lat, p.lng], {
          pane: 'poi', renderer: poiRenderer, radius: 4, color: '#fff', weight: 1,
          fillColor: '#D85A30', fillOpacity: 0.95, bubblingMouseEvents: false,
        }).bindTooltip(plainText(p.name || 'bez nazwy')).addTo(poiLayer);
      }
    },
  };
}

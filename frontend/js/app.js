// Punkt startowy frontendu: spina mapę, panel boczny i API.
// Obszar analizy to widoczny fragment mapy: wynik odświeża się sam po przesunięciu/przybliżeniu mapy
// i po zmianie formularza. Kliknięcie mapy pokazuje dymek z dokładnymi liczbami dla klikniętego punktu.
import { getCatalog, getMeta, getPoi, point, view as fetchView } from './api.js';
import { logColor, logScale } from './colors.js';
import { initMap } from './map.js';
import * as ui from './ui.js';

const $ = (id) => document.getElementById(id);
const map = initMap('map');
// center: środek opcjonalnego obszaru (miejsce z wyszukiwarki albo punkt z dymku) — promień czytamy z pola w panelu.
const state = { result: null, displayRes: null, controller: null, requestId: 0, center: null };

// Warstwy mapy: indeks wartości w wierszu heksagonu [h3, score, D, S, ...] i nagłówek legendy.
const LAYERS = {
  score: { value: 1, title: 'Klienci na firmę' },
  D: { value: 2, title: 'Popyt w zasięgu' },
  S: { value: 3, title: 'Konkurencja w zasięgu' },
};

const isMobile = () => window.matchMedia('(max-width: 767px)').matches;
const NOTHING_SELECTED = 'Wybierz typ działalności albo czynnik popytu';

// Na telefonie zwijamy panel, żeby odsłonić mapę; po zmianie rozmiaru Leaflet musi przeliczyć widok.
function collapseSheetOnMobile() {
  if (!isMobile()) return;
  $('sidebar').classList.add('collapsed');
  map.invalidateSize();
}

// ---- Opcjonalny obszar: okrąg o podanym promieniu wokół wybranego środka ----

// { lat, lng, radius } albo null, gdy nie ma środka lub promień jest pusty.
function activeArea() {
  const radius = ui.areaRadius();
  return state.center && radius ? { lat: state.center.lat, lng: state.center.lng, radius } : null;
}

// Odległość po kuli w km (haversine) — tak samo liczy serwer przy wyborze top-5 w okręgu.
function distanceKm(lat1, lng1, lat2, lng2) {
  const rad = Math.PI / 180;
  const a = Math.sin((lat2 - lat1) * rad / 2) ** 2 +
    Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin((lng2 - lng1) * rad / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.sqrt(a));
}

// Heksagony, których środek leży w okręgu (bez obszaru — wszystkie).
function rowsInArea(rows, area) {
  if (!area) return rows;
  return rows.filter((row) => {
    const [lat, lng] = h3.cellToLatLng(row[0]);
    return distanceKm(area.lat, area.lng, lat, lng) <= area.radius;
  });
}

// Rysuje okrąg (albo go usuwa) i, gdy `fit`, dopasowuje do niego mapę. Wynik rysujemy od razu z nowym filtrem,
// a odświeżenie z serwera dociągnie top-5 dla okręgu.
function applyArea(fit) {
  const area = activeArea();
  if (area) map.setArea(area.lat, area.lng, area.radius, { fit }); else map.clearArea();
  drawLayer();
  if (fit) scheduleRefresh();
  writeHash();
}

function setCenter(lat, lng, name) {
  state.center = { lat, lng, name };
  ui.setAreaCenter(name);
}

// Miejsce z wyszukiwarki: z promieniem — mapa dopasowuje się do okręgu, bez — jak dotąd przelatuje do miejsca.
function pickPlace(place) {
  setCenter(place.lat, place.lng, place.name.split(',')[0]);
  if (ui.areaRadius()) applyArea(true);
  else { applyArea(false); map.safeFlyTo(place.lat, place.lng, 14); }
}

// „Ustaw jako środek” w dymku: ten punkt staje się środkiem, a użytkownik wpisuje promień.
function useAsCenter(lat, lng) {
  setCenter(lat, lng, 'wybrany punkt');
  map.closePoint();
  $('sidebar').classList.remove('collapsed');
  if (ui.areaRadius()) applyArea(true); else { applyArea(false); ui.focusAreaRadius(); }
}

// ---- Rysowanie wyniku ----

// Rysuje wybraną warstwę z ostatniego wyniku — bez ponownego zapytania do serwera.
// Skala kolorów (logarytmiczna) wynika z heksagonów, które faktycznie rysujemy.
function drawLayer(fade = false) {
  const result = state.result;
  const rows = result ? rowsInArea(result.hexes, activeArea()) : [];
  if (!rows.length) { map.clearHexes(); ui.hideLegend(); return; }
  const layer = LAYERS[ui.currentLayer()];
  const scale = logScale(rows.map((row) => row[layer.value]));
  map.setHexes(rows, (row) => logColor(row[layer.value], scale), { fade });
  // Dla czynników z pozwoleń podajemy okres danych i zastrzeżenie (pozwolenie ≠ wybudowany dom).
  const period = result.permits_period;
  const note = period && ui.currentLayer() !== 'S'
    ? `Pozwolenia: ${period.from} – ${period.to}. Pozwolenie nie oznacza wybudowanego domu.` : '';
  const title = ui.currentLayer() === 'score' && period ? 'Nowe budowy na firmę' : layer.title;
  ui.renderLegend(title, scale, note);
}

function showResult(result) {
  const resChanged = state.displayRes !== null && state.displayRes !== result.display_res;
  state.result = result;
  state.displayRes = result.display_res;
  ui.setLayerAvailability(result.mode);
  drawLayer(resChanged);
  ui.renderWarnings(result.warnings);
  ui.renderNotes(result.notes);
  ui.renderTop(result.top, result.top_metric, (place) => openPlace(place));
  map.setTopMarkers(result.top, (place) => openPlace(place));
}

function clearResult(message) {
  state.result = null;
  map.clearHexes();
  map.setTopMarkers([], () => {});
  map.closePoint();
  ui.hideLegend();
  ui.renderWarnings([]);
  ui.renderNotes([]);
  ui.renderTop([], 'score', () => {});
  ui.showInfo(message);
}

// ---- Odświeżanie wyniku dla widocznego fragmentu mapy ----

let refreshTimer = null;
function scheduleRefresh() {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(refresh, 250);   // debounce: czekamy, aż użytkownik skończy przesuwać mapę / zmieniać formularz
}

async function refresh() {
  const params = ui.selectedParams();
  loadPoi();
  if (!params.type && !params.demand) {
    if (state.controller) state.controller.abort();
    ui.setLoading(false);
    clearResult(NOTHING_SELECTED);
    writeHash();
    return;
  }
  ui.showInfo('');
  ui.showError('');
  if (state.controller) state.controller.abort();   // poprzednie zapytanie jest już nieaktualne
  const controller = new AbortController();
  state.controller = controller;
  const mine = ++state.requestId;
  const { bbox, zoom } = map.getView();
  if (bbox[0] >= bbox[2] || bbox[1] >= bbox[3]) { ui.setLoading(false); return; }   // mapa jeszcze bez rozmiaru — poczekaj na moveend
  ui.setLoading(true);
  try {
    const area = activeArea();
    const areaParam = area ? `${area.lat.toFixed(5)},${area.lng.toFixed(5)},${area.radius}` : undefined;
    const result = await fetchView({ ...params, bbox: bbox.join(','), zoom, area: areaParam }, controller.signal);
    if (mine !== state.requestId) return;
    showResult(result);
    writeHash();
  } catch (e) {
    if (e.name === 'AbortError') return;   // zastąpione nowszym zapytaniem
    if (mine !== state.requestId) return;
    ui.showError(e.message);
  } finally {
    if (mine === state.requestId) ui.setLoading(false);
  }
}

// ---- Dymek klikniętego punktu ----

let pointRequest = 0;

// Dymek opisuje ustawienia z chwili kliknięcia: po zmianie formularza lub linku zamykamy go i ignorujemy spóźnioną odpowiedź.
function discardPoint() {
  pointRequest++;
  map.closePoint();
}

async function showPointAt(lat, lng) {
  const params = ui.selectedParams();
  if (!params.type && !params.demand) { ui.showInfo(NOTHING_SELECTED); return; }
  const mine = ++pointRequest;
  try {
    const data = await point({ ...params, lat, lng });
    if (mine !== pointRequest) return;
    map.showPoint(lat, lng, data.radius_km, ui.pointPopup(data, () => useAsCenter(lat, lng)));
  } catch (e) {
    if (mine === pointRequest) ui.showError(e.message);
  }
}

// Wskazane miejsce (z listy top-5 albo ze znacznika): przybliżamy mapę i pokazujemy dymek z liczbami.
function openPlace(place) {
  map.safeFlyTo(place.lat, place.lng, Math.max(map.getView().zoom, 14));
  collapseSheetOnMobile();
  showPointAt(place.lat, place.lng);
}

// ---- Stan widoku w adresie URL (#type=beauty&demand=pop_f&bw=1.5&lat=…&lng=…&z=13) — link można komuś wysłać ----

function writeHash() {
  const params = ui.selectedParams();
  const { center, zoom } = map.getView();
  const hash = new URLSearchParams({
    type: params.type, demand: params.demand, bw: params.bandwidth_km, layer: ui.currentLayer(),
    lat: center[0].toFixed(5), lng: center[1].toFixed(5), z: zoom,
  });
  if (params.months) hash.set('m', params.months);   // okres tylko dla czynników z pozwoleń
  if (state.center) {                                  // środek obszaru (clat, clng, cn) i opcjonalny promień (cr)
    hash.set('clat', state.center.lat.toFixed(5));
    hash.set('clng', state.center.lng.toFixed(5));
    hash.set('cn', state.center.name);
    if (ui.areaRadius()) hash.set('cr', ui.areaRadius());
  }
  history.replaceState(null, '', '#' + hash);
}

// Środek i promień obszaru z adresu (bez dopasowywania mapy: widok zapisany jest osobno w lat, lng, z).
function restoreArea(h) {
  const lat = Number(h.get('clat'));
  const lng = Number(h.get('clng'));
  if (h.get('clat') && h.get('clng') && Number.isFinite(lat) && Number.isFinite(lng)) {
    setCenter(lat, lng, h.get('cn') || 'wybrane miejsce');
    const radius = Number(h.get('cr'));
    ui.setAreaRadius(Number.isFinite(radius) && radius > 0 ? Math.min(50, Math.round(radius)) : null);
  } else {
    state.center = null;
    ui.setAreaCenter(null);
    ui.setAreaRadius(null);
  }
  const area = activeArea();
  if (area) map.setArea(area.lat, area.lng, area.radius, { fit: false }); else map.clearArea();
}

// Odtwarza ustawienia i widok z adresu; zwraca true, jeśli adres zawierał zapisany widok.
// Stare parametry z v1 (r, pl) są ignorowane.
function applyHash() {
  const h = new URLSearchParams(location.hash.slice(1));
  if (!h.has('type') && !h.has('demand')) return false;
  ui.setSelection({ type: h.get('type'), demand: h.get('demand'), bandwidth: h.get('bw'), months: h.get('m') });
  restoreArea(h);
  if (h.get('layer') in LAYERS) document.querySelector(`input[name=layer][value="${h.get('layer')}"]`).checked = true;
  const lat = Number(h.get('lat'));
  const lng = Number(h.get('lng'));
  const z = Number(h.get('z'));
  // Dopasowanie widoku bez animacji (animowany zoom potrafi utknąć w stanie pośrednim).
  if (h.get('lat') && h.get('lng') && Number.isFinite(lat) && Number.isFinite(lng)) {
    map.setView(lat, lng, Number.isFinite(z) && z > 0 ? z : 12);
  }
  return true;
}

// ---- Punkty firm: pobieramy tylko dla widocznego fragmentu mapy i tylko przy dużym przybliżeniu ----
const POI_MIN_ZOOM = 11;
let poiTimer = null;
let poiRequest = 0;

function loadPoi() {
  clearTimeout(poiTimer);
  poiTimer = setTimeout(doLoadPoi, 300);
}

async function doLoadPoi() {
  const note = $('poi-note');
  const request = ++poiRequest;          // odpowiedzi spóźnione względem nowszego zapytania ignorujemy
  const type = $('type-select').value;
  if (!$('poi-checkbox').checked || !type) { map.setPoi([]); note.hidden = true; return; }
  const { bbox, zoom } = map.getView();
  if (zoom < POI_MIN_ZOOM) {
    map.setPoi([]);
    note.textContent = 'Przybliż mapę, aby zobaczyć firmy';
    note.hidden = false;
    return;
  }
  try {
    const data = await getPoi(type, bbox);
    if (request !== poiRequest) return;
    map.setPoi(data.items);
    note.textContent = data.truncated ? 'Pokazano 5000 pierwszych firm' : '';
    note.hidden = !data.truncated;
  } catch (e) {
    if (request === poiRequest) { note.textContent = e.message; note.hidden = false; }
  }
}

// ---- Podłączenie zdarzeń ----
map.onMapClick((lat, lng) => showPointAt(lat, lng));
map.onMoveEnd(scheduleRefresh);

$('poi-checkbox').addEventListener('change', loadPoi);
document.querySelectorAll('input[name=layer]').forEach((el) => el.addEventListener('change', () => {
  drawLayer();
  writeHash();
}));
$('opacity-input').addEventListener('input', () => map.setHexOpacity(Number($('opacity-input').value)));

// Mobile: uchwyt zwija i rozwija arkusz.
$('sheet-handle').addEventListener('click', () => $('sidebar').classList.toggle('collapsed'));

ui.renderHelp();
ui.initSearch(pickPlace);
ui.initArea(() => applyArea(true));

// Wklejenie innego linku w tej samej karcie zmienia tylko hash (bez przeładowania) — odtwórz widok.
window.addEventListener('hashchange', () => { if (applyHash()) { discardPoint(); scheduleRefresh(); } });

getMeta().then(ui.renderFooter).catch(() => { /* stopka jest dodatkiem — brak metadanych nie przeszkadza */ });
getCatalog()
  .then((catalog) => {
    // Zmiana formularza unieważnia dymek punktu (opisuje poprzednie ustawienia) i odświeża wynik.
    ui.renderCatalog(catalog, () => { discardPoint(); scheduleRefresh(); });
    applyHash();
    scheduleRefresh();   // jedno zapytanie (z opóźnieniem 250 ms); setView z linku wywołuje moveend, który tylko je odnowi
  })
  .catch((e) => ui.showError(e.message));

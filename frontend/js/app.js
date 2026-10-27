// Punkt startowy frontendu: spina mapę, panel boczny i API.
// Obszar analizy to widoczny fragment mapy: wynik odświeża się sam po przesunięciu/przybliżeniu mapy
// i po zmianie formularza. Kliknięcie mapy pokazuje dymek z dokładnymi liczbami dla klikniętego punktu.
import { getCatalog, getMeta, getPoi, point, view as fetchView } from './api.js';
import { initMap } from './map.js';
import * as ui from './ui.js';

const $ = (id) => document.getElementById(id);
const map = initMap('map');
const state = { result: null, displayRes: null, controller: null, requestId: 0 };

// Warstwy mapy: indeks kolumny percentyla w wierszu heksagonu [h3, score, D, S, pct_score, pct_D, pct_S],
// klucz w `legend` z odpowiedzi i nagłówek legendy.
const LAYERS = {
  score: { pct: 4, legend: 'score', title: 'Klienci na firmę' },
  D: { pct: 5, legend: 'D', title: 'Popyt w zasięgu' },
  S: { pct: 6, legend: 'S', title: 'Konkurencja w zasięgu' },
};

const isMobile = () => window.matchMedia('(max-width: 767px)').matches;
const NOTHING_SELECTED = 'Wybierz typ działalności albo czynnik popytu';

// Na telefonie zwijamy panel, żeby odsłonić mapę; po zmianie rozmiaru Leaflet musi przeliczyć widok.
function collapseSheetOnMobile() {
  if (!isMobile()) return;
  $('sidebar').classList.add('collapsed');
  map.invalidateSize();
}

// ---- Rysowanie wyniku ----

// Rysuje wybraną warstwę z ostatniego wyniku — bez ponownego zapytania do serwera.
function drawLayer(fade = false) {
  const result = state.result;
  if (!result || !result.hexes.length) { map.clearHexes(); ui.hideLegend(); return; }
  const layer = LAYERS[ui.currentLayer()];
  map.setHexes(result.hexes, layer.pct, { fade });
  // Dla czynników z pozwoleń podajemy okres danych i zastrzeżenie (pozwolenie ≠ wybudowany dom).
  const period = result.permits_period;
  const note = period && ui.currentLayer() !== 'S'
    ? `Pozwolenia: ${period.from} – ${period.to}. Pozwolenie nie oznacza wybudowanego domu.` : '';
  ui.renderLegend(layer.title, result.legend[layer.legend], note);
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
    const result = await fetchView({ ...params, bbox: bbox.join(','), zoom }, controller.signal);
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
    map.showPoint(lat, lng, data.radius_km, ui.pointPopup(data));
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
  history.replaceState(null, '', '#' + hash);
}

// Odtwarza ustawienia i widok z adresu; zwraca true, jeśli adres zawierał zapisany widok.
// Stare parametry z v1 (r, pl) są ignorowane.
function applyHash() {
  const h = new URLSearchParams(location.hash.slice(1));
  if (!h.has('type') && !h.has('demand')) return false;
  ui.setSelection({ type: h.get('type'), demand: h.get('demand'), bandwidth: h.get('bw'), months: h.get('m') });
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
ui.initSearch((place) => map.safeFlyTo(place.lat, place.lng, 14));

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

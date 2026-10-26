// Punkt startowy frontendu: spina mapę, panel boczny i API.
import { analyze, getCatalog, getMeta, getPoi } from './api.js';
import { initMap } from './map.js';
import * as ui from './ui.js';

const $ = (id) => document.getElementById(id);
const view = initMap('map');
const state = { lat: null, lng: null, result: null };

// Warstwy mapy: indeks kolumny w wierszu heksagonu, klucz granic w stats i nagłówek legendy.
const LAYERS = {
  score: { index: 1, breaks: 'score_breaks', title: 'Klienci na 1 konkurenta' },
  D: { index: 2, breaks: 'D_breaks', title: 'Popyt w zasięgu' },
  S: { index: 3, breaks: 'S_breaks', title: 'Konkurencja w zasięgu' },
};

const radiusKm = () => Number($('radius-input').value);
const isPoland = () => $('poland-checkbox').checked;
const currentLayer = () => document.querySelector('input[name=layer]:checked').value;
const isMobile = () => window.matchMedia('(max-width: 767px)').matches;

// Pinezka i okrąg obszaru; w trybie „cała Polska” ich nie ma.
function redrawArea() {
  if (isPoland() || state.lat == null) {
    view.clearPin();
    view.setAreaCircle(0, 0, null);
    return;
  }
  view.setPin(state.lat, state.lng);
  view.setAreaCircle(state.lat, state.lng, radiusKm());
}

function setPoint(lat, lng) {
  state.lat = lat;
  state.lng = lng;
  redrawArea();
}

// Rysuje wybraną warstwę z ostatniego wyniku — bez ponownego zapytania do serwera.
function drawLayer() {
  if (!state.result) return;
  const layer = LAYERS[currentLayer()];
  const breaks = state.result.stats[layer.breaks];
  view.setHexes(state.result.hexes, layer.index, breaks);
  // Dla czynników z pozwoleń podajemy okres danych i zastrzeżenie (pozwolenie ≠ wybudowany dom).
  const period = state.result.permits_period;
  const note = period && currentLayer() !== 'S'
    ? `Pozwolenia: ${period.from} – ${period.to}. Pozwolenie nie oznacza wybudowanego domu.` : '';
  ui.renderLegend(layer.title, breaks, note);
}

function popupHtml(row) {
  const [, score, D, S, , , pct] = row;
  return `<div class="title">Szczegóły okolicy</div>` +
    `Popyt w zasięgu: <b>${ui.fmt(D)}</b><br>` +
    `Konkurenci w zasięgu: <b>${ui.fmt(S, 1)}</b><br>` +
    `Na 1 konkurenta: <b>${ui.fmt(score)}</b><br>` +
    `Percentyl: <b>${pct}</b>`;
}

// ---- Stan widoku w adresie URL (#type=beauty&demand=pop_f&lat=…) — link można komuś wysłać ----

function writeHash() {
  const params = ui.selectedParams();
  const hash = new URLSearchParams({
    type: params.type, demand: params.demand, bw: params.bandwidth_km, m: params.months || '',
    pl: isPoland() ? 1 : 0, layer: currentLayer(),
  });
  if (!isPoland()) {
    hash.set('lat', state.lat.toFixed(5));
    hash.set('lng', state.lng.toFixed(5));
    hash.set('r', params.radius_km);
  }
  history.replaceState(null, '', '#' + hash);
}

// Odtwarza ustawienia z adresu i zwraca true, jeśli wystarcza do automatycznej analizy.
function applyHash() {
  const h = new URLSearchParams(location.hash.slice(1));
  if (!h.get('type')) return false;
  ui.setSelection({ type: h.get('type'), demand: h.get('demand'), bandwidth: h.get('bw'), months: h.get('m') });
  if (h.get('r')) { $('radius-input').value = h.get('r'); $('radius-value').textContent = h.get('r'); }
  const layer = document.querySelector(`input[name=layer][value="${h.get('layer')}"]`);
  if (layer) layer.checked = true;
  $('poland-checkbox').checked = h.get('pl') === '1';
  syncPolandMode();
  if (h.get('lat') && h.get('lng')) setPoint(Number(h.get('lat')), Number(h.get('lng')));
  return isPoland() || state.lat != null;
}

// Tryb „cała Polska” wyłącza promień i pinezkę.
function syncPolandMode() {
  $('radius-input').disabled = isPoland();
  redrawArea();
}

async function runAnalysis() {
  ui.showError('');
  if (!isPoland() && state.lat == null) {
    ui.showError('Wybierz punkt na mapie albo wyszukaj adres');
    return;
  }
  ui.setLoading(true);
  try {
    const params = ui.selectedParams();
    if (!isPoland()) { params.lat = state.lat; params.lng = state.lng; }
    const result = await analyze(params);
    state.result = result;
    if (isPoland()) view.fitPoland(); else view.fitArea();
    drawLayer();
    ui.renderWarnings(result.warnings);
    ui.renderTop(result.top, (place) => {
      view.flyTo(place.lat, place.lng, 14);
      view.highlightHex(place.h3);
      if (isMobile()) $('sidebar').classList.add('collapsed');   // na telefonie odsłoń mapę
    });
    if (!result.hexes.length) ui.hideLegend();
    writeHash();
    if (isMobile()) $('sidebar').classList.add('collapsed');
  } catch (e) {
    ui.showError(e.message);
  } finally {
    ui.setLoading(false);
  }
}

// ---- Punkty firm: pobieramy tylko dla widocznego fragmentu mapy i tylko przy dużym przybliżeniu ----
const POI_MIN_ZOOM = 11;
let poiTimer = null;
let poiRequest = 0;

function refreshPoi() {
  clearTimeout(poiTimer);
  poiTimer = setTimeout(loadPoi, 300);   // debounce: czekamy, aż użytkownik przestanie przesuwać mapę
}

async function loadPoi() {
  const note = $('poi-note');
  const request = ++poiRequest;          // odpowiedzi spóźnione względem nowszego zapytania ignorujemy
  if (!$('poi-checkbox').checked) { view.setPoi([]); note.hidden = true; return; }
  if (view.getZoom() < POI_MIN_ZOOM) {
    view.setPoi([]);
    note.textContent = 'Przybliż mapę, aby zobaczyć firmy';
    note.hidden = false;
    return;
  }
  try {
    const data = await getPoi($('type-select').value, view.getBbox());
    if (request !== poiRequest) return;
    view.setPoi(data.items);
    note.textContent = data.truncated ? 'Pokazano 5000 pierwszych firm' : '';
    note.hidden = !data.truncated;
  } catch (e) {
    if (request === poiRequest) { note.textContent = e.message; note.hidden = false; }
  }
}

// ---- Podłączenie zdarzeń ----
view.onClick((lat, lng) => { if (!isPoland()) setPoint(lat, lng); });
view.onHexClick((row, latlng) => view.showPopup(latlng, popupHtml(row)));
view.onMoveEnd(refreshPoi);

$('radius-input').addEventListener('input', () => {
  $('radius-value').textContent = radiusKm();
  redrawArea();
});
$('poland-checkbox').addEventListener('change', syncPolandMode);
$('poi-checkbox').addEventListener('change', loadPoi);
$('type-select').addEventListener('change', loadPoi);
$('analyze-btn').addEventListener('click', runAnalysis);
document.querySelectorAll('input[name=layer]').forEach((el) => el.addEventListener('change', () => {
  drawLayer();
  if (state.result) writeHash();
}));
$('opacity-input').addEventListener('input', () => view.setHexOpacity(Number($('opacity-input').value)));

// Mobile: uchwyt zwija i rozwija arkusz.
$('sheet-handle').addEventListener('click', () => $('sidebar').classList.toggle('collapsed'));

ui.initSearch((place) => {
  setPoint(place.lat, place.lng);
  view.flyTo(place.lat, place.lng, 12);
});

getMeta().then(ui.renderFooter).catch(() => { /* stopka jest dodatkiem — brak metadanych nie przeszkadza */ });
getCatalog()
  .then((catalog) => {
    ui.renderCatalog(catalog);
    if (applyHash()) runAnalysis();   // link z zapisanym widokiem otwiera się od razu z wynikiem
  })
  .catch((e) => ui.showError(e.message));

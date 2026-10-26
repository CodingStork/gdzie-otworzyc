// Punkt startowy frontendu: spina mapę, panel boczny i API.
import { analyze, getCatalog } from './api.js';
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
const currentLayer = () => document.querySelector('input[name=layer]:checked').value;

function redrawArea() {
  if (state.lat == null) return;
  view.setPin(state.lat, state.lng);
  view.setAreaCircle(state.lat, state.lng, radiusKm());
}

// Rysuje wybraną warstwę z ostatniego wyniku — bez ponownego zapytania do serwera.
function drawLayer() {
  if (!state.result) return;
  const layer = LAYERS[currentLayer()];
  const breaks = state.result.stats[layer.breaks];
  view.setHexes(state.result.hexes, layer.index, breaks);
  ui.renderLegend(layer.title, breaks);
}

function popupHtml(row) {
  const [, score, D, S, , , pct] = row;
  return `<div class="title">Szczegóły okolicy</div>` +
    `Popyt w zasięgu: <b>${ui.fmt(D)}</b><br>` +
    `Konkurenci w zasięgu: <b>${ui.fmt(S, 1)}</b><br>` +
    `Na 1 konkurenta: <b>${ui.fmt(score)}</b><br>` +
    `Percentyl: <b>${pct}</b>`;
}

async function runAnalysis() {
  ui.showError('');
  if (state.lat == null) {
    ui.showError('Wybierz punkt na mapie albo wyszukaj adres');
    return;
  }
  ui.setLoading(true);
  try {
    const result = await analyze({ ...ui.selectedParams(), lat: state.lat, lng: state.lng });
    state.result = result;
    view.fitArea();
    drawLayer();
    ui.renderWarnings(result.warnings);
    ui.renderTop(result.top, (place) => {
      view.flyTo(place.lat, place.lng, 14);
      view.highlightHex(place.h3);
    });
    if (!result.hexes.length) ui.hideLegend();
  } catch (e) {
    ui.showError(e.message);
  } finally {
    ui.setLoading(false);
  }
}

view.onClick((lat, lng) => { state.lat = lat; state.lng = lng; redrawArea(); });
view.onHexClick((row, latlng) => view.showPopup(latlng, popupHtml(row)));

$('radius-input').addEventListener('input', () => {
  $('radius-value').textContent = radiusKm();
  redrawArea();
});
$('analyze-btn').addEventListener('click', runAnalysis);
document.querySelectorAll('input[name=layer]').forEach((el) => el.addEventListener('change', drawLayer));
$('opacity-input').addEventListener('input', () => view.setHexOpacity(Number($('opacity-input').value)));

// Mobile: uchwyt zwija i rozwija arkusz.
$('sheet-handle').addEventListener('click', () => $('sidebar').classList.toggle('collapsed'));

getCatalog().then(ui.renderCatalog).catch((e) => ui.showError(e.message));

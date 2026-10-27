// Punkt startowy frontendu: spina mapę, panel boczny i API.
// Przepływ (Shneiderman 1996: przegląd → zawężenie → szczegóły na żądanie):
//   1. użytkownik wybiera branżę/klientów, miejsce i promień → „Pokaż mapę” (zawężenie),
//   2. mapa okolicy jako mgła (przegląd),
//   3. kliknięcie w mapę pokazuje szczegóły punktu (okrąg zasięgu, drobne heksagony, liczby).
// Ruch mapy NICZEGO nie przelicza — zapytania idą tylko po „Pokaż mapę” i po zmianie ustawień.
import { getCatalog, getMeta, getPoi, point, surface } from './api.js';
import { logPosition, logScale } from './colors.js';
import { initMap } from './map.js';
import * as ui from './ui.js';

const $ = (id) => document.getElementById(id);
const map = initMap('map');

// place: wybrane miejsce {lat, lng, name}; result: ostatnia odpowiedź /api/surface; used: ustawienia, dla których ją policzono.
const state = { place: null, result: null, used: null, controller: null, requestId: 0 };

const isMobile = () => window.matchMedia('(max-width: 767px)').matches;
const NEED_SELECTION = 'Wybierz branżę lub klientów.';
const NEED_PLACE = 'Wybierz miejsce: wpisz miejscowość albo kliknij mapę.';

// Na telefonie zwijamy panel, żeby odsłonić mapę; po zmianie rozmiaru Leaflet musi przeliczyć widok.
function collapseSheetOnMobile() {
  if (!isMobile()) return;
  $('sidebar').classList.add('collapsed');
  map.invalidateSize();
}

// Odległość po kuli w km (haversine).
function distanceKm(lat1, lng1, lat2, lng2) {
  const rad = Math.PI / 180;
  const a = Math.sin((lat2 - lat1) * rad / 2) ** 2 +
    Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin((lng2 - lng1) * rad / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.sqrt(a));
}

// ---- Wybór miejsca ----

// Ustawia miejsce: pinezka + okrąg podglądu (po wyniku także przygaszenie poza okręgiem).
function setPlace(lat, lng, name, { fit = false } = {}) {
  state.place = { lat, lng, name };
  ui.setPlaceName(name);
  map.setArea(lat, lng, ui.radiusKm(), { veil: !!state.result, fit });
}

function pickPlace(place) {
  setPlace(place.lat, place.lng, place.name.split(',')[0], { fit: true });
  discardPoint();
  if (state.result) scheduleRun(true);
  writeHash();
}

// ---- Rysowanie wyniku ----

const hasPermits = () => !!(state.result && state.result.permits_period);

// Rysuje wybraną warstwę z ostatniego wyniku — bez ponownego zapytania do serwera.
function drawLayer() {
  const result = state.result;
  const layer = ui.currentLayer();
  const values = result.values[layer];
  const scale = logScale(values);
  if (!scale) {
    map.clearFog();
    ui.hideLegend();
  } else {
    const t = new Float32Array(values.length);
    values.forEach((v, i) => { t[i] = v === null ? NaN : logPosition(v, scale); });
    map.setFog(result.grid, t, state.used.radius_km);
    // Dla czynników z pozwoleń podajemy okres danych i zastrzeżenie (pozwolenie ≠ wybudowany dom).
    const period = result.permits_period;
    const note = period && layer !== 'competition'
      ? `Pozwolenia: ${period.from} – ${period.to}. Pozwolenie nie oznacza wybudowanego domu.` : '';
    ui.renderLegend(ui.legendTitle(layer), scale, note);
  }
  const top = result.top[layer] || [];
  ui.renderTop(top, layer, hasPermits(), (place) => openPlace(place));
  map.setTopMarkers(top, (place) => openPlace(place));
}

function showResult(result, used) {
  state.result = result;
  state.used = used;
  ui.hideIntro();
  ui.showControls(true);
  ui.setLayers(result.layers);
  // Warstwa zapisana w linku (tylko przy pierwszym wyniku po wczytaniu linku).
  if (state.pendingLayer && result.layers.includes(state.pendingLayer)) ui.selectLayer(state.pendingLayer);
  state.pendingLayer = null;
  map.setArea(used.lat, used.lng, used.radius_km, { veil: true });
  drawLayer();
  ui.renderWarnings(result.warnings);
  ui.renderNotes(result.notes);
}

// ---- Zapytanie o mapę ----

let runTimer = null;
function scheduleRun(fit) {
  clearTimeout(runTimer);
  runTimer = setTimeout(() => run({ fit }), 300);   // debounce: czekamy, aż użytkownik skończy zmieniać ustawienia
}

// Sprawdza, czy można liczyć; w przeciwnym razie pokazuje komunikat w panelu.
function validate() {
  const p = ui.selectedParams();
  if (!p.type && !p.demand) { ui.showInfo(NEED_SELECTION); return null; }
  if (!state.place) { ui.showInfo(NEED_PLACE); return null; }
  return p;
}

async function run({ fit }) {
  const p = validate();
  if (!p) return;
  ui.showInfo('');
  ui.showError('');
  if (state.controller) state.controller.abort();   // poprzednie zapytanie jest już nieaktualne
  const controller = new AbortController();
  state.controller = controller;
  const mine = ++state.requestId;
  const used = { ...p, lat: state.place.lat, lng: state.place.lng };
  ui.setLoading(true);
  try {
    const result = await surface({
      type: p.type, demand: p.demand, lat: used.lat, lng: used.lng,
      radius_km: p.radius_km, reach_km: p.reach_km, months: p.months,
    }, controller.signal);
    if (mine !== state.requestId) return;
    discardPoint();
    showResult(result, used);
    if (fit) map.setArea(used.lat, used.lng, used.radius_km, { veil: true, fit: true });
    writeHash();
    collapseSheetOnMobile();
  } catch (e) {
    if (e.name === 'AbortError') return;   // zastąpione nowszym zapytaniem
    if (mine !== state.requestId) return;
    ui.showError(e.message);
  } finally {
    if (mine === state.requestId) ui.setLoading(false);
  }
}

// ---- Szczegóły klikniętego punktu ----

let pointRequest = 0;

// Szczegóły opisują ustawienia z chwili kliknięcia: po zmianie formularza lub linku zamykamy je i ignorujemy spóźnioną odpowiedź.
function discardPoint() {
  pointRequest++;
  map.closeDetails();
}

async function showPointAt(lat, lng) {
  const u = state.used;
  const mine = ++pointRequest;
  try {
    // Konkurenci do narysowania: firmy z OSM w prostokącie okręgu zasięgu, przycięte do okręgu.
    // Zasięg efektywny (dla pozwoleń min. 1 km) znamy dopiero z odpowiedzi, więc prostokąt liczymy z zapasem.
    const reach = Math.max(u.reach_km, 1);
    const dlat = reach / 110.54;
    const dlng = reach / (111.32 * Math.cos(lat * Math.PI / 180));
    const [data, poi] = await Promise.all([
      point({ lat, lng, type: u.type, demand: u.demand, reach_km: u.reach_km, months: u.months }),
      u.type ? getPoi(u.type, [lng - dlng, lat - dlat, lng + dlng, lat + dlat]).catch(() => null) : null,
    ]);   // brak konkurentów na mapie (poi == null) nie blokuje dymku
    if (mine !== pointRequest) return;
    const competitors = poi ? poi.items.filter((c) => distanceKm(lat, lng, c.lat, c.lng) <= data.radius_km) : [];
    map.showDetails(lat, lng, data.radius_km, data.cells, competitors,
      ui.pointPopup(data, () => useAsCenter(lat, lng)));
  } catch (e) {
    if (mine === pointRequest) ui.showError(e.message);
  }
}

// Wskazane miejsce (z listy top-5 albo ze znacznika): przybliżamy mapę i pokazujemy szczegóły.
function openPlace(place) {
  map.safeFlyTo(place.lat, place.lng, Math.max(map.getView().zoom, 13));
  collapseSheetOnMobile();
  showPointAt(place.lat, place.lng);
}

// „Ustaw tu środek obszaru” w dymku: ten punkt staje się środkiem i mapa jest liczona od nowa.
function useAsCenter(lat, lng) {
  discardPoint();
  setPlace(lat, lng, 'wybrany punkt');
  run({ fit: true });
}

// Kliknięcie w mapę: bez wyniku ustawia miejsce, z wynikiem pokazuje szczegóły.
function onMapClick(lat, lng) {
  if (!state.result) {
    setPlace(lat, lng, 'punkt na mapie');
    ui.showInfo('');
    writeHash();
    return;
  }
  showPointAt(lat, lng);
}

// ---- Stan w adresie URL (#type=…&demand=…&reach=…&m=…&layer=…&lat=…&lng=…&r=…) — link można komuś wysłać ----

function writeHash() {
  if (!state.place) return;
  const p = ui.selectedParams();
  const hash = new URLSearchParams({
    type: p.type, demand: p.demand, reach: p.reach_km, layer: ui.currentLayer(),
    lat: state.place.lat.toFixed(5), lng: state.place.lng.toFixed(5), r: p.radius_km, n: state.place.name,
  });
  if (p.months) hash.set('m', p.months);   // okres tylko dla czynników z pozwoleń
  history.replaceState(null, '', '#' + hash);
}

// Odtwarza ustawienia z adresu; zwraca true, jeśli adres zawierał miejsce i wybór (wtedy od razu liczymy mapę).
function applyHash() {
  const h = new URLSearchParams(location.hash.slice(1));
  const lat = Number(h.get('lat'));
  const lng = Number(h.get('lng'));
  if (!h.get('lat') || !h.get('lng') || !Number.isFinite(lat) || !Number.isFinite(lng)) return false;
  if (!h.get('type') && !h.get('demand')) return false;
  ui.setSelection({
    type: h.get('type'), demand: h.get('demand'), reach: Number(h.get('reach')) || null,
    months: h.get('m'), radius: Number(h.get('r')) || null,
  });
  setPlace(lat, lng, h.get('n') || 'wybrane miejsce', { fit: true });
  state.pendingLayer = h.get('layer');
  return true;
}

// ---- Podłączenie zdarzeń ----
map.onMapClick(onMapClick);

// Zmiana ustawień: po wyniku liczymy od nowa (z opóźnieniem), przed wynikiem tylko odświeżamy okrąg podglądu.
function onFormChange() {
  discardPoint();
  ui.showInfo('');
  if (state.result) scheduleRun(false);
  else if (state.place) map.setArea(state.place.lat, state.place.lng, ui.radiusKm(), { veil: false });
  writeHash();
}

ui.onShowClick(() => { clearTimeout(runTimer); run({ fit: true }); });
document.querySelectorAll('input[name=layer]').forEach((el) => el.addEventListener('change', () => {
  discardPoint();
  drawLayer();
  writeHash();
}));
$('opacity-input').addEventListener('input', () => map.setFogOpacity(Number($('opacity-input').value)));

// Mobile: uchwyt zwija i rozwija arkusz.
$('sheet-handle').addEventListener('click', () => $('sidebar').classList.toggle('collapsed'));

ui.renderHelp();
ui.initSearch(pickPlace);

// Wklejenie innego linku w tej samej karcie zmienia tylko hash (bez przeładowania) — odtwórz widok.
window.addEventListener('hashchange', () => { if (applyHash()) run({ fit: true }); });

getMeta().then(ui.renderFooter).catch(() => { /* stopka jest dodatkiem — brak metadanych nie przeszkadza */ });
getCatalog()
  .then((catalog) => {
    ui.renderCatalog(catalog, onFormChange);
    if (applyHash()) run({ fit: true });
  })
  .catch((e) => ui.showError(e.message));

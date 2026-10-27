// Punkt startowy frontendu: spina mapę, panele (lewy = ustawienia, prawy = wnioski) i API.
// Przepływ (Shneiderman 1996: przegląd → zawężenie → szczegóły na żądanie):
//   1. użytkownik wybiera branżę/klientów, miejsce i promień → „Pokaż mapę” (zawężenie),
//   2. mapa okolicy jako mgła + podsumowanie obszaru po prawej (przegląd),
//   3. kliknięcie W okręgu pokazuje szczegóły punktu (okrąg zasięgu, konkurenci, liczby),
//      kliknięcie POZA okręgiem wybiera nowe miejsce.
// Ruch mapy NICZEGO nie przelicza — zapytania idą tylko po „Pokaż mapę” i po zmianie ustawień.
import { getCatalog, getMeta, getPoi, point, surface } from './api.js';
import { logPosition, logScale, trendColor, trendPosition, trendScale } from './colors.js';
import { initMap } from './map.js';
import * as ui from './ui.js';

const $ = (id) => document.getElementById(id);
const map = initMap('map');

// place: wybrane miejsce {lat, lng, name}; result: ostatnia odpowiedź /api/surface; used: ustawienia, dla których ją policzono;
// preview: wskazano nowe miejsce, a mapa pokazuje jeszcze stary obszar; pendingNote: dodatkowa notatka (np. po podniesieniu zasięgu).
const state = { loading: false, place: null, result: null, used: null, controller: null, requestId: 0, preview: false, pendingNote: null };

const isMobile = () => window.matchMedia('(max-width: 767px)').matches;
const NEED_SELECTION = 'Wybierz branżę lub klientów.';
const NEED_PLACE = 'Wybierz miejsce: wpisz miejscowość albo kliknij mapę.';
const NEW_PLACE_INFO = 'Wybrano nowe miejsce — kliknij »Pokaż mapę«.';
const MAP_POINT = 'punkt na mapie';   // nazwa miejsca wskazanego kliknięciem (nigdy „wybrane miejsce”)

// Odległość po kuli w km (haversine).
function distanceKm(lat1, lng1, lat2, lng2) {
  const rad = Math.PI / 180;
  const a = Math.sin((lat2 - lat1) * rad / 2) ** 2 +
    Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin((lng2 - lng1) * rad / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.sqrt(a));
}

// ---- Wybór miejsca ----

// Ustawia miejsce: pinezka + okrąg. `preview` = nowe miejsce przy widocznym starym wyniku: przerywany okrąg podglądu,
// bez przygaszenia poza okręgiem, a mgła starego obszaru przygasa do 30% i przycisk „Pokaż mapę” się wyróżnia.
function setPlace(lat, lng, name, { fit = false, preview = false } = {}) {
  state.place = { lat, lng, name };
  state.preview = preview;
  ui.setPlaceName(name);
  map.setArea(lat, lng, ui.radiusKm(), { veil: !!state.result && !preview, fit });
  map.dimFog(preview);
  ui.highlightShow(preview);
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
  const { result, used } = state;
  const layer = ui.currentLayer();
  const values = result.values[layer];
  if (!values) return;                                   // warstwa z nowszych ustawień — poczekajmy na nowy wynik
  const title = ui.legendTitle(layer, used.type, used.demand);
  const period = result.permits_period;
  if (layer === 'trend') {
    // Trend ma znak (spadek / wzrost): paleta rozbieżna, środek (bez zmian) przezroczysty.
    const scale = trendScale(values);
    if (!scale) {
      map.clearFog();
      ui.hideLegend();
    } else {
      const t = new Float32Array(values.length);
      values.forEach((v, i) => { t[i] = v === null ? NaN : trendPosition(v, scale); });
      map.setFog(result.grid, t, used.radius_km, trendColor);
      ui.renderTrendLegend(title, 'mniej budów ← → więcej budów (ostatnie 12 mies. vs poprzednie 12)');
    }
  } else {
    const scale = logScale(values);
    if (!scale) {
      map.clearFog();
      ui.hideLegend();
    } else {
      const t = new Float32Array(values.length);
      values.forEach((v, i) => { t[i] = v === null ? NaN : logPosition(v, scale); });
      map.setFog(result.grid, t, used.radius_km);
      // Dla czynników z pozwoleń podajemy okres danych i zastrzeżenie (pozwolenie ≠ wybudowany dom).
      const note = period && layer !== 'competition'
        ? `Pozwolenia: ${period.from} – ${period.to}. Pozwolenie nie oznacza wybudowanego domu.` : '';
      ui.renderLegend(title, scale, note);
    }
  }
  map.dimFog(state.preview);
  const top = result.top[layer] || [];
  ui.renderTop(top, layer, hasPermits(), (place) => openPlace(place));
  map.setTopMarkers(top, (place) => openPlace(place));
}

function showResult(result, used) {
  state.result = result;
  state.used = used;
  state.preview = false;
  ui.highlightShow(false);
  ui.hideIntro();
  ui.showInsights();                                     // panel po prawej zmienia szerokość mapy
  map.invalidateSize();
  map.setArea(used.lat, used.lng, used.radius_km, { veil: true });
  drawLayer();
  ui.renderSummary(result.summary, { placeName: used.name, demandId: used.demand, permitsPeriod: result.permits_period });
  ui.renderWarnings(result.warnings);
  ui.renderNotes([...(state.pendingNote ? [state.pendingNote] : []), ...result.notes]);
  state.pendingNote = null;
  if (isMobile()) ui.setTab('insights');                 // na telefonie po „Pokaż mapę” od razu wnioski
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
  const used = { ...p, lat: state.place.lat, lng: state.place.lng, name: state.place.name };
  ui.setLoading(true);
  state.loading = true;
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
  } catch (e) {
    if (e.name === 'AbortError') return;   // zastąpione nowszym zapytaniem
    if (mine !== state.requestId) return;
    ui.showError(e.message);
  } finally {
    if (mine === state.requestId) { ui.setLoading(false); state.loading = false; }
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
    // Konkurenci do narysowania: firmy (OSM i Overture) w prostokącie okręgu zasięgu, przycięte do okręgu.
    // Zasięg efektywny (min. 0,3 km, dla pozwoleń 1 km) znamy dopiero z odpowiedzi, więc prostokąt liczymy z zapasem.
    const reach = Math.max(u.reach_km, 1);
    const dlat = reach / 110.54;
    const dlng = reach / (111.32 * Math.cos(lat * Math.PI / 180));
    const [data, poi] = await Promise.all([
      point({ lat, lng, type: u.type, demand: u.demand, reach_km: u.reach_km, months: u.months }),
      u.type ? getPoi(u.type, [lng - dlng, lat - dlat, lng + dlng, lat + dlat]).catch(() => null) : null,
    ]);   // brak konkurentów na mapie (poi == null) nie blokuje dymku
    if (mine !== pointRequest) return;
    const competitors = poi ? poi.items.filter((c) => distanceKm(lat, lng, c.lat, c.lng) <= data.radius_km) : [];
    map.showDetails(lat, lng, data.radius_km, competitors, ui.pointPopup(data, () => useAsCenter(lat, lng)));
  } catch (e) {
    if (mine === pointRequest) ui.showError(e.message);
  }
}

// Wskazane miejsce (z listy top-5 albo ze znacznika): przybliżamy mapę i pokazujemy szczegóły.
function openPlace(place) {
  if (isMobile()) ui.collapseSheet();                    // arkusz zasłaniałby mapę i dymek
  map.safeFlyTo(place.lat, place.lng, Math.max(map.getView().zoom, 13));
  showPointAt(place.lat, place.lng);
}

// „Ustaw tu środek obszaru” w dymku: ten punkt staje się środkiem i mapa jest liczona od nowa.
function useAsCenter(lat, lng) {
  discardPoint();
  setPlace(lat, lng, MAP_POINT);
  run({ fit: true });
}

// Kliknięcie w mapę:
//   • bez wyniku (albo gdy właśnie wskazano nowe miejsce) — ustawia miejsce,
//   • w okręgu obszaru — szczegóły punktu,
//   • poza okręgiem — nowe miejsce (podgląd; trzeba kliknąć »Pokaż mapę«).
function onMapClick(lat, lng) {
  if (!state.result) {
    setPlace(lat, lng, MAP_POINT);
    ui.showInfo('');
    writeHash();
    return;
  }
  const u = state.used;
  if (!state.preview && distanceKm(lat, lng, u.lat, u.lng) <= u.radius_km) {
    showPointAt(lat, lng);
    return;
  }
  discardPoint();
  setPlace(lat, lng, MAP_POINT, { preview: true });
  ui.showInfo(NEW_PLACE_INFO);
  if (isMobile()) ui.setTab('settings');                 // tam jest przycisk „Pokaż mapę”
  writeHash();
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
  const clamped = ui.setSelection({
    type: h.get('type'), demand: h.get('demand'), reach: Number(h.get('reach')) || null,
    months: h.get('m'), radius: Number(h.get('r')) || null,
  });
  state.pendingNote = clamped ? ui.MIN_REACH_NOTE : null;   // stary link z zasięgiem < 0,3 km
  if (h.get('layer')) ui.selectLayer(h.get('layer'));
  setPlace(lat, lng, h.get('n') || MAP_POINT, { fit: true });
  return true;
}

// ---- Podłączenie zdarzeń ----
map.onMapClick(onMapClick);

// Zmiana ustawień: po wyniku liczymy od nowa (z opóźnieniem), przed wynikiem tylko odświeżamy okrąg podglądu.
function onFormChange() {
  discardPoint();
  ui.showInfo(state.preview ? NEW_PLACE_INFO : '');
  if (state.result || state.loading) scheduleRun(state.preview);   // także w trakcie pierwszego zapytania; przy podglądzie nowego miejsca dopasuj widok
  else if (state.place) map.setArea(state.place.lat, state.place.lng, ui.radiusKm(), { veil: false });
  writeHash();
}

ui.onShowClick(() => { clearTimeout(runTimer); run({ fit: true }); });
ui.onLayerChange(() => {
  discardPoint();
  if (state.result) drawLayer();
  writeHash();
});
$('opacity-input').addEventListener('input', () => map.setFogOpacity(Number($('opacity-input').value)));

ui.initTabs(() => map.invalidateSize());
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

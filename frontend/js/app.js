// Punkt startowy frontendu: spina mapę, panele (lewy = ustawienia, prawy = wnioski) i API.
// Dwa tryby (przełącznik „Obszar analizy”, Shneiderman 1996: przegląd → zawężenie → szczegóły na żądanie):
//   • Cała Polska (domyślny): mgła jest od razu. Po oddaleniu (widok szerszy niż ~40 km) pokazujemy GOTOWĄ mapę Polski z ETL
//     (/api/national, stała skala kolorów); po przybliżeniu do miasta mgła liczy się NA ŻYWO z ustawieniami użytkownika
//     (/api/surface w trybie prostokąta widoku). Zapytania idą dopiero po zakończeniu ruchu mapy (debounce) — w v2 ciągłe
//     przeliczanie przy ruchu męczyło, dlatego oddalony widok jest natychmiastowy, a na żywo liczymy tylko po przybliżeniu.
//   • Wybrane miejsce: jak w v3.1 — miejsce + promień → „Pokaż mapę”, podsumowanie obszaru, ruch mapy niczego nie przelicza.
// Kliknięcie w mapę tworzy WYBÓR: pinezka, okrąg podglądu i karta z liczbami punktu, suwakiem promienia i przyciskiem ✓ (analiza obszaru).
// Wyjątek: kliknięcie wewnątrz bieżącej analizy pokazuje szczegóły punktu (dymek z konkurentami).
import { getCatalog, getMeta, getPoi, national, point, surface } from './api.js';
import { logPosition, logScale, trendColor, trendPosition, trendScale } from './colors.js';
import { initMap } from './map.js';
import * as ui from './ui.js';

const $ = (id) => document.getElementById(id);
const map = initMap('map');

// mode: 'pl' | 'place'. result: ostatnia odpowiedź (/api/national, /api/surface); used: ustawienia, dla których ją policzono.
// Tryb miejsca: place = wybrane miejsce {lat, lng, name}; pendingNote = dodatkowa notatka (np. po podniesieniu zasięgu).
// Tryb Polski: view = 'national' | 'live' (co teraz widać).
// selection = wybór w toku (jeszcze nie przeanalizowany): { kind: 'circle', lat, lng, name, radiusKm }, card = jego karta.
const state = {
  mode: 'pl', loading: false, place: null, result: null, used: null, controller: null, requestId: 0,
  pendingNote: null, view: null, selection: null, card: null,
};

const isMobile = () => window.matchMedia('(max-width: 767px)').matches;
const NEED_SELECTION = 'Wybierz branżę lub klientów.';
const NEED_PLACE = 'Wybierz miejsce: wpisz miejscowość albo kliknij mapę.';
const MAP_POINT = 'punkt na mapie';   // nazwa miejsca wskazanego kliknięciem (nigdy „wybrane miejsce”)
const LIVE_HALF_DIAGONAL_KM = 20;     // widok o półprzekątnej ≤ 20 km (ok. 28 × 28 km) liczymy na żywo
const NO_CIRCLE = 1e9;                // „promień” maski mgły bez okręgu: w trybie Polski mgła nie jest przycinana do koła
const NATIONAL_DEBOUNCE_MS = 250;
const LIVE_DEBOUNCE_MS = 400;
const FORM_DEBOUNCE_MS = 300;
const DEFAULT_MONTHS = 24;            // okno pozwoleń gotowej mapy Polski (zgodne z catalog.DEFAULT_MONTHS)

// Odległość po kuli w km (haversine).
function distanceKm(lat1, lng1, lat2, lng2) {
  const rad = Math.PI / 180;
  const a = Math.sin((lat2 - lat1) * rad / 2) ** 2 +
    Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin((lng2 - lng1) * rad / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.sqrt(a));
}

// Półprzekątna widocznego fragmentu mapy w km — decyduje, czy liczyć na żywo.
function halfDiagonalKm(b) {
  const midLat = (b.south + b.north) / 2;
  const width = (b.east - b.west) * 111.32 * Math.cos(midLat * Math.PI / 180);
  const height = (b.north - b.south) * 110.54;
  return Math.hypot(width, height) / 2;
}

const kmText = (km) => String(km).replace('.', ',');

// ---- Wybór miejsca (tryb „Wybrane miejsce”) ----

// Ustawia miejsce analizy: pinezka + okrąg (z przygaszeniem poza okręgiem, gdy jest już wynik).
function setPlace(lat, lng, name, { fit = false } = {}) {
  state.place = { lat, lng, name };
  ui.setPlaceName(name);
  map.setArea(lat, lng, ui.radiusKm(), { veil: !!state.result, fit });
}

// Wybór z wyszukiwarki działa tak samo jak kliknięcie w mapę: pinezka i karta z ✓ (mapa dopasowuje się do okręgu).
function pickPlace(place) {
  beginSelection(place.lat, place.lng, place.name.split(',')[0], { fit: true });
}

// ---- Wybór obszaru kliknięciem: pinezka + okrąg podglądu + karta (suwak promienia, ✓, ✕) ----

let selectionInfoRequest = 0;

function clearSelection() {
  selectionInfoRequest++;                                // spóźniona odpowiedź nie dopisze się do usuniętej karty
  state.selection = null;
  state.card = null;
  map.clearSelection();
}

function beginSelection(lat, lng, name, { fit = false } = {}) {
  discardPoint();
  clearSelection();
  const radiusKm = ui.radiusKm();                        // jedna wartość promienia: suwak w lewym panelu i na karcie
  state.selection = { kind: 'circle', lat, lng, name, radiusKm };
  state.card = ui.selectionCard({
    title: name === MAP_POINT ? 'Wybrany punkt' : name, radiusKm,
    onRadius: (km) => setSelectionRadius(km, true), onConfirm: confirmSelection, onCancel: clearSelection,
  });
  map.showSelection(lat, lng, radiusKm, state.card.el);
  if (fit) map.fitCircle(lat, lng, radiusKm);
  if (isMobile()) ui.collapseSheet();                    // arkusz paneli zasłaniałby kartę
  loadSelectionInfo();
}

// Promień z suwaka (na karcie albo w lewym panelu): okrąg podglądu zmienia się od razu, bez zapytań do serwera.
function setSelectionRadius(km, fromCard) {
  const s = state.selection;
  if (!s || s.kind !== 'circle') return;
  s.radiusKm = km;
  if (fromCard) ui.setRadius(km); else state.card.setRadius(km);
  map.updateSelectionRadius(s.lat, s.lng, km);
}

// Liczby punktu (to samo co dymek w v3.3: klienci w zasięgu, model Huffa, ostrzeżenie o lukach) dopisujemy do karty po odpowiedzi serwera.
async function loadSelectionInfo() {
  const s = state.selection;
  const card = state.card;
  const mine = ++selectionInfoRequest;
  const u = state.result ? state.used : ui.selectedParams();
  if (!u.type && !u.demand) {
    card.setBody('Wybierz branżę lub klientów w panelu po lewej, żeby zobaczyć liczby.');
    map.refreshSelectionCard();
    return;
  }
  try {
    const data = await point({ lat: s.lat, lng: s.lng, type: u.type, demand: u.demand, reach_km: u.reach_km, months: u.months });
    if (mine !== selectionInfoRequest) return;
    card.setBody(ui.pointPopup(data, null));
  } catch (e) {
    if (mine !== selectionInfoRequest) return;
    card.setBody(e.message);
  }
  map.refreshSelectionCard();
}

// ✓ na karcie: przejście do trybu „Wybrane miejsce” i analiza.
function confirmSelection() {
  const s = state.selection;
  if (!s) return;
  const p = ui.selectedParams();
  if (!p.type && !p.demand) { state.card.setBody(NEED_SELECTION); map.refreshSelectionCard(); return; }
  analyzeCircle(s.lat, s.lng, s.name, s.radiusKm);
}

function analyzeCircle(lat, lng, name, radiusKm) {
  clearSelection();
  map.closeDetails();
  ui.setRadius(radiusKm);
  switchMode('place');
  setPlace(lat, lng, name);
  run({ fit: true });
}

// ---- Rysowanie wyniku ----

const hasPermits = () => !!(state.result && state.result.permits_period);

// Rysuje wybraną warstwę z ostatniego wyniku — bez ponownego zapytania do serwera.
// Skala kolorów: gotowa mapa Polski ma STAŁĄ (result.scale, percentyle z całego kraju); okrąg i widok na żywo — lokalną (2 rzędy wielkości).
function drawLayer() {
  const { result, used } = state;
  let layer = ui.currentLayer();
  if (!result.values[layer]) layer = result.layers[0];   // np. „Gdzie otworzyć” bez gotowej warstwy: rysujemy pierwszą dostępną (wybór w panelu zostaje)
  const values = layer && result.values[layer];
  if (!values) {                                         // brak warstwy z nowszych ustawień (poczekajmy na wynik) albo brak gotowej mapy
    map.clearFog();
    ui.hideLegend();
    map.setTopMarkers([], () => {});
    ui.renderTop([], ui.currentLayer(), false, () => {}, state.mode === 'pl');
    return;
  }
  const national = result.mode === 'national';
  const title = ui.legendTitle(layer, used.type, used.demand);
  const period = result.permits_period;
  const radius = state.mode === 'place' ? used.radius_km : NO_CIRCLE;
  if (layer === 'trend') {
    // Trend ma znak (spadek / wzrost): paleta rozbieżna, środek (bez zmian) przezroczysty.
    const scale = national ? result.scale.trend : trendScale(values);
    if (!scale) {
      map.clearFog();
      ui.hideLegend();
    } else {
      const t = new Float32Array(values.length);
      values.forEach((v, i) => { t[i] = v === null ? NaN : trendPosition(v, scale); });
      map.setFog(result.grid, t, radius, trendColor);
      ui.renderTrendLegend(title, 'mniej budów ← → więcej budów (ostatnie 12 mies. vs poprzednie 12)' +
        (national ? ` · stała skala dla całej Polski, zasięg ${kmText(result.layer_reach_km.trend)} km` : ' · kolory dopasowane do widoku'));
    }
  } else {
    const scale = national ? result.scale[layer] : logScale(values);
    if (!scale) {
      map.clearFog();
      ui.hideLegend();
    } else {
      const t = new Float32Array(values.length);
      values.forEach((v, i) => { t[i] = v === null ? NaN : logPosition(v, scale); });
      // Szare kreskowanie „mało danych o firmach” — tylko na warstwie „Gdzie otworzyć”.
      const gapCells = layer === 'open' && result.gap && result.gap.open;
      const gap = gapCells ? Float32Array.from(gapCells, (g) => (g === null ? NaN : g)) : null;
      map.setFog(result.grid, t, radius, undefined, gap);
      // Dla czynników z pozwoleń podajemy okres danych i zastrzeżenie (pozwolenie ≠ wybudowany dom).
      const notes = [];
      if (period && layer !== 'competition') notes.push(`Pozwolenia: ${period.from} – ${period.to}. Pozwolenie nie oznacza wybudowanego domu.`);
      if (national) notes.push('Skala jest stała dla całego kraju: te same kolory znaczą te same liczby (na oddalonych poziomach pokazujemy najlepsze miejsce w rejonie).');
      else if (state.mode === 'pl') notes.push('Kolory dopasowane do widoku.');
      ui.renderLegend(title, scale, notes.join(' '), !!gap && gap.includes(1));
    }
  }
  // Gotowa mapa jest liczona dla kadru zaokrąglonego na zewnątrz, więc w „Najlepszych miejscach w widoku” zostawiamy tylko te na ekranie.
  const top = (result.top[layer] || []).filter((p) => !national || map.contains(p.lat, p.lng));
  // Pusta lista przy kreskowaniu to nie „brak danych”, tylko miejsca bez wiarygodnych klientów — mówimy to wprost.
  const onlyGaps = layer === 'open' && result.gap && result.gap.open.includes(1) && !(result.top[layer] || []).length;   // pusta już z serwera, a nie przez filtr widoku
  ui.renderTop(top, layer, hasPermits(), (place) => openPlace(place), state.mode === 'pl',
    onlyGaps ? 'Brak wiarygodnych miejsc: wyniki tutaj opierają się głównie na lukach w danych o firmach (kreskowanie).' : undefined);
  map.setTopMarkers(top, (place) => openPlace(place));
}

function showResult(result, used) {
  state.result = result;
  state.used = used;
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

// Czyści wynik i wszystko, co z niego narysowano (zmiana trybu, brak wyboru).
function resetResult() {
  state.result = null;
  state.used = null;
  state.view = null;
  discardPoint();
  map.clearFog();
  map.setTopMarkers([], () => {});
  ui.hideLegend();
  ui.hideSummary();
  ui.renderTop([], 'open', false, () => {});
  $('top-title').hidden = true;
  ui.renderWarnings([]);
  ui.renderNotes([]);
}

// ---- Tryb „Wybrane miejsce”: zapytanie o mapę ----

let runTimer = null;
function scheduleRun(fit) {
  clearTimeout(runTimer);
  runTimer = setTimeout(() => run({ fit }), FORM_DEBOUNCE_MS);   // debounce: czekamy, aż użytkownik skończy zmieniać ustawienia
}

// Sprawdza, czy można liczyć; w przeciwnym razie pokazuje komunikat w panelu.
function validate() {
  const p = ui.selectedParams();
  if (!p.type && !p.demand) { ui.showInfo(NEED_SELECTION); return null; }
  if (!state.place) { ui.showInfo(NEED_PLACE); return null; }
  return p;
}

async function run({ fit }) {
  if (state.mode !== 'place') return;
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

// ---- Tryb „Cała Polska”: gotowa mapa (daleko) albo mapa na żywo (blisko) ----

let viewTimer = null;
function scheduleView(delay) {
  clearTimeout(viewTimer);
  viewTimer = setTimeout(refreshView, delay);
}

// Ruch mapy: po jego zakończeniu (moveend) odświeżamy mgłę. Bez wyboru branży/klientów nie ma co liczyć.
async function refreshView() {
  if (state.mode !== 'pl') return;
  const p = ui.selectedParams();
  if (!p.type && !p.demand) {
    if (state.controller) state.controller.abort();
    resetResult();
    ui.showInfo(NEED_SELECTION);
    ui.setLoading(false);
    return;
  }
  ui.showInfo('');
  ui.showError('');
  const bounds = map.viewBounds();
  if (bounds.px < 50 || !(bounds.east > bounds.west) || !(bounds.north > bounds.south)) return;   // mapa jeszcze bez rozmiaru (start strony)
  const live = halfDiagonalKm(bounds) <= LIVE_HALF_DIAGONAL_KM;
  if (state.controller) state.controller.abort();   // wcześniejsze zapytanie (inny kadr) jest nieaktualne
  const controller = new AbortController();
  state.controller = controller;
  const mine = ++state.requestId;
  ui.setLoading(true);
  try {
    const box = { west: bounds.west, south: bounds.south, east: bounds.east, north: bounds.north };
    const result = live
      ? await surface({ type: p.type, demand: p.demand, reach_km: p.reach_km, months: p.months, ...box }, controller.signal)
      : await national({ type: p.type, demand: p.demand, px: bounds.px, ...box }, controller.signal);
    if (mine !== state.requestId || state.mode !== 'pl') return;
    showView(result, { ...p, reach_km: live ? p.reach_km : result.reach_km }, live ? 'live' : 'national');
    writeHash();
  } catch (e) {
    if (e.name === 'AbortError') return;
    if (mine !== state.requestId) return;
    ui.showError(e.message);
  } finally {
    if (mine === state.requestId) ui.setLoading(false);
  }
}

function showView(result, used, kind) {
  const firstResult = !state.result;
  state.result = result;
  state.used = used;
  state.view = kind;
  if (kind === 'national') used.months = DEFAULT_MONTHS;   // gotowa mapa jest policzona dla 24 miesięcy — dymek ma liczyć tak samo
  ui.hideIntro();
  ui.showInsights();
  if (firstResult) map.invalidateSize();                 // prawy panel pojawił się po raz pierwszy
  ui.setReachLocked(kind === 'national');
  drawLayer();
  if (kind === 'live') {
    ui.renderSummary(result.summary, { placeName: 'widoczny obszar', demandId: used.demand, permitsPeriod: result.permits_period });
  } else {
    ui.hideSummary();                                    // podsumowanie ze średnią krajową ma sens tylko dla konkretnego obszaru
  }
  ui.renderWarnings(result.warnings);
  ui.renderNotes(result.notes);
}

// ---- Zmiana trybu ----

function switchMode(mode) {
  if (state.mode === mode) return;
  state.mode = mode;
  clearTimeout(viewTimer);
  clearTimeout(runTimer);
  if (state.controller) state.controller.abort();
  ui.setLoading(false);
  state.loading = false;                                 // przerwane zapytanie nie dojdzie do swojego finally (requestId już inny)
  clearSelection();
  ui.showError('');
  ui.setMode(mode);
  resetResult();
  if (mode === 'pl') {
    map.clearArea();
    ui.showIntro();
    ui.showInfo('');
    refreshView();
  } else {
    ui.showIntro();
    ui.showInfo(state.place ? '' : NEED_PLACE);
    if (state.place) setPlace(state.place.lat, state.place.lng, state.place.name);   // pinezka i okrąg wracają
  }
  writeHash();
}

// „Przeanalizuj to miejsce” w dymku: ten punkt staje się wybranym miejscem i od razu liczymy okrąg wokół niego.
function analyzePlace(lat, lng) {
  analyzeCircle(lat, lng, MAP_POINT, ui.radiusKm());
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
    const popup = state.mode === 'pl'
      ? ui.pointPopup(data, () => analyzePlace(lat, lng), 'Przeanalizuj to miejsce')
      : ui.pointPopup(data, () => useAsCenter(lat, lng));
    map.showDetails(lat, lng, data.radius_km, competitors, popup);
  } catch (e) {
    if (mine === pointRequest) ui.showError(e.message);
  }
}

// Wskazane miejsce (z listy top-5 albo ze znacznika): przybliżamy mapę i pokazujemy szczegóły.
function openPlace(place) {
  clearSelection();
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

// Kliknięcie w mapę: wewnątrz bieżącej analizy (tryb „Wybrane miejsce”) — szczegóły punktu,
// wszędzie indziej (Cała Polska, poza obszarem, brak wyniku) — nowy wybór z kartą i przyciskiem ✓.
function onMapClick(lat, lng) {
  if (state.mode === 'place' && state.result && !state.selection && distanceKm(lat, lng, state.used.lat, state.used.lng) <= state.used.radius_km) {
    showPointAt(lat, lng);
    return;
  }
  beginSelection(lat, lng, MAP_POINT);
}

// ---- Stan w adresie URL — link można komuś wysłać ----
//   Cała Polska:      #mode=pl&type=…&demand=…&reach=…&m=…&layer=…&z=…&clat=…&clng=…
//   Wybrane miejsce:  #mode=place&type=…&demand=…&reach=…&m=…&layer=…&lat=…&lng=…&r=…&n=…
// Stare linki (bez mode, z lat/lng) to tryb „Wybrane miejsce”.

function writeHash() {
  const p = ui.selectedParams();
  let hash;
  if (state.mode === 'pl') {
    const c = map.leaflet.getCenter();
    hash = new URLSearchParams({
      mode: 'pl', type: p.type, demand: p.demand, reach: p.reach_km, layer: ui.currentLayer(),
      z: map.leaflet.getZoom().toFixed(2), clat: c.lat.toFixed(5), clng: c.lng.toFixed(5),
    });
  } else {
    if (!state.place) return;
    hash = new URLSearchParams({
      mode: 'place', type: p.type, demand: p.demand, reach: p.reach_km, layer: ui.currentLayer(),
      lat: state.place.lat.toFixed(5), lng: state.place.lng.toFixed(5), r: p.radius_km, n: state.place.name,
    });
  }
  if (p.months) hash.set('m', p.months);   // okres tylko dla czynników z pozwoleń
  history.replaceState(null, '', '#' + hash);
}

// Odtwarza ustawienia z adresu; zwraca true, gdy adres zawierał widok albo miejsce (wtedy od razu pokazujemy mapę).
function applyHash() {
  const h = new URLSearchParams(location.hash.slice(1));
  const lat = Number(h.get('lat'));
  const lng = Number(h.get('lng'));
  const hasPlace = h.get('lat') && h.get('lng') && Number.isFinite(lat) && Number.isFinite(lng);
  const mode = h.get('mode') === 'pl' || (!h.get('mode') && !hasPlace) ? 'pl' : 'place';
  const selection = {
    type: h.get('type'), demand: h.get('demand'), reach: Number(h.get('reach')) || null,
    months: h.get('m'), radius: Number(h.get('r')) || null,
  };
  if (mode === 'pl') {
    const z = Number(h.get('z'));
    const clat = Number(h.get('clat'));
    const clng = Number(h.get('clng'));
    if (!h.get('z') || !Number.isFinite(z) || !Number.isFinite(clat) || !Number.isFinite(clng)) return false;
    const clamped = ui.setSelection(selection);
    state.pendingNote = clamped ? ui.MIN_REACH_NOTE : null;
    if (h.get('layer')) ui.selectLayer(h.get('layer'));
    if (state.mode !== 'pl') {                           // link wklejony w trybie miejsca: sprzątamy pinezkę, okrąg i stary wynik
      if (state.controller) state.controller.abort();
      clearTimeout(runTimer);
      resetResult();
      map.clearArea();
    }
    state.mode = 'pl';
    ui.setMode('pl');
    map.setView(clat, clng, z);                          // wywoła moveend → odświeżenie mgły
    scheduleView(0);
    return true;
  }
  if (!hasPlace || (!h.get('type') && !h.get('demand'))) return false;
  const clamped = ui.setSelection(selection);
  state.pendingNote = clamped ? ui.MIN_REACH_NOTE : null;   // stary link z zasięgiem < 0,3 km
  if (h.get('layer')) ui.selectLayer(h.get('layer'));
  if (state.mode !== 'place') {
    state.mode = 'place';
    clearTimeout(viewTimer);
    resetResult();
    ui.setMode('place');
    map.clearArea();
  }
  setPlace(lat, lng, h.get('n') || MAP_POINT, { fit: true });
  return true;
}

// ---- Podłączenie zdarzeń ----
map.onMapClick(onMapClick);
map.onViewChange(() => {
  if (state.mode !== 'pl') return;
  scheduleView(halfDiagonalKm(map.viewBounds()) <= LIVE_HALF_DIAGONAL_KM ? LIVE_DEBOUNCE_MS : NATIONAL_DEBOUNCE_MS);
  writeHash();
});

// Zmiana ustawień: tryb Polski przelicza widok; tryb miejsca po wyniku liczy od nowa (z opóźnieniem),
// a przed wynikiem tylko odświeża okrąg podglądu.
function onFormChange(source) {
  discardPoint();
  if (state.selection) loadSelectionInfo();              // liczby na karcie zależą od branży, klientów i zasięgu
  if (source === 'radius' && state.selection) return;    // promień zmienia tylko okrąg podglądu, nie starą analizę
  if (state.mode === 'pl') {
    ui.showInfo('');
    scheduleView(FORM_DEBOUNCE_MS);
    writeHash();
    return;
  }
  ui.showInfo('');
  if (state.result || state.loading) scheduleRun(false);   // także w trakcie pierwszego zapytania
  else if (state.place) map.setArea(state.place.lat, state.place.lng, ui.radiusKm(), { veil: false });
  writeHash();
}

ui.onModeChange(switchMode);
ui.onShowClick(() => {
  clearTimeout(runTimer);
  if (state.selection) confirmSelection(); else run({ fit: true });   // wybór w toku: »Pokaż mapę« działa jak ✓
});
ui.onRadiusInput((km) => setSelectionRadius(km, false));
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
window.addEventListener('hashchange', () => { if (applyHash() && state.mode === 'place') run({ fit: true }); });

getMeta().then(ui.renderFooter).catch(() => { /* stopka jest dodatkiem — brak metadanych nie przeszkadza */ });
getCatalog()
  .then((catalog) => {
    ui.renderCatalog(catalog, onFormChange);
    ui.setMode('pl');
    if (applyHash() && state.mode === 'place') run({ fit: true });
  })
  .catch((e) => ui.showError(e.message));

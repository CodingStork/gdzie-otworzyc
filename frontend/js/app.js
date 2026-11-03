// Punkt startowy frontendu: spina mapę, panele (lewy = ustawienia, prawy = wnioski) i API.
// v3.6 — jedna droga, bez przełącznika „Cała Polska / Wybrane miejsce” (Marcin: mapa liczyła się sama, zanim kliknął „Analizuj”):
//   1. W lewym panelu użytkownik wybiera narzędzie: ◯ Okrąg albo ▭ Prostokąt (nie ma domyślnego — bez niego kliknięcie mapy
//      tylko podpowiada, co zrobić).
//   2. Zaznacza obszar: okrąg po kliknięciu (zawsze ok. 1/5 ekranu, mapa płynnie się na nim centruje; kropka w środku go przesuwa,
//      kropka na krawędzi zmienia promień, promień można też wpisać w km) albo prostokąt przeciągnięciem (rogi zmieniają rozmiar).
//   3. Karta przy obszarze ma przycisk „Analizuj obszar” dopiero wtedy, gdy wybrano branżę lub klientów — inaczej mówi, co wybrać,
//      a te pola pulsują. NIC nie liczy się samo, zanim użytkownik kliknie „Analizuj”.
// Po analizie: zmiana ustawień przelicza TEN SAM obszar, ruch mapy tylko przemalowuje mgłę (kolory dopasowane do tego, co widać —
// bez zapytań do serwera), a kliknięcie w zbadany obszar pokazuje szczegóły punktu (Shneiderman: przegląd → zawężenie → szczegóły).
// Prostota (Marcin): po prawej tylko legenda i dwie liczby obszaru (klienci, firmy) ze źródłami — bez rankingu i notatek;
// wyjaśnienia są pod pytajnikami. Odświeżenie strony zaczyna od zera (stanu analizy nie zapisujemy w adresie).
import { getCatalog, getMeta, getPoi, point, surface } from './api.js';
import { logPosition, logScale, setDarkPalette, trendColor, trendPosition, trendScale } from './colors.js';
import { initIntro } from './intro.js';
import { initMap } from './map.js';
import * as ui from './ui.js';

const $ = (id) => document.getElementById(id);
const map = initMap('map');
// Uchwyt dla testów, które klikają w aplikację jak użytkownik (tests/e2e): stan i mapa Leaflet. Kod aplikacji z niego nie korzysta.
window.gdzieOtworzyc = { get state() { return state; }, get map() { return map.leaflet; } };

// tool: 'circle' | 'rect' | null — wybrane narzędzie.
// selection: zaznaczenie w toku (jeszcze nie przeanalizowane): { kind: 'circle', lat, lng, radiusKm, name } albo { kind: 'rect', bounds };
//   card: jego karta (ui.areaCard).
// area: przeanalizowany obszar (ten sam kształt co selection); result: odpowiedź /api/surface; used: ustawienia, dla których ją policzono.
const state = {
  tool: null, selection: null, card: null, area: null, result: null, used: null,
  controller: null, requestId: 0, loading: false,
};

const isMobile = () => window.matchMedia('(max-width: 767px)').matches;
const CIRCLE_SCREEN_FRACTION = 0.2;   // promień okręgu po kliknięciu = 20% krótszego boku mapy (ten sam rozmiar na ekranie przy każdym przybliżeniu)
const RECT_MIN_KM = 0.6;              // limity boku zaznaczonego prostokąta — jak w API (/api/surface?area=rect)
const RECT_MAX_KM = 700;
const NO_CIRCLE = 1e9;                // „promień” maski mgły bez okręgu (prostokąt jest przycięty już przez serwer)
const FORM_DEBOUNCE_MS = 300;
const VIEW_DEBOUNCE_MS = 150;
const MAP_POINT = 'punkt na mapie';   // nazwa miejsca wskazanego kliknięciem
const NEED_TOOL = 'Najpierw wybierz z lewej, jak zaznaczyć obszar: ◯ Okrąg albo ▭ Prostokąt.';
const SEARCH_RADIUS_KM = 2.5;          // miejscowość z wyszukiwarki: okrąg o średnicy 5 km

// Odległość po kuli w km (haversine).
function distanceKm(lat1, lng1, lat2, lng2) {
  const rad = Math.PI / 180;
  const a = Math.sin((lat2 - lat1) * rad / 2) ** 2 +
    Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin((lng2 - lng1) * rad / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.sqrt(a));
}

const kmText = (km) => String(km).replace('.', ',');

// Wymiary prostokąta w km (przybliżenie płaskie, jak w API).
function rectSizeKm(b) {
  const midLat = (b.south + b.north) / 2;
  return { width: (b.east - b.west) * 111.32 * Math.cos(midLat * Math.PI / 180), height: (b.north - b.south) * 110.54 };
}
const rectCenter = (b) => ({ lat: (b.south + b.north) / 2, lng: (b.west + b.east) / 2 });
const rectText = (b) => { const s = rectSizeKm(b); return ui.sizeText(s.width, s.height); };
const inRect = (b, lat, lng) => lat >= b.south && lat <= b.north && lng >= b.west && lng <= b.east;
const mercY = (lat) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI / 180) / 2));

// ---- Krok 1: narzędzie ----

function chooseTool(tool, { silent = false } = {}) {
  state.tool = tool;
  ui.setTool(tool);
  ui.toolsAttention(false);
  ui.showInfo('');
  if (tool === 'rect' && !silent) map.startRectDraw(); else map.stopRectDraw();
  if (isMobile() && !silent) ui.collapseSheet();     // arkusz z ustawieniami zasłaniałby mapę, na której trzeba teraz zaznaczyć
  if (!silent) intro.toolChosen(tool);
}

// Drugie kliknięcie wybranego narzędzia je odznacza: przy prostokącie lewy przycisk rysuje, więc żeby najpierw znaleźć
// fragment mapy, trzeba móc wrócić do zwykłego przesuwania (uwaga Marcina). Zaznaczony obszar zostaje.
function dropTool() {
  state.tool = null;
  ui.setTool(null);
  map.stopRectDraw();
  ui.showInfo('');
}

// Zmiana narzędzia przy zaznaczonym obszarze: ten sam fragment mapy w drugim kształcie — okrąg → kwadrat opisany na nim,
// prostokąt → okrąg o promieniu połowy krótszego boku (np. po wpisaniu miejscowości wystarczy kliknąć „Prostokąt”).
function convertSelection(tool) {
  const s = state.selection;
  if (tool === 'rect' && s.kind === 'circle') {
    const dlat = s.radiusKm / 110.54;
    const dlng = s.radiusKm / (111.32 * Math.cos(s.lat * Math.PI / 180));
    beginRect({ west: s.lng - dlng, south: s.lat - dlat, east: s.lng + dlng, north: s.lat + dlat });
  } else if (tool === 'circle' && s.kind === 'rect') {
    const size = rectSizeKm(s.bounds);
    const c = rectCenter(s.bounds);
    beginCircle(c.lat, c.lng, MAP_POINT, ui.snapRadius(Math.min(size.width, size.height) / 2));
  }
}

// ---- Krok 2: zaznaczenie obszaru (karta z ✓ dopiero, gdy jest co liczyć) ----

function clearSelection() {
  state.selection = null;
  state.card = null;
  map.clearSelection();
  ui.settingsAttention(false);
}

// Okrąg po kliknięciu: promień tak dobrany, żeby okrąg zajmował ok. 1/5 ekranu (przy oddalonej mapie — województwo, w mieście — osiedla),
// a mapa płynnie przesuwa się tak, żeby okrąg był na środku. radiusKm podany wprost: z wyszukiwarki albo z zamiany prostokąta.
function beginCircle(lat, lng, name = MAP_POINT, radiusKm = null) {
  discardPoint();
  clearSelection();
  radiusKm = radiusKm ?? ui.snapRadius(map.kmForScreenFraction(lat, lng, CIRCLE_SCREEN_FRACTION));
  state.selection = { kind: 'circle', lat, lng, radiusKm, name };
  state.card = ui.areaCard({
    kind: 'circle', radiusKm, onRadius: (km) => setCircleRadius(km, { fromInput: true }), onConfirm: confirmSelection, onCancel: clearSelection,
  });
  map.showCircle(lat, lng, radiusKm, state.card.el, {
    minKm: ui.RADIUS_MIN_KM,
    maxKm: ui.RADIUS_MAX_KM,
    move: (la, ln) => { Object.assign(state.selection, { lat: la, lng: ln, name: MAP_POINT }); },
    radius: (km, done) => setCircleRadius(km, { done }),
  });
  map.panTo(lat, lng);
  if (isMobile()) ui.collapseSheet();
  updateCardReady();
}

// Promień z pola w karcie albo z kropki na krawędzi. Zaokrąglamy (0,5 km do 5 km, potem 1 km, od 50 km — 5 km); w trakcie
// przeciągania kropki zmienia się tylko napis, a po puszczeniu okrąg dostaje zaokrąglony promień — ten, który policzy serwer.
function setCircleRadius(km, { fromInput = false, done = true } = {}) {
  const s = state.selection;
  if (!s || s.kind !== 'circle') return;
  s.radiusKm = ui.snapRadius(km);
  state.card.setRadius(s.radiusKm);
  if (fromInput || done) map.setCircleRadius(s.radiusKm);
  if (fromInput) map.fitCircleIfNeeded(s.lat, s.lng, s.radiusKm);
}

// Prostokąt narysowany przeciągnięciem: karta z wymiarami, rogi można przeciągać.
function beginRect(bounds) {
  discardPoint();
  clearSelection();
  state.selection = { kind: 'rect', bounds };
  state.card = ui.areaCard({ kind: 'rect', onConfirm: confirmSelection, onCancel: clearSelection });
  map.showRect(bounds, state.card.el, (b) => { state.selection.bounds = b; updateRectCard(); });
  ui.setTool('rect');
  if (isMobile()) ui.collapseSheet();
  updateRectCard();
  updateCardReady();
}

// Co jest nie tak z prostokątem (bok poza limitami 0,6–700 km)? Pusty tekst = wszystko w porządku.
function rectProblem(b) {
  const s = rectSizeKm(b);
  if (Math.max(s.width, s.height) > RECT_MAX_KM) return `Za duży obszar — maks. ${RECT_MAX_KM} km boku`;
  if (Math.min(s.width, s.height) < RECT_MIN_KM) return `Za mały obszar — min. ${kmText(RECT_MIN_KM)} km boku`;
  return '';
}

// Napis z wymiarami; poza limitami ramka jest czerwona, a ✓ nieaktywny.
function updateRectCard() {
  const b = state.selection.bounds;
  const problem = rectProblem(b);
  state.card.setSize(rectText(b), problem);
  map.setRectInvalid(!!problem);
  map.refreshSelectionCard();
}

// Karta przy obszarze: przycisk „Analizuj obszar” tylko wtedy, gdy wybrano branżę lub klientów; inaczej podpowiedź i pulsujące pola.
function updateCardReady() {
  if (!state.card) { ui.settingsAttention(false); return; }
  const ready = ui.hasSettings();
  state.card.setReady(ready);
  ui.settingsAttention(!ready);
  map.refreshSelectionCard();
}

// ✓ na karcie: zaznaczenie staje się analizowanym obszarem.
function confirmSelection() {
  const s = state.selection;
  if (!s || !ui.hasSettings()) return;
  if (s.kind === 'rect' && rectProblem(s.bounds)) return;
  state.area = s.kind === 'rect'
    ? { kind: 'rect', bounds: s.bounds }
    : { kind: 'circle', lat: s.lat, lng: s.lng, radiusKm: s.radiusKm, name: s.name };
  clearSelection();
  map.closeDetails();
  run({ fit: false });                                   // mapa już pokazuje obszar (okrąg jest na środku ekranu)
}

// ---- Analiza obszaru ----

let runTimer = null;
function scheduleRun() {
  clearTimeout(runTimer);
  runTimer = setTimeout(() => run({ fit: false }), FORM_DEBOUNCE_MS);   // debounce: czekamy, aż użytkownik skończy zmieniać ustawienia
}

async function run({ fit }) {
  const area = state.area;
  if (!area) return;
  const p = ui.selectedParams();
  if (!p.type && !p.demand) {                           // ktoś wyczyścił ustawienia po analizie — nie ma czego pokazywać
    resetResult();
    ui.showInfo('Wybierz branżę lub klientów, żeby przeanalizować zaznaczony obszar.');
    return;
  }
  ui.showInfo('');
  ui.showError('');
  if (state.controller) state.controller.abort();       // poprzednie zapytanie jest już nieaktualne
  const controller = new AbortController();
  state.controller = controller;
  const mine = ++state.requestId;
  const used = area.kind === 'rect'
    ? { ...p, ...rectCenter(area.bounds), area: 'rect', bounds: area.bounds, name: 'zaznaczony obszar' }
    : { ...p, lat: area.lat, lng: area.lng, radius_km: area.radiusKm, name: area.name };
  const query = area.kind === 'rect'
    ? { type: p.type, demand: p.demand, reach_km: p.reach_km, months: p.months, area: 'rect', ...area.bounds }
    : { type: p.type, demand: p.demand, lat: area.lat, lng: area.lng, radius_km: area.radiusKm, reach_km: p.reach_km, months: p.months };
  ui.setLoading(true);
  state.loading = true;
  try {
    const result = await surface(query, controller.signal);
    if (mine !== state.requestId) return;
    discardPoint();
    showResult(result, used, fit);
  } catch (e) {
    if (e.name === 'AbortError') return;                 // zastąpione nowszym zapytaniem
    if (mine !== state.requestId) return;
    ui.showError(e.message);
  } finally {
    if (mine === state.requestId) { ui.setLoading(false); state.loading = false; }
  }
}

// Wartości komórek siatki, których środek jest teraz widoczny na ekranie (siatka: wiersze od północy; gotowa mapa Polski jest równa
// w Mercatorze, siatka na żywo — w metrach, czyli w przybliżeniu równa w stopniach). Z nich liczymy skalę kolorów.
function visibleValues(grid, values) {
  const b = map.viewBounds();
  const merc = grid.projection === 'mercator';
  const y = (lat) => (merc ? mercY(lat) : lat);
  const yN = y(grid.north);
  const yS = y(grid.south);
  const out = [];
  for (let j = 0; j < grid.ny; j++) {
    const yc = yN - (j + 0.5) * (yN - yS) / grid.ny;
    if (yc < y(b.south) || yc > y(b.north)) continue;
    for (let i = 0; i < grid.nx; i++) {
      const xc = grid.west + (i + 0.5) * (grid.east - grid.west) / grid.nx;
      if (xc < b.west || xc > b.east) continue;
      const v = values[j * grid.nx + i];
      if (v !== null) out.push(v);
    }
  }
  return out;
}

// Rysuje wybraną warstwę z ostatniego wyniku — bez zapytania do serwera. Skala kolorów jest liczona z wartości WIDOCZNYCH na ekranie
// (v3.6: przy jednej skali dla całego obszaru centrum miasta miało jeden kolor, choć liczby w różnych punktach różniły się o połowę).
function drawLayer() {
  const { result, used } = state;
  let layer = ui.currentLayer();
  if (!result.values[layer]) layer = result.layers[0];   // np. warstwa niedostępna w gotowej mapie: rysujemy pierwszą dostępną
  const values = layer && result.values[layer];
  if (!values) {                                         // brak warstwy (np. ten wybór jej nie ma)
    map.clearFog();
    ui.hideLegend();
    return;
  }
  const title = ui.legendTitle(layer, used.type, used.demand);
  const radius = used.area === 'rect' ? NO_CIRCLE : used.radius_km;
  const center = used.area === 'rect' ? null : { lat: used.lat, lng: used.lng };
  const visible = visibleValues(result.grid, values);
  if (layer === 'trend') {
    // Trend ma znak (spadek / wzrost): paleta rozbieżna, środek (bez zmian) przezroczysty.
    const scale = trendScale(visible) || trendScale(values);
    if (!scale) {
      map.clearFog();
      ui.hideLegend();
    } else {
      const t = new Float32Array(values.length);
      values.forEach((v, i) => { t[i] = v === null ? NaN : trendPosition(v, scale); });
      map.setFog(result.grid, t, radius, trendColor, null, center);
      ui.renderTrendLegend(title);
    }
  } else {
    const scale = logScale(visible) || logScale(values);
    if (!scale) {
      map.clearFog();
      ui.hideLegend();
    } else {
      const t = new Float32Array(values.length);
      values.forEach((v, i) => { t[i] = v === null ? NaN : logPosition(v, scale); });
      // Szare kreskowanie „mało danych o firmach” — tylko na warstwie „Gdzie otworzyć”.
      const gapCells = layer === 'open' && result.gap && result.gap.open;
      const gap = gapCells ? Float32Array.from(gapCells, (g) => (g === null ? NaN : g)) : null;
      map.setFog(result.grid, t, radius, undefined, gap, center);
      ui.renderLegend(title, scale, !!gap && gap.includes(1));
    }
  }
}

function showResult(result, used, fit) {
  state.result = result;
  state.used = used;
  ui.showInsights();                                     // panel po prawej zmienia szerokość mapy
  map.invalidateSize();
  if (used.area === 'rect') {
    map.setRectArea(used.bounds, { veil: true, fit });
  } else {
    map.setArea(used.lat, used.lng, used.radius_km, { veil: true });
    if (fit) map.fitCircle(used.lat, used.lng, used.radius_km);
  }
  drawLayer();
  ui.renderSummary(result.summary, { demandId: used.demand, permitsPeriod: result.permits_period });
  ui.renderWarnings(withoutTypeWarning(result.warnings, used.type));
  if (isMobile()) ui.setTab('insights');                 // na telefonie po analizie od razu wnioski
}

// Ostrzeżenie o niepełnych danych dla branży jest już pod wyborem branży (lewy panel) — nie powtarzamy go pod mapą.
function withoutTypeWarning(warnings, typeId) {
  const type = ui.typeById(typeId);
  return warnings.filter((w) => !type || w !== type.warning);
}

// Czyści wynik i wszystko, co z niego narysowano.
function resetResult() {
  state.result = null;
  state.used = null;
  discardPoint();
  map.clearFog();
  map.clearArea();
  ui.hideLegend();
  ui.hideSummary();
  ui.renderWarnings([]);
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
    map.showDetails(lat, lng, data.radius_km, competitors, ui.pointPopup(data, () => newCircleAt(lat, lng)));
  } catch (e) {
    if (mine === pointRequest) ui.showError(e.message);
  }
}

// „Zaznacz tu nowy okrąg” w dymku: nowe zaznaczenie z karty (analiza dopiero po ✓).
function newCircleAt(lat, lng) {
  if (state.tool !== 'circle') chooseTool('circle', { silent: true });
  beginCircle(lat, lng);
}

// Czy punkt leży w przeanalizowanym obszarze (okręgu albo prostokącie)?
function insideAnalysis(lat, lng) {
  const u = state.used;
  return u.area === 'rect' ? inRect(u.bounds, lat, lng) : distanceKm(lat, lng, u.lat, u.lng) <= u.radius_km;
}

// Kliknięcie w mapę: w przeanalizowanym obszarze — szczegóły punktu; poza nim — zależnie od narzędzia: nowy okrąg,
// nowy prostokąt (włączamy rysowanie) albo (bez narzędzia) podpowiedź, że najpierw trzeba je wybrać.
function onMapClick(lat, lng) {
  if (state.result && insideAnalysis(lat, lng)) {
    showPointAt(lat, lng);
    return;
  }
  if (state.tool === 'circle') {
    beginCircle(lat, lng);
  } else if (state.tool === 'rect') {
    map.startRectDraw();
    ui.showInfo('Przeciągnij po mapie, żeby narysować nowy prostokąt.');
  } else {
    ui.showInfo(NEED_TOOL);
    ui.toolsAttention(true);
  }
}

// ---- Tryb nocny ----
// Na start jak w systemie (index.html ustawia data-theme przed pierwszą klatką); przycisk ☾/☀ przy mapie zmienia go
// do odświeżenia strony — nie zapamiętujemy wyboru, bo odświeżenie ma przywracać ustawienia fabryczne.
const systemDark = window.matchMedia('(prefers-color-scheme: dark)');
let themeChosen = false;

function applyTheme(dark) {
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  setDarkPalette(dark);
  map.setTheme(dark);
  if (!state.result) return;
  const u = state.used;                                  // obrys obszaru ma kolor motywu — rysujemy go jeszcze raz
  if (u.area === 'rect') map.setRectArea(u.bounds, { veil: true });
  else map.setArea(u.lat, u.lng, u.radius_km, { veil: true });
  drawLayer();
}

// ---- Start: zawsze od zera ----
// Marcin: odświeżenie strony ma przywracać ustawienia fabryczne, jakby zrestartował się serwer — dlatego NIE zapisujemy analizy
// w adresie. Adres może tylko ustawić widok mapy (#z=…&clat=…&clng=…, np. w testach), a potem go czyścimy, żeby odświeżenie
// znów zaczynało od widoku całej Polski.
function applyViewHash() {
  const h = new URLSearchParams(location.hash.slice(1));
  const z = Number(h.get('z'));
  const clat = Number(h.get('clat'));
  const clng = Number(h.get('clng'));
  if (h.get('z') && [z, clat, clng].every(Number.isFinite)) map.setView(clat, clng, z);
  if (location.hash) history.replaceState(null, '', location.pathname + location.search);
}

// ---- Podłączenie zdarzeń ----

map.onMapClick(onMapClick);
map.onRectDrawn(beginRect);
map.onDrawCancel(() => ui.setTool('rect'));
// Ruch mapy po analizie: tylko przemalowanie mgły (skala z widocznych wartości), bez zapytań do serwera.
let viewTimer = null;
map.onViewChange(() => {
  if (!state.result) return;
  clearTimeout(viewTimer);
  viewTimer = setTimeout(drawLayer, VIEW_DEBOUNCE_MS);
});

// Zmiana ustawień: karta zaznaczenia sprawdza, czy można już analizować; przeanalizowany obszar liczy się od nowa (po 300 ms).
// Przed pierwszym „Analizuj” nic się nie liczy.
function onFormChange() {
  discardPoint();
  updateCardReady();
  ui.showInfo('');
  if (state.area && (state.result || state.loading)) scheduleRun();
}

const intro = initIntro(map.leaflet.getContainer());
ui.initTools((tool) => {
  if (tool === state.tool) { dropTool(); return; }
  if (state.selection) {                                 // jest zaznaczenie: zamieniamy jego kształt zamiast rysować od nowa
    chooseTool(tool, { silent: true });
    convertSelection(tool);
    return;
  }
  chooseTool(tool);
});
map.onHelpClick(() => intro.show(state.tool));
map.onThemeClick(() => { themeChosen = true; applyTheme(document.documentElement.dataset.theme !== 'dark'); });
systemDark.addEventListener('change', (e) => { if (!themeChosen) applyTheme(e.matches); });
applyTheme(systemDark.matches);
ui.onLayerChange(() => {
  discardPoint();
  if (state.result) drawLayer();
});
$('opacity-input').addEventListener('input', () => map.setFogOpacity(Number($('opacity-input').value)));

ui.initTabs(() => map.invalidateSize());
ui.renderHelp();
// Wyszukiwarka: mapa przelatuje do miejsca i zaznacza tam okrąg o średnicy 5 km (analiza dopiero po ✓).
ui.initSearch((place) => {
  chooseTool('circle', { silent: true });
  map.leaflet.once('moveend', () => beginCircle(place.lat, place.lng, place.name.split(',')[0], SEARCH_RADIUS_KM));
  map.flyToCircle(place.lat, place.lng, SEARCH_RADIUS_KM);
});

getMeta().then(ui.renderFooter).catch(() => { /* stopka jest dodatkiem — brak metadanych nie przeszkadza */ });
getCatalog()
  .then((catalog) => {
    ui.renderCatalog(catalog, onFormChange);
    applyViewHash();
    intro.showFirstTime();                               // pierwsza wizyta: pokaż, jak zacząć
  })
  .catch((e) => ui.showError(e.message));

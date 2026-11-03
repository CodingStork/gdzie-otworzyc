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
import { getCatalog, getMeta, getPoi, point, surface } from './api.js';
import { logPosition, logScale, trendColor, trendPosition, trendScale } from './colors.js';
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
  controller: null, requestId: 0, loading: false, pendingNote: null,
};

const isMobile = () => window.matchMedia('(max-width: 767px)').matches;
const CIRCLE_SCREEN_FRACTION = 0.2;   // promień okręgu po kliknięciu = 20% krótszego boku mapy (ten sam rozmiar na ekranie przy każdym przybliżeniu)
const LIVE_RECT_KM = 60;              // prostokąt do 60 km boku liczymy na żywo, większy — z gotowej mapy Polski (backend: national.run_area)
const RECT_MIN_KM = 0.6;              // limity boku zaznaczonego prostokąta — jak w API (/api/surface?area=rect)
const RECT_MAX_KM = 700;
const NO_CIRCLE = 1e9;                // „promień” maski mgły bez okręgu (prostokąt jest przycięty już przez serwer)
const FORM_DEBOUNCE_MS = 300;
const VIEW_DEBOUNCE_MS = 150;
const SMALL_SPREAD = 0.2;             // najlepsze miejsca różniące się o mniej niż 20% traktujemy jak równie dobre (dokładność danych)
const MAP_POINT = 'punkt na mapie';   // nazwa miejsca wskazanego kliknięciem (w podsumowaniu zastępuje ją najbliższe miasto z serwera)
const NEED_TOOL = 'Najpierw wybierz z lewej, jak zaznaczyć obszar: ◯ Okrąg albo ▭ Prostokąt.';
const TOOL_HINTS = {
  circle: 'Kliknij mapę w miejscu, które chcesz zbadać. Kropką na krawędzi zmienisz promień, kropką w środku przesuniesz okrąg.',
  rect: 'Przeciągnij po mapie, żeby zaznaczyć prostokąt. Za rogi zmienisz jego rozmiar.',
};
const RECT_AGAIN_HINT = 'Za rogi zmienisz rozmiar prostokąta. Żeby narysować nowy, kliknij jeszcze raz »▭ Prostokąt« albo mapę poza nim.';
const BIG_TOP_HINT = 'Najlepsze miejsca pokazujemy dla obszaru do 30 km promienia (60 km boku): na dużym obszarze ranking mieszałby ' +
  'miasta ze wsiami, dla których model zawyża wynik. Zaznacz mniejszy obszar.';

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
  ui.setTool(tool, TOOL_HINTS[tool]);
  ui.toolsAttention(false);
  ui.showInfo('');
  if (tool === 'rect' && !silent) map.startRectDraw(); else map.stopRectDraw();
  if (isMobile() && !silent) ui.collapseSheet();     // arkusz z ustawieniami zasłaniałby mapę, na której trzeba teraz zaznaczyć
  if (!silent) intro.toolChosen(tool);
}

// ---- Krok 2: zaznaczenie obszaru (karta z ✓ dopiero, gdy jest co liczyć) ----

function clearSelection() {
  state.selection = null;
  state.card = null;
  map.clearSelection();
  ui.settingsAttention(false);
}

// Okrąg po kliknięciu: promień tak dobrany, żeby okrąg zajmował ok. 1/5 ekranu (przy oddalonej mapie — województwo, w mieście — osiedla),
// a mapa płynnie przesuwa się tak, żeby okrąg był na środku.
function beginCircle(lat, lng, name = MAP_POINT) {
  discardPoint();
  clearSelection();
  const radiusKm = ui.snapRadius(map.kmForScreenFraction(lat, lng, CIRCLE_SCREEN_FRACTION));
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
  ui.setTool('rect', RECT_AGAIN_HINT);
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
  const s = rectSizeKm(b);
  state.card.setSize(rectText(b), problem, Math.max(s.width, s.height) > LIVE_RECT_KM);
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
  const px = map.viewBounds().px;                       // szerokość mapy: rozdzielczość gotowej mapy dla dużego obszaru
  const used = area.kind === 'rect'
    ? { ...p, ...rectCenter(area.bounds), area: 'rect', bounds: area.bounds, name: 'zaznaczony obszar' }
    : { ...p, lat: area.lat, lng: area.lng, radius_km: area.radiusKm, name: area.name };
  const query = area.kind === 'rect'
    ? { type: p.type, demand: p.demand, reach_km: p.reach_km, months: p.months, area: 'rect', ...area.bounds, px }
    : { type: p.type, demand: p.demand, lat: area.lat, lng: area.lng, radius_km: area.radiusKm, reach_km: p.reach_km, months: p.months, px };
  ui.setLoading(true);
  state.loading = true;
  try {
    const result = await surface(query, controller.signal);
    if (mine !== state.requestId) return;
    discardPoint();
    showResult(result, used, fit);
    writeHash();
  } catch (e) {
    if (e.name === 'AbortError') return;                 // zastąpione nowszym zapytaniem
    if (mine !== state.requestId) return;
    ui.showError(e.message);
  } finally {
    if (mine === state.requestId) { ui.setLoading(false); state.loading = false; }
  }
}

const hasPermits = () => !!(state.result && state.result.permits_period);

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

// Wartość mapy (koloru) w punkcie: komórka siatki, w której leży punkt — do dymku „Kolor mapy w tym miejscu: …”.
function valueAt(lat, lng) {
  const { result, used } = state;
  let layer = ui.currentLayer();
  if (!result.values[layer]) layer = result.layers[0];
  const values = layer && result.values[layer];
  if (!values) return null;
  const g = result.grid;
  const merc = g.projection === 'mercator';
  const y = (v) => (merc ? mercY(v) : v);
  const i = Math.floor((lng - g.west) / (g.east - g.west) * g.nx);
  const j = Math.floor((y(g.north) - y(lat)) / (y(g.north) - y(g.south)) * g.ny);
  if (i < 0 || j < 0 || i >= g.nx || j >= g.ny) return null;
  const v = values[j * g.nx + i];
  return v === null ? null : { value: v, label: ui.legendTitle(layer, used.type, used.demand) };
}

// Rysuje wybraną warstwę z ostatniego wyniku — bez zapytania do serwera. Skala kolorów jest liczona z wartości WIDOCZNYCH na ekranie
// (v3.6: przy jednej skali dla całego obszaru centrum miasta miało jeden kolor, choć liczby w różnych punktach różniły się o połowę).
// withTop = false: tylko przemalowanie po ruchu mapy (lista najlepszych miejsc się nie zmienia).
function drawLayer({ withTop = true } = {}) {
  const { result, used } = state;
  let layer = ui.currentLayer();
  if (!result.values[layer]) layer = result.layers[0];   // np. warstwa niedostępna w gotowej mapie: rysujemy pierwszą dostępną
  const values = layer && result.values[layer];
  if (!values) {                                         // brak warstwy (np. duży obszar bez gotowej mapy dla tego wyboru)
    map.clearFog();
    ui.hideLegend();
    if (withTop) { map.setTopMarkers([], () => {}); ui.renderTop([], ui.currentLayer(), false, () => {}); ui.setTopNote(''); }
    return;
  }
  const title = ui.legendTitle(layer, used.type, used.demand);
  const period = result.permits_period;
  const radius = used.area === 'rect' ? NO_CIRCLE : used.radius_km;
  const center = used.area === 'rect' ? null : { lat: used.lat, lng: used.lng };
  const visible = visibleValues(result.grid, values);
  const VIEW_NOTE = 'Kolory dopasowane do tego, co widać — przybliż mapę, żeby zobaczyć różnice w mieście.';
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
      ui.renderTrendLegend(title, `mniej budów ← → więcej budów (ostatnie 12 mies. vs poprzednie 12) · ${VIEW_NOTE}`);
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
      // Dla czynników z pozwoleń podajemy okres danych i zastrzeżenie (pozwolenie ≠ wybudowany dom, blok = jeden budynek).
      const notes = [];
      if (period && layer !== 'competition') {
        const blocks = ['new_mf', 'new_all'].includes(used.demand) ? ' Blok liczy się jak jeden budynek (rejestr nie podaje liczby mieszkań).' : '';
        notes.push(`Pozwolenia: ${period.from} – ${period.to}. Pozwolenie nie oznacza wybudowanego domu.${blocks}`);
      }
      notes.push(VIEW_NOTE);
      ui.renderLegend(title, scale, notes.join(' '), !!gap && gap.includes(1));
    }
  }
  if (!withTop) return;
  if (result.area === 'big') {
    // Duży obszar (z gotowej mapy Polski): bez rankingu — patrz BIG_TOP_HINT i docs/audyt-przydatnosci.md (B4, B7).
    ui.renderTop([], layer, hasPermits(), () => {}, false, BIG_TOP_HINT);
    ui.setTopNote('');
    map.setTopMarkers([], () => {});
    return;
  }
  const top = result.top[layer] || [];
  // Pusta lista przy kreskowaniu to nie „brak danych”, tylko miejsca bez wiarygodnych klientów — mówimy to wprost.
  const onlyGaps = layer === 'open' && result.gap && result.gap.open.includes(1) && !top.length;
  const edge = !!(result.top_edge && result.top_edge[layer]);
  const emptyText = onlyGaps ? 'Brak wiarygodnych miejsc: wyniki tutaj opierają się głównie na lukach w danych o firmach (kreskowanie).'
    : edge ? 'Nie ma tu wyraźnie najlepszego miejsca — wartości rosną w stronę krawędzi obszaru, więc lepsze miejsce leży tuż obok. Przesuń obszar.'
      : undefined;
  ui.renderTop(top, layer, hasPermits(), (place) => openPlace(place), false, emptyText);
  ui.setTopNote(topNote(top, edge, layer === 'open' && result.summary && result.summary.verdict === 'few'));
  map.setTopMarkers(top, (place) => openPlace(place));
}

// Zdania pod najlepszymi miejscami: gdy różnią się o mniej niż 20% (to mniej niż dokładność danych), gdy na krawędzi
// obszaru jest więcej niż w najlepszym miejscu (szczyt leży poza obszarem) i gdy obszar jest słabo zaludniony (sparse).
function topNote(top, edge, sparse) {
  const notes = [];
  if (sparse && top.length) {
    // Audyt: na wsi model daje setki „klientów”, bo przy zasięgu typowym dla miasta nie widzi firm w mieście kilka km dalej.
    notes.push('Na słabo zaludnionym terenie model zawyża liczbę klientów: zakłada, że klienci nie dojeżdżają dalej niż kilka km, ' +
      'więc nie widzi firm w najbliższym mieście, do których jeżdżą.');
  }
  if (top.length >= 2) {
    const values = top.map((p) => p.value);
    if ((Math.max(...values) - Math.min(...values)) / Math.max(...values) < SMALL_SPREAD) {
      notes.push('Te miejsca różnią się o mniej niż 20% — to mniej niż dokładność danych. Wybieraj między nimi według lokalu, czynszu i ruchu na ulicy.');
    }
  }
  if (edge && top.length) notes.push('Na skraju obszaru wartości są wyższe niż tutaj — warto przesunąć obszar w tę stronę.');
  return notes.join(' ');
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
  // Miejsce wskazane kliknięciem nazywamy jak najbliższe miasto z odpowiedzi serwera („Brzeg, promień 3 km”), a nie „punkt na mapie”.
  const placeName = used.name === MAP_POINT && result.summary.place_name ? result.summary.place_name : used.name;
  ui.renderSummary(result.summary, { placeName, demandId: used.demand, permitsPeriod: result.permits_period });
  ui.renderWarnings(withoutTypeWarning(result.warnings, used.type));
  ui.renderNotes([...(state.pendingNote ? [state.pendingNote] : []), ...result.notes]);
  state.pendingNote = null;
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
  map.setTopMarkers([], () => {});
  ui.hideLegend();
  ui.hideSummary();
  ui.renderTop([], 'open', false, () => {});
  ui.setTopNote('');
  $('top-title').hidden = true;
  ui.renderWarnings([]);
  ui.renderNotes([]);
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
    data.map_value = valueAt(lat, lng);                   // ta sama liczba, z której wziął się kolor mapy w tym miejscu
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

// Wskazane miejsce (z listy top-5 albo ze znacznika): przybliżamy mapę i pokazujemy szczegóły.
function openPlace(place) {
  if (isMobile()) ui.collapseSheet();                    // arkusz zasłaniałby mapę i dymek
  map.safeFlyTo(place.lat, place.lng, Math.max(map.getView().zoom, 13));
  showPointAt(place.lat, place.lng);
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

// ---- Stan w adresie URL — link można komuś wysłać ----
//   Okrąg:      #type=…&demand=…&reach=…&m=…&layer=…&lat=…&lng=…&r=…&n=…
//   Prostokąt:  #type=…&demand=…&reach=…&m=…&layer=…&bbox=zachód,południe,wschód,północ
// Stare linki z mode=pl (tryb „Cała Polska” do v3.5) ustawiają tylko widok mapy i wybór branży.

function writeHash() {
  const a = state.area;
  if (!a) return;
  const p = ui.selectedParams();
  const hash = new URLSearchParams({ type: p.type, demand: p.demand, reach: p.reach_km, layer: ui.currentLayer() });
  if (a.kind === 'rect') {
    const b = a.bounds;
    hash.set('bbox', [b.west, b.south, b.east, b.north].map((v) => v.toFixed(5)).join(','));
  } else {
    hash.set('lat', a.lat.toFixed(5));
    hash.set('lng', a.lng.toFixed(5));
    hash.set('r', a.radiusKm);
    hash.set('n', a.name);
  }
  if (p.months) hash.set('m', p.months);                 // okres tylko dla czynników z pozwoleń
  history.replaceState(null, '', '#' + hash);
}

// Odtwarza ustawienia z adresu; zwraca true, gdy adres zawierał obszar i ustawienia (wtedy od razu go analizujemy).
function applyHash() {
  const h = new URLSearchParams(location.hash.slice(1));
  const selection = { type: h.get('type'), demand: h.get('demand'), reach: Number(h.get('reach')) || null, months: h.get('m') };
  const lat = Number(h.get('lat'));
  const lng = Number(h.get('lng'));
  const r = Number(h.get('r'));
  const hasCircle = h.get('lat') && h.get('lng') && Number.isFinite(lat) && Number.isFinite(lng);
  const box = (h.get('bbox') || '').split(',').map(Number);   // prostokąt: zachód, południe, wschód, północ
  const hasBbox = box.length === 4 && box.every(Number.isFinite) && box[0] < box[2] && box[1] < box[3];
  if (!hasCircle && !hasBbox) {
    const z = Number(h.get('z'));
    const clat = Number(h.get('clat'));
    const clng = Number(h.get('clng'));
    if (h.get('z') && [z, clat, clng].every(Number.isFinite)) {   // stary link „Cała Polska”: tylko widok i ustawienia, bez analizy
      state.area = null;
      clearSelection();
      resetResult();
      state.pendingNote = ui.setSelection(selection) ? ui.MIN_REACH_NOTE : null;
      map.setView(clat, clng, z);
    }
    return false;
  }
  if (!h.get('type') && !h.get('demand')) return false;
  state.pendingNote = ui.setSelection(selection) ? ui.MIN_REACH_NOTE : null;   // stary link z zasięgiem < 0,3 km
  if (h.get('layer')) ui.selectLayer(h.get('layer'));
  clearSelection();
  if (hasBbox) {
    state.area = { kind: 'rect', bounds: { west: box[0], south: box[1], east: box[2], north: box[3] } };
  } else {
    state.area = { kind: 'circle', lat, lng, radiusKm: ui.snapRadius(r || 10), name: h.get('n') || MAP_POINT };
  }
  chooseTool(state.area.kind, { silent: true });         // narzędzie zgodne z obszarem z linku (bez włączania rysowania)
  return true;
}

// ---- Podłączenie zdarzeń ----

map.onMapClick(onMapClick);
map.onRectDrawn(beginRect);
map.onDrawCancel(() => ui.setTool('rect', RECT_AGAIN_HINT));
// Ruch mapy po analizie: tylko przemalowanie mgły (skala z widocznych wartości), bez zapytań do serwera.
let viewTimer = null;
map.onViewChange(() => {
  if (!state.result) return;
  clearTimeout(viewTimer);
  viewTimer = setTimeout(() => drawLayer({ withTop: false }), VIEW_DEBOUNCE_MS);
});

// Zmiana ustawień: karta zaznaczenia sprawdza, czy można już analizować; przeanalizowany obszar liczy się od nowa (po 300 ms).
// Przed pierwszym „Analizuj” nic się nie liczy.
function onFormChange() {
  discardPoint();
  updateCardReady();
  ui.showInfo('');
  if (state.area && (state.result || state.loading)) scheduleRun();
  writeHash();
}

const intro = initIntro(map.leaflet.getContainer());
ui.initTools((tool) => {
  if (tool === state.tool && tool === 'rect') { map.startRectDraw(); ui.setTool('rect', TOOL_HINTS.rect); return; }   // nowy prostokąt
  chooseTool(tool);
});
map.onHelpClick(() => intro.show(state.tool));
ui.onLayerChange(() => {
  discardPoint();
  if (state.result) drawLayer();
  writeHash();
});
$('opacity-input').addEventListener('input', () => map.setFogOpacity(Number($('opacity-input').value)));

ui.initTabs(() => map.invalidateSize());
ui.renderHelp();
// Wyszukiwarka: mapa przelatuje do miejsca i zaznacza tam okrąg (analiza dopiero po ✓).
ui.initSearch((place) => {
  chooseTool('circle', { silent: true });
  map.leaflet.once('moveend', () => beginCircle(place.lat, place.lng, place.name.split(',')[0]));
  map.safeFlyTo(place.lat, place.lng, 12);
});

// Wklejenie innego linku w tej samej karcie zmienia tylko hash (bez przeładowania) — odtwórz widok.
window.addEventListener('hashchange', () => { if (applyHash()) run({ fit: true }); });

getMeta().then(ui.renderFooter).catch(() => { /* stopka jest dodatkiem — brak metadanych nie przeszkadza */ });
getCatalog()
  .then((catalog) => {
    ui.renderCatalog(catalog, onFormChange);
    if (applyHash()) run({ fit: true });
    else intro.showFirstTime();                          // pierwsza wizyta bez linku: pokaż, jak zacząć
  })
  .catch((e) => ui.showError(e.message));

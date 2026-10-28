// Interfejs: lewy panel (same ustawienia), prawy panel (legenda i wnioski o obszarze), pytajniki z wyjaśnieniami,
// dymek ze szczegółami punktu, wyszukiwarka adresów i zakładki arkusza na telefonie.
import { geocode } from './api.js';
import { fogGradientCss, niceLogTicks, trendGradientCss } from './colors.js';
import { SOURCE_NAMES } from './map.js';

const $ = (id) => document.getElementById(id);

let catalog = null;

// useGrouping: 'always' — domyślnie pl-PL nie grupuje liczb czterocyfrowych (1500), a pięciocyfrowe tak (15 800).
export const fmt = (n, digits = 0) =>
  Number(n).toLocaleString('pl-PL', { maximumFractionDigits: digits, useGrouping: 'always' });

const capitalize = (text) => text.charAt(0).toUpperCase() + text.slice(1);

// ---- Wyjaśnienia pod pytajnikami (teksty ze specyfikacji v3 §5, uzupełnione w v3.1 o drugie źródło firm — Overture) ----
const HELP = {
  area: 'Cała Polska: od razu widzisz całą mapę i możesz ją swobodnie przybliżać. Po oddaleniu pokazujemy gotową mapę dla typowego zasięgu branży, ' +
    'a po przybliżeniu do miasta liczymy ją na żywo z Twoimi ustawieniami. Wybrane miejsce: analiza okręgu wokół jednego miejsca ' +
    'z podsumowaniem i porównaniem ze średnią krajową.',
  open: 'Ilu klientów mogłaby przyciągnąć nowa firma w danym miejscu. Liczymy to modelem Huffa: każdy mieszkaniec wybiera między firmami, ' +
    'a bliższa firma przyciąga go mocniej. Uwzględniamy wszystkich konkurentów z OpenStreetMap i Overture Maps oraz »inne możliwości« ' +
    '(firmy, których nie ma w tych bazach, zakupy gdzie indziej). Najbardziej czerwone miejsca to najlepsze lokalizacje.',
  demand: 'Ilu potencjalnych klientów jest w pobliżu danego miejsca — bliżsi liczą się bardziej. ' +
    'Mieszkańcy to szacunek: spis 2021 rozłożony na budynki mieszkalne z OpenStreetMap. ' +
    'Dla nowych domów liczymy pozwolenia na budowę z wybranego okresu.',
  competition: 'Gdzie jest najwięcej firm wybranego typu. Dane z OpenStreetMap i Overture Maps — mogą być niepełne.',
  trend: 'Gdzie w ostatnich 12 miesiącach wydano więcej pozwoleń na nowe budynki niż w 12 miesiącach wcześniej. ' +
    'Czerwony = budów przybywa (rozwijająca się okolica), niebieski = ubywa, przezroczysty = bez zmian. ' +
    'Pozwolenie nie oznacza jeszcze wybudowanego domu.',
  reach: 'Jak daleko typowy klient jest gotów dojść lub dojechać. Fryzjer, sklep spożywczy: kilkaset metrów do 2 km; ' +
    'market budowlany, brukarz: 10–20 km. W tej odległości chęć dotarcia spada o ok. 2/3, a dwa razy dalej — o ok. 85%. ' +
    'Najmniejszy zasięg to 0,3 km, bo dane o mieszkańcach mają rozdzielczość ok. 300 m.',
  radius: 'Jak duży obszar wokół wybranego miejsca przeanalizować. Mniejszy obszar = szybciej i dokładniej.',
  legend: 'Kolor w skali logarytmicznej: każdy krok koloru to mniej więcej podwojenie wartości. ' +
    'Przezroczyste miejsca mają bardzo małe wartości. Dokładne liczby zobaczysz po kliknięciu mapy. ' +
    'Na mapie całej Polski skala jest stała (te same kolory znaczą te same liczby w każdym mieście); po przybliżeniu kolory dopasowują się do widoku.',
  gaps: 'Szare kreskowanie: większość klientów tego miejsca mieszka tam, gdzie w danych jest podejrzanie mało firm ' +
    '(najwyżej ¼ tego, co wynika ze średniej krajowej przy takiej liczbie mieszkańców). Wynik może być wtedy skutkiem luki w danych ' +
    '(brak firm w OpenStreetMap i Overture Maps), a nie braku konkurencji. Takich miejsc nie pokazujemy w najlepszych miejscach. ' +
    'Małych miejscowości, w których średnio byłyby mniej niż 3 firmy, nie oceniamy.',
  summary: 'Liczby dotyczą całego zaznaczonego okręgu. Średnia krajowa pokazuje, ilu klientów przypada na jedną firmę tego typu ' +
    'w całej Polsce — jeśli tutaj jest ich wyraźnie więcej, konkurencja jest mniejsza niż zwykle. ' +
    'Firmy: OpenStreetMap + Overture Maps (mogą nie obejmować wszystkich).',
};

// Pytajnik: przycisk .help[data-help]. Podpowiedź pokazuje się po najechaniu lub kliknięciu,
// zamyka ją kliknięcie poza nią albo Escape (klik w pytajnik „przypina” ją na stałe).
// Zdarzenia obsługujemy delegacją z dokumentu, więc działa też dla pytajników rysowanych dynamicznie.
export function renderHelp() {
  const pop = $('help-popover');
  let pinned = null;   // przycisk, którego podpowiedź jest przypięta kliknięciem

  const show = (button) => {
    pop.textContent = HELP[button.dataset.help];
    pop.hidden = false;
    const r = button.getBoundingClientRect();
    const width = Math.min(280, window.innerWidth - 16);
    pop.style.maxWidth = width + 'px';
    pop.style.left = Math.max(8, Math.min(r.left, window.innerWidth - width - 8)) + 'px';
    pop.style.top = (r.bottom + 6) + 'px';
    // Gdyby podpowiedź wystawała poza dół ekranu, otwieramy ją nad przyciskiem.
    const h = pop.getBoundingClientRect().height;
    if (r.bottom + 6 + h > window.innerHeight - 8) pop.style.top = Math.max(8, r.top - h - 6) + 'px';
  };
  const hide = () => { pop.hidden = true; pinned = null; };
  const helpButton = (e) => e.target.closest && e.target.closest('button.help');

  document.addEventListener('mouseover', (e) => {
    const button = helpButton(e);
    if (button && !pinned) show(button);
  });
  document.addEventListener('mouseout', (e) => {
    if (helpButton(e) && !pinned) pop.hidden = true;
  });
  document.addEventListener('click', (e) => {
    const button = helpButton(e);
    if (!button) { if (!pop.contains(e.target)) hide(); return; }
    if (pinned === button) { hide(); return; }
    pinned = button;
    show(button);
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') hide(); });
}

// ---- Suwak zasięgu klienta: logarytmiczny, 0,3–20 km ----
// Pozycja x ∈ [0, 100] → km = 0,3 · (20/0,3)^(x/100); dzięki temu małe zasięgi mają tyle samo miejsca co duże.
// Dolna granica 0,3 km: dane o mieszkańcach mają rozdzielczość ok. 300 m (komórka H3 res 9), mniejszy zasięg nic nie wnosi.
const KM_MIN = 0.3;
const KM_MAX = 20;
export const MIN_REACH_NOTE = 'Dane o mieszkańcach mają rozdzielczość ok. 300 m — mniejszy zasięg nie dodaje informacji.';
const sliderToKm = (x) => KM_MIN * Math.pow(KM_MAX / KM_MIN, x / 100);
const kmToSlider = (km) => Math.round(100 * Math.log(km / KM_MIN) / Math.log(KM_MAX / KM_MIN));

// Wyświetlana (i wysyłana do serwera) wartość: poniżej 2 km co 0,1, od 2 km co 0,5.
export function roundKm(km) {
  const rounded = km < 2 ? Math.round(km * 10) / 10 : Math.round(km * 2) / 2;
  return Math.min(KM_MAX, Math.max(KM_MIN, rounded));
}

export const reachKm = () => roundKm(sliderToKm(Number($('reach-input').value)));

function showReach() {
  $('reach-value').textContent = fmt(reachKm(), 1);
}

// Ustawia zasięg; zwraca true, gdy żądana wartość była poniżej minimum (np. stary link z 0,1 km) i została podniesiona.
function setReach(km) {
  const wanted = Number(km);
  $('reach-input').value = kmToSlider(Math.min(KM_MAX, Math.max(KM_MIN, wanted)));
  showReach();
  return wanted < KM_MIN;
}

// ---- Promień obszaru: 1–30 km ----
export const radiusKm = () => Math.min(30, Math.max(1, Math.round(Number($('radius-input').value)) || 10));

function showRadius() {
  $('radius-value').textContent = String(radiusKm());
}

export function setRadius(km) {
  $('radius-input').value = String(Math.min(30, Math.max(1, Math.round(Number(km)) || 10)));
  showRadius();
}

// ---- Obszar analizy: „Cała Polska” / „Wybrane miejsce” ----

export const currentMode = () => (document.querySelector('input[name=mode]:checked') || { value: 'pl' }).value;

// Ustawia tryb: w „Cała Polska” znikają miejsce, promień i przycisk „Pokaż mapę” (mgła pojawia się sama).
export function setMode(mode) {
  const place = mode === 'place';
  const radio = [...document.querySelectorAll('input[name=mode]')].find((r) => r.value === mode);
  if (radio) radio.checked = true;
  $('place-controls').hidden = !place;
  $('show-button').hidden = !place;
  $('intro-pl').hidden = place;
  $('intro-place').hidden = !place;
  if (place) setReachLocked(false);
}

export const onModeChange = (cb) => document.querySelectorAll('input[name=mode]')
  .forEach((r) => r.addEventListener('change', () => r.checked && cb(r.value)));

// Zasięg i okres pozwoleń są zablokowane, gdy widać gotową mapę Polski (liczoną dla typowego zasięgu i 24 miesięcy),
// a odblokowane przy mapie na żywo.
export function setReachLocked(locked) {
  $('reach-input').disabled = locked;
  $('months-select').disabled = locked;
  $('reach-hint').hidden = !locked;
}

// ---- Formularz ----

const NONE = '— nie wybieraj —';

function currentType() {
  if (!catalog) return null;   // katalog jeszcze się nie wczytał
  return typeById($('type-select').value);
}

export function typeById(id) {
  if (!catalog) return null;
  for (const group of catalog.groups) {
    const type = group.types.find((t) => t.id === id);
    if (type) return type;
  }
  return null;
}

export const demandById = (id) => (catalog && catalog.demands.find((d) => d.id === id)) || null;

export function currentDemand() {
  return catalog ? demandById($('demand-select').value) : null;
}

// Przy popycie z pozwoleń „klientami” są nowe budowy, nie ludzie — inaczej podpis wprowadzałby w błąd.
export const clientsNoun = (permits) => (permits ? 'nowych budów' : 'klientów');

function syncMonthsRow() {
  const demand = currentDemand();
  $('months-row').hidden = !(demand && demand.needs_months);
}

// Dopisek „(sugerowane)” przy czynnikach popytu zalecanych dla typu.
function markSuggested(type) {
  const suggested = new Set(type.suggested_demands);
  for (const option of $('demand-select').options) {
    if (!option.value) continue;
    const demand = catalog.demands.find((d) => d.id === option.value);
    option.textContent = demand.name + (suggested.has(demand.id) ? ' (sugerowane)' : '');
  }
}

// Po zmianie typu: czynniki sugerowane dla typu dostają dopisek, domyślny jest zaznaczony,
// a suwak „zasięg klienta” wraca do wartości typowej dla branży. Brak typu niczego nie zmienia.
function onTypeChange() {
  const type = currentType();
  if (!type) return;
  markSuggested(type);
  $('demand-select').value = type.default_demand;
  setReach(type.bandwidth_km);
  syncMonthsRow();
}

// onChange: wywoływane po każdej zmianie formularza, która wymaga nowego zapytania (suwaki: dopiero po puszczeniu).
export function renderCatalog(data, onChange) {
  catalog = data;
  const typeSelect = $('type-select');
  typeSelect.innerHTML = '';
  typeSelect.append(new Option(NONE, ''));
  for (const group of catalog.groups) {
    const optgroup = document.createElement('optgroup');
    optgroup.label = group.name;
    for (const type of group.types) optgroup.append(new Option(type.name, type.id));
    typeSelect.append(optgroup);
  }
  const demandSelect = $('demand-select');
  demandSelect.innerHTML = '';
  demandSelect.append(new Option(NONE, ''));
  for (const demand of catalog.demands) demandSelect.append(new Option(demand.name, demand.id));
  $('months-select').value = String(catalog.default_months);

  typeSelect.addEventListener('change', () => { onTypeChange(); syncLayers(); onChange(); });
  demandSelect.addEventListener('change', () => { syncMonthsRow(); syncLayers(); onChange(); });
  $('months-select').addEventListener('change', onChange);
  // Przy przeciąganiu suwaków tylko aktualizujemy podpis; zapytanie idzie po puszczeniu (zdarzenie change).
  $('reach-input').addEventListener('input', showReach);
  $('reach-input').addEventListener('change', onChange);
  $('radius-input').addEventListener('input', showRadius);
  $('radius-input').addEventListener('change', onChange);
  setReach(1.5);
  setRadius(10);
  syncMonthsRow();
  syncLayers();
}

// Parametry formularza; puste = brak wyboru (backend wymaga co najmniej jednego z: type, demand).
export function selectedParams() {
  const demand = currentDemand();
  const params = {
    type: $('type-select').value,
    demand: demand ? demand.id : '',
    reach_km: reachKm(),
    radius_km: radiusKm(),
  };
  if (demand && demand.needs_months) params.months = $('months-select').value;
  return params;
}

const hasOption = (select, value) => [...select.options].some((o) => o.value === value);

// Ustawia formularz z wartości zapisanych w adresie; nieznane wartości (np. ze starego linku) pomijamy.
// Zwraca true, gdy zasięg z linku był poniżej minimum 0,3 km (został podniesiony — trzeba o tym powiedzieć).
export function setSelection({ type, demand, reach, months, radius }) {
  $('type-select').value = type && hasOption($('type-select'), type) ? type : '';
  if ($('type-select').value) markSuggested(currentType());   // dopiski „sugerowane”, ale bez nadpisywania zapisanych wartości
  $('demand-select').value = demand && hasOption($('demand-select'), demand) ? demand : '';
  const clamped = reach ? setReach(reach) : false;
  if (radius) setRadius(radius);
  if (months) $('months-select').value = String(months);
  syncMonthsRow();
  syncLayers();
  return clamped;
}

// Nazwa wybranego miejsca: podpis pod wyszukiwarką — z wyszukiwarki albo „punkt na mapie”.
export function setPlaceName(name) {
  $('place-hint').textContent = name ? `Wybrane: ${name}` : 'albo kliknij mapę';
}

export const hideIntro = () => { $('intro').hidden = true; };
export const showIntro = () => { $('intro').hidden = false; };
export const onShowClick = (cb) => $('show-button').addEventListener('click', cb);
// Wyróżnienie przycisku „Pokaż mapę”, gdy wskazano nowe miejsce, a mapa jeszcze pokazuje stare.
export const highlightShow = (on) => $('show-button').classList.toggle('attention', on);

// ---- Warstwy mapy: wybór w lewym panelu (radio), tylko dostępne dla bieżących ustawień ----
// typ + klienci → „Gdzie otworzyć”, „Gdzie są klienci”; sam popyt → „Gdzie są klienci”; sama branża → „Gdzie są {firmy}”;
// popyt z pozwoleń dodatkowo → „Gdzie budowy przybywa” (trend).

export function availableLayers() {
  const type = currentType();
  const demand = currentDemand();
  const layers = type && demand ? ['open', 'demand'] : demand ? ['demand'] : type ? ['competition'] : [];
  if (demand && demand.source === 'permits') layers.push('trend');
  return layers;
}

function layerText(layer) {
  const type = currentType();
  return { open: 'Gdzie otworzyć', demand: 'Gdzie są klienci', trend: 'Gdzie budowy przybywa',
    competition: `Gdzie są ${type ? type.plural : 'firmy'}` }[layer];
}

let onLayerChangeCb = null;
export const onLayerChange = (cb) => { onLayerChangeCb = cb; };

// Przebudowuje listę radio zgodnie z ustawieniami; zachowuje zaznaczenie, jeśli warstwa nadal jest dostępna.
export function syncLayers() {
  const box = $('layer-options');
  const layers = availableLayers();
  const keep = document.querySelector('input[name=layer]:checked');
  const wanted = keep && layers.includes(keep.value) ? keep.value : layers[0];
  box.replaceChildren();
  if (!layers.length) {
    const p = document.createElement('p');
    p.className = 'muted';
    p.textContent = 'Najpierw wybierz branżę lub klientów.';
    box.append(p);
    return;
  }
  for (const layer of layers) {
    const row = document.createElement('div');
    row.className = 'layer-row';
    const label = document.createElement('label');
    const input = document.createElement('input');
    input.type = 'radio';
    input.name = 'layer';
    input.value = layer;
    input.checked = layer === wanted;
    input.addEventListener('change', () => onLayerChangeCb && onLayerChangeCb(layer));
    label.append(input, ` ${layerText(layer)}`);
    const help = document.createElement('button');
    help.type = 'button';
    help.className = 'help';
    help.dataset.help = layer;
    help.setAttribute('aria-label', `Co to znaczy: ${layerText(layer)}?`);
    help.textContent = '?';
    row.append(label, help);
    box.append(row);
  }
}

export function currentLayer() {
  const checked = document.querySelector('input[name=layer]:checked');
  return checked ? checked.value : 'open';
}

// Nazwa warstwy z linku bywa dowolnym tekstem — szukamy jej wśród dostępnych radio, zamiast wstawiać do selektora.
export function selectLayer(name) {
  const el = [...document.querySelectorAll('input[name=layer]')].find((input) => input.value === name);
  if (el) el.checked = true;
}

// Tytuł legendy zależny od warstwy (spec v3 §2 pkt 5).
export function legendTitle(layer, typeId, demandId) {
  const demand = demandById(demandId);
  const type = typeById(typeId);
  if (layer === 'open') return 'Szacowana liczba Twoich klientów';
  if (layer === 'demand') return `Dostępni klienci: ${demand ? demand.name.toLowerCase() : ''}`;
  if (layer === 'trend') return 'Zmiana liczby nowych budów';
  return `Zagęszczenie: ${type ? type.name : ''}`;
}

// ---- Prawy panel ----

export function showInsights() {
  $('insights').hidden = false;
  document.querySelector('#tabs [data-tab=insights]').disabled = false;
}

// ---- Legenda: pionowy pasek gradientu w skali logarytmicznej z podpisami „okrągłych” wartości (1–2–5 × 10^n) ----

// Liczba miejsc po przecinku zależnie od wielkości (0,37 → „0,37”, 4,2 → „4,2”, 130 → „130”).
const legendDigits = (v) => (v < 1 ? 2 : v < 10 ? 1 : 0);
// Końce skali to percentyle — podajemy je z dokładnością do 2 cyfr, żeby nie sugerować fałszywej precyzji.
const twoDigits = (v) => Number(v.toPrecision(2));

function legendHtml(title, bar, rows, note, gapHint = false) {
  const el = $('legend');
  el.innerHTML = '<div class="legend-title"><b></b> <button type="button" class="help" data-help="legend" aria-label="Jak czytać kolory?">?</button></div>' +
    `<div class="legend-body"><div class="bar" style="background:${bar}"></div><div class="stops">${rows}</div></div>` +
    (gapHint ? '<div class="legend-gap"><span class="hatch"></span> mało danych o firmach <button type="button" class="help" data-help="gaps" aria-label="Co oznacza kreskowanie?">?</button></div>' : '') +
    (note ? '<div class="note"></div>' : '');
  el.querySelector('b').textContent = title;   // tytuł zawiera nazwy z katalogu — wstawiamy jako tekst
  if (note) el.querySelector('.note').textContent = note;
  el.hidden = false;
}

const stopRow = (t, text) =>
  `<div class="stop" style="bottom:${(t * 100).toFixed(1)}%"><span class="tick"></span>${text}</div>`;

// scale: { lo, hi } z logScale() — wartości, przy których kolor jest najjaśniejszy / najciemniejszy.
export function renderLegend(title, scale, note = '', gapHint = false) {
  if (!scale) { $('legend').hidden = true; return; }
  const label = (prefix, v) => `${prefix}${fmt(v, legendDigits(v))}`;
  const stops = [{ t: 1, text: label('≥ ', twoDigits(scale.hi)) }, { t: 0, text: label('≤ ', twoDigits(scale.lo)) }];
  if (scale.hi > scale.lo) {
    // Na telefonie pasek jest niski: mniej podpisów i większy odstęp od końców, żeby się nie zlewały.
    const narrow = window.innerWidth < 768;
    for (const tick of niceLogTicks(scale, narrow ? 2 : 5, narrow ? 0.2 : 0.1)) stops.push({ t: tick.t, text: label('', tick.v) });
  }
  legendHtml(title, fogGradientCss('to top'), stops.map((s) => stopRow(s.t, s.text)).join(''), note, gapHint);
}

// Legenda trendu: paleta rozbieżna, podpisy słowne zamiast liczb (wartości to ważone odległością przyrosty pozwoleń).
export function renderTrendLegend(title, note = '') {
  const rows = [stopRow(1, 'więcej budów'), stopRow(0.5, 'bez zmian'), stopRow(0, 'mniej budów')].join('');
  legendHtml(title, trendGradientCss('to top'), rows, note);
}

export function hideLegend() { $('legend').hidden = true; }

// ---- Komunikaty, ostrzeżenia, notatki ----

function renderParagraphs(id, list) {
  const el = $(id);
  el.replaceChildren(...list.map((w) => {
    const p = document.createElement('p');
    p.textContent = w;   // textContent: komunikaty traktujemy jako zwykły tekst, nie HTML
    return p;
  }));
  el.hidden = list.length === 0;
}

export const renderWarnings = (list) => renderParagraphs('warnings', list);
export const renderNotes = (list) => renderParagraphs('notes', list);

export function showError(message) {
  const el = $('error');
  el.textContent = message || '';
  el.hidden = !message;
}

// Spokojny komunikat informacyjny (nie błąd), np. „Wybierz miejsce…”.
export function showInfo(message) {
  const el = $('info');
  el.textContent = message || '';
  el.hidden = !message;
}

export function setLoading(loading) {
  $('loading-bar').hidden = !loading;
}

// ---- Podsumowanie obszaru ----

// Szacunek do setek (od 1000), do dziesiątek (od 100), inaczej do jedności — nie pokazujemy fałszywej precyzji.
const roundEstimate = (n) => (n >= 1000 ? Math.round(n / 100) * 100 : n >= 100 ? Math.round(n / 10) * 10 : Math.round(n));

const VERDICTS = {
  less: 'Konkurencji jest tu mniej niż przeciętnie w Polsce.',
  more: 'Konkurencji jest tu więcej niż przeciętnie w Polsce.',
  similar: 'Konkurencja na poziomie średniej krajowej.',
  unknown: 'Nie da się ocenić konkurencji — za mało danych o firmach.',
};

// summary z /api/surface; ctx: { placeName, demandId, permitsPeriod }. Pokazujemy tylko wiersze, które mają sens
// dla wybranych ustawień (sam popyt: bez firm i porównania; sama branża: bez klientów).
export function renderSummary(summary, ctx) {
  const box = $('summary');
  box.replaceChildren();
  const add = (text, className = '') => {
    const row = document.createElement('div');
    row.className = `row ${className}`.trim();
    row.textContent = text;
    box.append(row);
    return row;
  };
  const demand = demandById(ctx.demandId);
  add(summary.shape === 'view' ? 'Widoczny obszar (to, co jest teraz na mapie)' : `Obszar: ${ctx.placeName}, promień ${fmt(summary.radius_km, 1)} km`, 'where');
  if (summary.demand_total != null && demand) {
    const permits = ctx.permitsPeriod;
    add(permits
      ? `${demand.name}: ${fmt(summary.demand_total)} (pozwolenia ${permits.from} – ${permits.to})`
      : `${demand.name}: ok. ${fmt(roundEstimate(summary.demand_total))}`);
  }
  if (summary.competitors) {
    const c = summary.competitors;
    add(`${capitalize(summary.type_plural)} w obszarze: ${fmt(c.total)} (OSM ${fmt(c.osm)}, Overture ${fmt(c.overture)})`);
  }
  if (summary.competitors && summary.demand_total != null) {
    add(summary.per_firm != null
      ? `→ 1 firma na ok. ${fmt(roundEstimate(summary.per_firm))} ${summary.demand_genitive}`
      : '→ brak firm tego typu w obszarze', 'strong');
    if (summary.national_per_firm != null) add(`Średnio w Polsce: 1 na ok. ${fmt(roundEstimate(summary.national_per_firm))}`);
    if (summary.verdict) add(VERDICTS[summary.verdict], `verdict ${summary.verdict}`);
  }
  if (summary.data_gap) {
    add(`⚠ Mało danych o firmach: ${summary.type_plural} w obszarze mamy w danych ${fmt(summary.competitors.total)}, ` +
      `a przy tej liczbie mieszkańców średnio w Polsce byłoby ok. ${fmt(Math.round(summary.expected_firms))}. ` +
      'Prawdopodobnie część firm nie jest jeszcze na mapach — sprawdź na miejscu.', 'warn');
  }
  $('summary-box').hidden = false;
}

export const hideSummary = () => { $('summary-box').hidden = true; };

// ---- Najlepsze miejsca ----

const TOP_TITLES = { open: 'Najlepsze miejsca', demand: 'Najwięcej klientów', competition: 'Najwięcej firm', trend: 'Gdzie przybywa budów' };

export function renderTop(list, layer, permits, onClick, inView = false) {
  $('top-title').textContent = inView && layer === 'open' ? 'Najlepsze miejsca w widoku' : (TOP_TITLES[layer] || TOP_TITLES.open);
  $('top-title').hidden = false;
  const ol = $('top-list');
  ol.innerHTML = '';
  if (!list.length) {
    ol.innerHTML = '<li class="muted">Brak danych w tym obszarze.</li>';
    return;
  }
  list.forEach((place, i) => {
    const li = document.createElement('li');
    const label = layer === 'open' ? `ok. ${fmt(roundEstimate(place.value))} ${clientsNoun(permits)}`
      : layer === 'demand' ? `${fmt(roundEstimate(place.value))} ${permits ? 'nowych budów' : 'dostępnych klientów'}`
        : layer === 'trend' ? `przyrost ok. ${fmt(roundEstimate(place.value))} budów`
          : `zagęszczenie ${fmt(place.value, 1)}`;
    li.textContent = `${place.name} — ${label}`;
    li.addEventListener('click', () => onClick(place, i));
    ol.append(li);
  });
}

// ---- Dymek klikniętego punktu (dokładne liczby z /api/point, spec v3 §4) ----

const km = (r) => fmt(r, 1);
const dist = (m) => (m >= 1000 ? `${fmt(m / 1000, 1)} km` : `${fmt(m)} m`);

// Zwraca element DOM (tekst wstawiamy przez textContent — nazwy firm nie są HTML-em).
// onSetCenter: wywoływane po kliknięciu przycisku pod dymkiem (podpis: actionLabel).
export function pointPopup(d, onSetCenter, actionLabel = 'Ustaw tu środek obszaru') {
  const box = document.createElement('div');
  const add = (text, bold = false) => {
    const p = document.createElement('div');
    if (bold) p.className = 'strong';
    p.textContent = text;
    box.append(p);
    return p;
  };
  const permits = d.permits_period != null;
  add(`W promieniu ${km(d.radius_km)} km:`, true);
  if (d.demand != null) {
    add(permits
      ? `${d.demand_name}: ${fmt(d.demand)} (pozwolenia ${d.permits_period.from} – ${d.permits_period.to})`
      : `${d.demand_name}: ok. ${fmt(roundEstimate(d.demand))} (szacunek)`);
  }
  if (d.competitors != null) add(`${d.type_name} w okolicy: ${fmt(d.competitors)}`);
  if (d.expected != null) {
    add(`Otwierając tu, zdobyłbyś ok. ${fmt(roundEstimate(d.expected))} ${clientsNoun(permits)} (model Huffa).`, true);
  }
  if (d.data_gap && d.data_gap.warn) {
    const g = d.data_gap;
    add(`⚠ Mało danych o firmach: ${d.type_plural} w promieniu ${fmt(g.radius_km)} km mamy w danych ${fmt(g.observed)}, ` +
      `a przy tej liczbie mieszkańców średnio w Polsce byłoby ok. ${fmt(Math.round(g.expected))}. ` +
      'Prawdopodobnie część firm nie jest jeszcze na mapach — sprawdź na miejscu.').className = 'warn';
  }
  if (d.nearest.length) {
    add('Najbliżsi:');
    const ul = document.createElement('ul');
    for (const n of d.nearest) {
      const li = document.createElement('li');
      li.textContent = `${n.name} — ${dist(n.distance_m)} (${SOURCE_NAMES[n.source] || 'OpenStreetMap'})`;
      ul.append(li);
    }
    box.append(ul);
  }
  for (const note of d.notes || []) add(note).className = 'note';
  if (onSetCenter) {
    const link = document.createElement('button');
    link.type = 'button';
    link.className = 'link-button';
    link.textContent = actionLabel;
    link.addEventListener('click', onSetCenter);
    box.append(link);
  }
  return box;
}

// ---- Wyszukiwarka adresów: podpowiedzi z opóźnieniem 400 ms, obsługa klawiatury ----

export function initSearch(onPick) {
  const input = $('search-input');
  const list = $('search-results');
  let results = [];
  let active = -1;
  let timer = null;
  let request = 0;

  const hide = () => { list.hidden = true; active = -1; };
  const highlight = () => [...list.children].forEach((li, i) => li.classList.toggle('active', i === active));
  const pick = (place) => {
    input.value = place.name;
    hide();
    onPick(place);
  };
  const show = (items) => {
    results = items;
    list.replaceChildren(...items.map((place) => {
      const li = document.createElement('li');
      li.textContent = place.name;
      li.addEventListener('mousedown', (e) => { e.preventDefault(); pick(place); });
      return li;
    }));
    if (!items.length) {
      const li = document.createElement('li');
      li.className = 'muted';
      li.textContent = 'Brak wyników';
      list.replaceChildren(li);
    }
    list.hidden = false;
    active = -1;
  };

  input.addEventListener('input', () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 3) { hide(); return; }
    timer = setTimeout(async () => {
      const mine = ++request;
      try {
        const items = await geocode(q);
        if (mine === request) show(items);
      } catch (e) {
        if (mine === request) showError(e.message);
      }
    }, 400);
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { hide(); return; }
    if (list.hidden || !results.length) return;
    if (e.key === 'ArrowDown') { active = Math.min(active + 1, results.length - 1); highlight(); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { active = Math.max(active - 1, 0); highlight(); e.preventDefault(); }
    else if (e.key === 'Enter') { pick(results[Math.max(active, 0)]); e.preventDefault(); }
  });
  input.addEventListener('blur', hide);
}

// ---- Źródła danych (stopka prawego panelu): świeżość danych ----

export function renderFooter(meta) {
  const find = (source) => meta.sources.find((x) => x.source === source);
  const date = (source) => (find(source) ? new Date(find(source).downloaded_at).toLocaleDateString('pl-PL') : null);
  const parts = [];
  if (date('osm')) parts.push(`OpenStreetMap ${date('osm')}`);
  const overture = find('overture');
  if (overture) {
    const release = (overture.url.match(/release\/([^/]+)\//) || [])[1];
    parts.push(`Overture Maps${release ? ` ${release}` : ''}`);
  }
  if (date('gunb')) parts.push(`GUNB ${date('gunb')}`);
  if (date('census')) parts.push('Spis 2021');
  $('meta-footer').textContent = parts.length ? `Źródła danych: ${parts.join(', ')}. Firmy: © OpenStreetMap contributors, © Overture Maps Foundation.` : '';
}

// ---- Telefon: zakładki arkusza („Ustawienia” / „Wnioski”) ----

export function setTab(tab) {
  document.body.dataset.tab = tab;
  document.body.classList.remove('sheet-collapsed');
  document.querySelectorAll('#tabs button').forEach((b) => b.classList.toggle('active', b.dataset.tab === tab));
}

export const collapseSheet = () => document.body.classList.add('sheet-collapsed');

// Kliknięcie w aktywną zakładkę zwija arkusz, w nieaktywną przełącza; onResize — mapa musi przeliczyć rozmiar.
export function initTabs(onResize) {
  document.querySelectorAll('#tabs button').forEach((button) => button.addEventListener('click', () => {
    const same = document.body.dataset.tab === button.dataset.tab;
    if (same && !document.body.classList.contains('sheet-collapsed')) collapseSheet();
    else setTab(button.dataset.tab);
    onResize();
  }));
}

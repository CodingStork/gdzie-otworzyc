// Panel boczny: formularz (typ, klienci, zasięg, miejsce, promień), pytajniki z wyjaśnieniami, legenda,
// lista najlepszych miejsc i dymek ze szczegółami punktu.
import { geocode } from './api.js';
import { fogGradientCss, niceLogTicks } from './colors.js';

const $ = (id) => document.getElementById(id);

let catalog = null;

// useGrouping: 'always' — domyślnie pl-PL nie grupuje liczb czterocyfrowych (1500), a pięciocyfrowe tak (15 800).
export const fmt = (n, digits = 0) =>
  Number(n).toLocaleString('pl-PL', { maximumFractionDigits: digits, useGrouping: 'always' });

// ---- Wyjaśnienia pod pytajnikami (teksty uzgodnione ze specyfikacją v3 §5 — nie zmieniać bez powodu) ----
const HELP = {
  open: 'Ilu klientów mogłaby przyciągnąć nowa firma w danym miejscu. Liczymy to modelem Huffa: każdy mieszkaniec wybiera między firmami, ' +
    'a bliższa firma przyciąga go mocniej. Uwzględniamy wszystkich konkurentów z OpenStreetMap i »inne możliwości« ' +
    '(firmy, których nie ma w OSM, zakupy gdzie indziej). Najbardziej czerwone miejsca to najlepsze lokalizacje.',
  demand: 'Ilu potencjalnych klientów jest w pobliżu danego miejsca — bliżsi liczą się bardziej. ' +
    'Mieszkańcy to szacunek: spis 2021 rozłożony na budynki mieszkalne z OpenStreetMap. ' +
    'Dla nowych domów liczymy pozwolenia na budowę z wybranego okresu.',
  competition: 'Gdzie jest najwięcej firm wybranego typu. Dane z OpenStreetMap — mogą być niepełne.',
  reach: 'Jak daleko typowy klient jest gotów dojść lub dojechać. Fryzjer, sklep spożywczy: kilkaset metrów do 2 km; ' +
    'market budowlany, brukarz: 10–20 km. W tej odległości chęć dotarcia spada o ok. 2/3, a dwa razy dalej — o ok. 85%.',
  radius: 'Jak duży obszar wokół wybranego miejsca przeanalizować. Mniejszy obszar = szybciej i dokładniej.',
  legend: 'Kolor w skali logarytmicznej: każdy krok koloru to mniej więcej podwojenie wartości. ' +
    'Przezroczyste miejsca mają bardzo małe wartości. Dokładne liczby zobaczysz po kliknięciu mapy.',
};

// Pytajnik: przycisk .help[data-help]. Podpowiedź pokazuje się po najechaniu lub kliknięciu,
// zamyka ją kliknięcie poza nią albo Escape (klik w pytajnik „przypina” ją na stałe).
// Zdarzenia obsługujemy delegacją z dokumentu, więc działa też dla pytajnika w legendzie, rysowanej dynamicznie.
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

// ---- Suwak zasięgu klienta: logarytmiczny, 0,1–20 km ----
// Pozycja x ∈ [0, 100] → km = 0,1 · 200^(x/100); dzięki temu małe zasięgi (0,1–2 km) mają tyle samo miejsca co duże.
const KM_MIN = 0.1;
const KM_MAX = 20;
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

function setReach(km) {
  $('reach-input').value = kmToSlider(Math.min(KM_MAX, Math.max(KM_MIN, Number(km))));
  showReach();
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

// ---- Formularz ----

const NONE = '— nie wybieraj —';

function currentType() {
  if (!catalog) return null;   // katalog jeszcze się nie wczytał
  for (const group of catalog.groups) {
    const type = group.types.find((t) => t.id === $('type-select').value);
    if (type) return type;
  }
  return null;
}

export const currentTypeInfo = currentType;

export function currentDemand() {
  if (!catalog) return null;
  return catalog.demands.find((d) => d.id === $('demand-select').value) || null;
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

  typeSelect.addEventListener('change', () => { onTypeChange(); onChange(); });
  demandSelect.addEventListener('change', () => { syncMonthsRow(); onChange(); });
  $('months-select').addEventListener('change', onChange);
  // Przy przeciąganiu suwaków tylko aktualizujemy podpis; zapytanie idzie po puszczeniu (zdarzenie change).
  $('reach-input').addEventListener('input', showReach);
  $('reach-input').addEventListener('change', onChange);
  $('radius-input').addEventListener('input', showRadius);
  $('radius-input').addEventListener('change', onChange);
  setReach(1.5);
  setRadius(10);
  syncMonthsRow();
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
export function setSelection({ type, demand, reach, months, radius }) {
  $('type-select').value = type && hasOption($('type-select'), type) ? type : '';
  if ($('type-select').value) markSuggested(currentType());   // dopiski „sugerowane”, ale bez nadpisywania zapisanych wartości
  $('demand-select').value = demand && hasOption($('demand-select'), demand) ? demand : '';
  if (reach) setReach(reach);
  if (radius) setRadius(radius);
  if (months) $('months-select').value = String(months);
  syncMonthsRow();
}

// Wybrane miejsce: podpis pod wyszukiwarką.
export function setPlaceName(name) {
  $('place-hint').textContent = name ? `Wybrane: ${name}` : 'albo kliknij mapę';
}

export const hideIntro = () => { $('intro').hidden = true; };
export const onShowClick = (cb) => $('show-button').addEventListener('click', cb);

// ---- Warstwy mapy ----
// typ + klienci → przełącznik dwóch map („Gdzie otworzyć” / „Gdzie są klienci”); w pozostałych przypadkach jedna mapa
// bez przełącznika, z podpisem („Gdzie są klienci” albo „Gdzie są {firmy}”, np. „Gdzie są fryzjerzy”).
let availableLayers = [];

export function setLayers(layers) {
  availableLayers = layers;
  const two = layers.length === 2;
  $('layer-switch').hidden = !two;
  const title = $('layer-title');
  title.hidden = two;
  if (!two) {
    const type = currentType();
    const text = layers[0] === 'competition' ? `Gdzie są ${type ? type.plural : 'firmy'}` : 'Gdzie są klienci';
    title.innerHTML = '<b></b> <button type="button" class="help" aria-label="Co to znaczy?">?</button>';
    title.querySelector('b').textContent = text;
    title.querySelector('button').dataset.help = layers[0];
  }
  const checked = document.querySelector('input[name=layer]:checked');
  if (two && !layers.includes(checked.value)) document.querySelector('input[name=layer][value="open"]').checked = true;
}

export function currentLayer() {
  if (availableLayers.length === 2) return document.querySelector('input[name=layer]:checked').value;
  return availableLayers[0] || 'open';
}

export function selectLayer(name) {
  const el = document.querySelector(`input[name=layer][value="${name}"]`);
  if (el) el.checked = true;
}

export const showControls = (show) => { $('map-controls').hidden = !show; };

// Tytuł legendy zależny od warstwy (spec §2 pkt 5).
export function legendTitle(layer) {
  const demand = currentDemand();
  const type = currentType();
  if (layer === 'open') return 'Szacowana liczba Twoich klientów';
  if (layer === 'demand') return `Dostępni klienci: ${demand ? demand.name.toLowerCase() : ''}`;
  return `Zagęszczenie: ${type ? type.name : ''}`;
}

// ---- Legenda: pionowy pasek gradientu w skali logarytmicznej z podpisami „okrągłych” wartości (1–2–5 × 10^n) ----

// Liczba miejsc po przecinku zależnie od wielkości (0,37 → „0,37”, 4,2 → „4,2”, 130 → „130”).
const legendDigits = (v) => (v < 1 ? 2 : v < 10 ? 1 : 0);
// Końce skali to percentyle 5 i 99 — podajemy je z dokładnością do 2 cyfr, żeby nie sugerować fałszywej precyzji.
const twoDigits = (v) => Number(v.toPrecision(2));

// scale: { lo, hi } z logScale() — wartości, przy których kolor jest najjaśniejszy / najciemniejszy.
export function renderLegend(title, scale, note = '') {
  const el = $('legend');
  if (!scale) { el.hidden = true; return; }
  const label = (prefix, v) => `${prefix}${fmt(v, legendDigits(v))}`;
  const stops = [{ t: 1, text: label('≥ ', twoDigits(scale.hi)) }, { t: 0, text: label('≤ ', twoDigits(scale.lo)) }];
  if (scale.hi > scale.lo) {
    // Na telefonie pasek jest niski: mniej podpisów i większy odstęp od końców, żeby się nie zlewały.
    const narrow = window.innerWidth < 768;
    for (const tick of niceLogTicks(scale, narrow ? 2 : 5, narrow ? 0.2 : 0.1)) stops.push({ t: tick.t, text: label('', tick.v) });
  }
  const rows = stops.map((s) =>
    `<div class="stop" style="bottom:${(s.t * 100).toFixed(1)}%"><span class="tick"></span>${s.text}</div>`).join('');
  el.innerHTML = '<div class="legend-title"><b></b> <button type="button" class="help" data-help="legend" aria-label="Jak czytać kolory?">?</button></div>' +
    `<div class="legend-body"><div class="bar" style="background:${fogGradientCss('to top')}"></div><div class="stops">${rows}</div></div>` +
    (note ? '<div class="note"></div>' : '');
  el.querySelector('b').textContent = title;   // tytuł zawiera nazwy z katalogu — wstawiamy jako tekst
  if (note) el.querySelector('.note').textContent = note;
  el.hidden = false;
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

// ---- Najlepsze miejsca ----

const TOP_TITLES = { open: 'Najlepsze miejsca', demand: 'Najwięcej klientów', competition: 'Najwięcej firm' };

// Szacunek do setek (od 1000), do dziesiątek (od 100), inaczej do jedności — nie pokazujemy fałszywej precyzji.
const roundEstimate = (n) => (n >= 1000 ? Math.round(n / 100) * 100 : n >= 100 ? Math.round(n / 10) * 10 : Math.round(n));

export function renderTop(list, layer, permits, onClick) {
  $('top-title').textContent = TOP_TITLES[layer] || TOP_TITLES.open;
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
        : `zagęszczenie ${fmt(place.value, 1)}`;
    li.textContent = `${place.name} — ${label}`;
    li.addEventListener('click', () => onClick(place, i));
    ol.append(li);
  });
}

export function clearTop() {
  $('top-title').hidden = true;
  $('top-list').innerHTML = '';
}

// ---- Dymek klikniętego punktu (dokładne liczby z /api/point, spec §4) ----

const km = (r) => fmt(r, 1);
const dist = (m) => (m >= 1000 ? `${fmt(m / 1000, 1)} km` : `${fmt(m)} m`);

// Zwraca element DOM (tekst wstawiamy przez textContent — nazwy firm z OSM nie są HTML-em).
// onSetCenter: wywoływane po kliknięciu „Ustaw tu środek obszaru”.
export function pointPopup(d, onSetCenter) {
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
  if (d.competitors != null) add(`${d.type_name} w OSM: ${fmt(d.competitors)}`);
  if (d.expected != null) {
    add(`Otwierając tu, zdobyłbyś ok. ${fmt(roundEstimate(d.expected))} ${clientsNoun(permits)} (model Huffa).`, true);
  }
  if (d.nearest.length) {
    add('Najbliżsi:');
    const ul = document.createElement('ul');
    for (const n of d.nearest) {
      const li = document.createElement('li');
      li.textContent = `${n.name} — ${dist(n.distance_m)}`;
      ul.append(li);
    }
    box.append(ul);
  }
  for (const note of d.notes || []) add(note).className = 'note';
  if (onSetCenter) {
    const link = document.createElement('button');
    link.type = 'button';
    link.className = 'link-button';
    link.textContent = 'Ustaw tu środek obszaru';
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

// ---- Stopka: świeżość danych ----

export function renderFooter(meta) {
  const date = (source) => {
    const s = meta.sources.find((x) => x.source === source);
    return s ? new Date(s.downloaded_at).toLocaleDateString('pl-PL') : null;
  };
  const parts = [];
  if (date('osm')) parts.push(`OSM ${date('osm')}`);
  if (date('gunb')) parts.push(`GUNB ${date('gunb')}`);
  if (date('census')) parts.push('Spis 2021');
  $('meta-footer').textContent = parts.length ? `Dane: ${parts.join(', ')}` : '';
}

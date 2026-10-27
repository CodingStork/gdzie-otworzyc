// Panel boczny: formularz (typ, popyt, zasięg), pytajniki z wyjaśnieniami, legenda, lista najlepszych miejsc, dymek punktu.
import { geocode } from './api.js';
import { gradientCss } from './colors.js';

const $ = (id) => document.getElementById(id);

let catalog = null;

// useGrouping: 'always' — domyślnie pl-PL nie grupuje liczb czterocyfrowych (1500), a pięciocyfrowe tak (15 800).
export const fmt = (n, digits = 0) =>
  Number(n).toLocaleString('pl-PL', { maximumFractionDigits: digits, useGrouping: 'always' });

// ---- Wyjaśnienia pod pytajnikami (teksty uzgodnione ze specyfikacją — nie zmieniać bez powodu) ----
const HELP = {
  score: 'Ilu potencjalnych klientów przypadnie na jedną firmę, jeśli otworzysz tu swoją: klienci w zasięgu ÷ (konkurenci w zasięgu + 1). ' +
    'Im ciemniejszy kolor, tym lepiej. Porównuj miejsca między sobą — w OpenStreetMap brakuje części firm, więc same liczby są zawyżone.',
  D: 'Ilu potencjalnych klientów jest w zasięgu od danego miejsca, np. mieszkańców w promieniu 1,5 km. ' +
    'Liczba mieszkańców to szacunek: dane ze spisu 2021 (kwadraty 1 km) rozłożone na budynki mieszkalne z OpenStreetMap. ' +
    'Dla nowych domów liczymy pozwolenia na budowę z wybranego okresu.',
  S: 'Ile firm wybranego typu jest w zasięgu od danego miejsca. Dane z OpenStreetMap — mogą być niepełne.',
  range: 'Z jak daleka przychodzą klienci. Fryzjer czy sklep spożywczy: kilkaset metrów do 2 km; market budowlany czy brukarz: 10–20 km. ' +
    'Mały zasięg daje ostrą mapę pokazującą pojedyncze ulice, duży — ogólny obraz okolicy.',
  legend: 'Kolor pokazuje pozycję miejsca w rankingu widocznego obszaru: najjaśniejszy to najniższe wartości, najciemniejszy — najwyższe. ' +
    'Dokładne liczby zobaczysz po kliknięciu mapy.',
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

export const bandwidthKm = () => roundKm(sliderToKm(Number($('bandwidth-input').value)));

function showBandwidth() {
  $('bandwidth-value').textContent = fmt(bandwidthKm(), 1);
}

function setBandwidth(km) {
  $('bandwidth-input').value = kmToSlider(Math.min(KM_MAX, Math.max(KM_MIN, Number(km))));
  showBandwidth();
}

// ---- Formularz ----

const NONE = '— nie wybieraj —';

function currentType() {
  for (const group of catalog.groups) {
    const type = group.types.find((t) => t.id === $('type-select').value);
    if (type) return type;
  }
  return null;
}

function currentDemand() {
  return catalog.demands.find((d) => d.id === $('demand-select').value) || null;
}

function syncMonthsRow() {
  const demand = currentDemand();
  $('months-row').hidden = !(demand && demand.needs_months);
}

// Po zmianie typu: czynniki sugerowane dla typu dostają dopisek, domyślny jest zaznaczony,
// a suwak „zasięg klienta” wraca do wartości typowej dla branży. Brak typu niczego nie zmienia.
function onTypeChange() {
  const type = currentType();
  if (!type) return;
  const suggested = new Set(type.suggested_demands);
  for (const option of $('demand-select').options) {
    if (!option.value) continue;
    const demand = catalog.demands.find((d) => d.id === option.value);
    option.textContent = demand.name + (suggested.has(demand.id) ? ' (sugerowane)' : '');
  }
  $('demand-select').value = type.default_demand;
  setBandwidth(type.bandwidth_km);
  syncMonthsRow();
}

// onChange: wywoływane po każdej zmianie formularza, która wymaga nowego zapytania (suwak: dopiero po puszczeniu).
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
  // Przy przeciąganiu suwaka tylko aktualizujemy podpis; zapytanie idzie po puszczeniu (zdarzenie change).
  $('bandwidth-input').addEventListener('input', showBandwidth);
  $('bandwidth-input').addEventListener('change', onChange);
  setBandwidth(1.5);
  syncMonthsRow();
}

// Parametry formularza; puste = brak wyboru (backend wymaga co najmniej jednego z: type, demand).
export function selectedParams() {
  const demand = currentDemand();
  const params = {
    type: $('type-select').value,
    demand: demand ? demand.id : '',
    bandwidth_km: bandwidthKm(),
  };
  if (demand && demand.needs_months) params.months = $('months-select').value;
  return params;
}

const hasOption = (select, value) => [...select.options].some((o) => o.value === value);

// Ustawia formularz z wartości zapisanych w adresie; nieznane wartości (np. ze starego linku) pomijamy.
export function setSelection({ type, demand, bandwidth, months }) {
  $('type-select').value = type && hasOption($('type-select'), type) ? type : '';
  if (type && $('type-select').value) {
    // jak po zmianie typu (dopiski „sugerowane”), ale bez nadpisywania zapisanych wartości poniżej
    const t = currentType();
    const suggested = new Set(t.suggested_demands);
    for (const option of $('demand-select').options) {
      if (!option.value) continue;
      const d = catalog.demands.find((x) => x.id === option.value);
      option.textContent = d.name + (suggested.has(d.id) ? ' (sugerowane)' : '');
    }
  }
  $('demand-select').value = demand && hasOption($('demand-select'), demand) ? demand : '';
  if (bandwidth) setBandwidth(bandwidth);
  if (months) $('months-select').value = String(months);
  syncMonthsRow();
}

// ---- Warstwy mapy ----

// Tryb wyniku decyduje, które warstwy mają sens: tylko typ → Konkurencja, tylko popyt → Popyt.
// Niedostępne przyciski są wyłączone; jeśli wybrana warstwa jest niedostępna, przełączamy na dostępną.
const MODE_LAYERS = { full: ['score', 'D', 'S'], demand: ['D'], competition: ['S'] };

export function setLayerAvailability(mode) {
  const allowed = MODE_LAYERS[mode] || MODE_LAYERS.full;
  document.querySelectorAll('input[name=layer]').forEach((el) => {
    el.disabled = !allowed.includes(el.value);
    el.closest('label').classList.toggle('disabled', el.disabled);
  });
  const checked = document.querySelector('input[name=layer]:checked');
  if (!allowed.includes(checked.value)) {
    document.querySelector(`input[name=layer][value="${allowed[0]}"]`).checked = true;
  }
}

export function currentLayer() {
  return document.querySelector('input[name=layer]:checked').value;
}

// ---- Legenda: pionowy pasek gradientu z podpisami (min, 25%, mediana, 75%, 90%, max) ----

const LEGEND_STOPS = [
  { p: 100, label: 'maks.' }, { p: 90, label: '90%' }, { p: 75, label: '75%' },
  { p: 50, label: 'mediana' }, { p: 25, label: '25%' }, { p: 0, label: 'min.' },
];

// values: legend[m] z API = wartości dla percentyli [0, 25, 50, 75, 90, 100].
export function renderLegend(title, values, note = '') {
  const el = $('legend');
  if (!values || !values.length) { el.hidden = true; return; }
  const digits = (v) => (Math.abs(v) < 10 ? 1 : 0);
  const rows = LEGEND_STOPS.map((s) => {
    const v = values[[0, 25, 50, 75, 90, 100].indexOf(s.p)];
    return `<div class="stop" style="bottom:${s.p}%"><span class="tick"></span>${fmt(v, digits(v))} <small>${s.label}</small></div>`;
  }).join('');
  el.innerHTML = `<div class="legend-title"><b>${title}</b> <button type="button" class="help" data-help="legend" aria-label="Jak czytać kolory?">?</button></div>` +
    `<div class="legend-body"><div class="bar" style="background:${gradientCss('to top')}"></div><div class="stops">${rows}</div></div>` +
    (note ? `<div class="note"></div>` : '');
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

// Spokojny komunikat informacyjny (nie błąd), np. „Wybierz typ działalności albo czynnik popytu”.
export function showInfo(message) {
  const el = $('info');
  el.textContent = message || '';
  el.hidden = !message;
}

export function setLoading(loading) {
  $('loading-bar').hidden = !loading;
}

// ---- Najlepsze miejsca ----

const TOP_TITLES = { score: 'Najlepsze miejsca', D: 'Największy popyt', S: 'Najwięcej firm' };

export function renderTop(list, metric, onClick) {
  $('top-title').textContent = TOP_TITLES[metric] || TOP_TITLES.score;
  const ol = $('top-list');
  ol.innerHTML = '';
  if (!list.length) {
    ol.innerHTML = '<li class="muted">Brak danych w tym obszarze.</li>';
    return;
  }
  list.forEach((place, i) => {
    const li = document.createElement('li');
    const label = metric === 'S' ? `${fmt(place.value, 1)} firm w zasięgu`
      : metric === 'D' ? `${fmt(place.value)} w zasięgu` : `${fmt(place.value)} klientów na firmę`;
    li.textContent = `${place.name} — ${label}`;
    li.addEventListener('click', () => onClick(place, i));
    ol.append(li);
  });
}

// ---- Dymek klikniętego punktu (dokładne liczby z /api/point) ----

const km = (r) => fmt(r, 1);
const dist = (m) => (m >= 1000 ? `${fmt(m / 1000, 1)} km` : `${fmt(m)} m`);

// Szacunek ludności: do setek, a dla małych liczb do dziesiątek (zaokrąglenie do 100 pokazałoby „ok. 0”).
const roundEstimate = (n) => (n >= 1000 ? Math.round(n / 100) * 100 : Math.round(n / 10) * 10);

// Zwraca element DOM (tekst wstawiamy przez textContent — nazwy firm z OSM nie są HTML-em).
export function pointPopup(d) {
  const box = document.createElement('div');
  const add = (text, bold = false) => {
    const p = document.createElement('div');
    if (bold) p.className = 'strong';
    p.textContent = text;
    box.append(p);
    return p;
  };
  add(`W promieniu ${km(d.radius_km)} km:`, true);
  if (d.demand != null) {
    const permits = d.permits_period != null;
    add(permits
      ? `${d.demand_name}: ${fmt(d.demand)} (pozwolenia ${d.permits_period.from} – ${d.permits_period.to})`
      : `${d.demand_name}: ok. ${fmt(roundEstimate(d.demand))} (szacunek)`);
  }
  if (d.competitors != null) add(`${d.type_name} w OpenStreetMap: ${fmt(d.competitors)}`);
  if (d.score != null) add(`→ ok. ${fmt(d.score)} klientów na firmę po otwarciu Twojej`, true);
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

// Panel boczny: wypełnianie formularza danymi z katalogu i wyświetlanie wyników.
import { classColors } from './colors.js';

const $ = (id) => document.getElementById(id);

let catalog = null;

export const fmt = (n, digits = 0) => Number(n).toLocaleString('pl-PL', { maximumFractionDigits: digits });
// Granice klas w legendzie: mało miejsc po przecinku dla dużych liczb, więcej dla małych.
const fmtBreak = (n) => fmt(n, Math.abs(n) < 10 ? 1 : 0);

function currentType() {
  for (const group of catalog.groups) {
    const type = group.types.find((t) => t.id === $('type-select').value);
    if (type) return type;
  }
  return null;
}

function currentDemand() {
  return catalog.demands.find((d) => d.id === $('demand-select').value);
}

function syncMonthsRow() {
  $('months-row').hidden = !currentDemand().needs_months;
}

function setBandwidth(km) {
  $('bandwidth-input').value = km;
  $('bandwidth-value').textContent = fmt(km, 1);
}

// Po zmianie typu: czynniki sugerowane dla typu dostają dopisek, domyślny jest zaznaczony,
// a suwak „zasięg klienta” wraca do wartości typowej dla branży.
function onTypeChange() {
  const type = currentType();
  const suggested = new Set(type.suggested_demands);
  for (const option of $('demand-select').options) {
    const demand = catalog.demands.find((d) => d.id === option.value);
    option.textContent = demand.name + (suggested.has(demand.id) ? ' (sugerowane)' : '');
  }
  $('demand-select').value = type.default_demand;
  setBandwidth(type.bandwidth_km);
  syncMonthsRow();
}

export function renderCatalog(data) {
  catalog = data;
  const typeSelect = $('type-select');
  typeSelect.innerHTML = '';
  for (const group of catalog.groups) {
    const optgroup = document.createElement('optgroup');
    optgroup.label = group.name;
    for (const type of group.types) optgroup.append(new Option(type.name, type.id));
    typeSelect.append(optgroup);
  }
  const demandSelect = $('demand-select');
  demandSelect.innerHTML = '';
  for (const demand of catalog.demands) demandSelect.append(new Option(demand.name, demand.id));
  $('months-select').value = String(catalog.default_months);

  typeSelect.addEventListener('change', onTypeChange);
  demandSelect.addEventListener('change', syncMonthsRow);
  $('bandwidth-input').addEventListener('input', () => {
    $('bandwidth-value').textContent = fmt($('bandwidth-input').value, 1);
  });
  onTypeChange();
}

// Parametry formularza (bez położenia — to trzyma app.js).
export function selectedParams() {
  const demand = currentDemand();
  const params = {
    type: $('type-select').value,
    demand: demand.id,
    radius_km: $('radius-input').value,
    bandwidth_km: $('bandwidth-input').value,
  };
  if (demand.needs_months) params.months = $('months-select').value;
  return params;
}

export function setSelection({ type, demand, bandwidth, months }) {
  if (type) { $('type-select').value = type; onTypeChange(); }
  if (demand) { $('demand-select').value = demand; syncMonthsRow(); }
  if (bandwidth) setBandwidth(bandwidth);
  if (months) $('months-select').value = String(months);
}

// Legenda: kolor + przedział wartości dla każdej z klas kwantylowych.
export function renderLegend(title, breaks, note = '') {
  const el = $('legend');
  if (!breaks.length) { el.hidden = true; return; }
  const colors = classColors(breaks);
  const labels = colors.map((_, i) => {
    if (i === 0) return `< ${fmtBreak(breaks[0])}`;
    if (i === colors.length - 1) return `≥ ${fmtBreak(breaks[i - 1])}`;
    return `${fmtBreak(breaks[i - 1])} – ${fmtBreak(breaks[i])}`;
  });
  el.innerHTML = `<b>${title}</b>` + colors.map((c, i) =>
    `<div class="row"><span class="sw" style="background:${c}"></span>${labels[i]}</div>`).join('')
    + (note ? `<div class="note">${note}</div>` : '');
  el.hidden = false;
}

export function hideLegend() { $('legend').hidden = true; }

export function renderWarnings(list) {
  const el = $('warnings');
  el.replaceChildren(...list.map((w) => {
    const p = document.createElement('p');
    p.textContent = w;   // textContent: komunikaty traktujemy jako zwykły tekst, nie HTML
    return p;
  }));
  el.hidden = list.length === 0;
}

export function renderTop(list, onClick) {
  const ol = $('top-list');
  ol.innerHTML = '';
  if (!list.length) {
    ol.innerHTML = '<li class="muted">Brak wyników w tym obszarze.</li>';
    return;
  }
  list.forEach((place, i) => {
    const li = document.createElement('li');
    li.textContent = `${place.name} — ${fmt(place.score)} klientów / konkurenta`;
    li.addEventListener('click', () => onClick(place, i));
    ol.append(li);
  });
}

export function setLoading(loading) {
  const btn = $('analyze-btn');
  btn.disabled = loading;
  btn.textContent = loading ? 'Analizuję…' : 'Analizuj';
}

export function showError(message) {
  const el = $('error');
  el.textContent = message || '';
  el.hidden = !message;
}

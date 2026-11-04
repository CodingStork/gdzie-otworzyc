// Interfejs: lewy panel (same ustawienia), prawy panel (legenda i wnioski o obszarze), pytajniki z wyjaśnieniami,
// dymek ze szczegółami punktu, wyszukiwarka adresów i zakładki arkusza na telefonie.
import { geocode } from './api.js';
import { fogGradientCss, niceLogTicks, trendGradientCss } from './colors.js';

const $ = (id) => document.getElementById(id);

let catalog = null;

// useGrouping: 'always' — domyślnie pl-PL nie grupuje liczb czterocyfrowych (1500), a pięciocyfrowe tak (15 800).
export const fmt = (n, digits = 0) =>
  Number(n).toLocaleString('pl-PL', { maximumFractionDigits: digits, useGrouping: 'always' });

const capitalize = (text) => text.charAt(0).toUpperCase() + text.slice(1);

// ---- Wyjaśnienia pod pytajnikami (teksty ze specyfikacji v3 §5, uzupełnione w v3.1 o drugie źródło firm — Overture) ----
const HELP = {
  tools: 'Okrąg: kliknij mapę w miejscu, które chcesz zbadać — pojawi się okrąg (zawsze ok. 1/5 ekranu, więc po oddaleniu mapy ' +
    'obejmie nawet województwo). Kropką na krawędzi zmienisz promień, kropką w środku przesuniesz okrąg, a promień możesz też wpisać w km. ' +
    'Wpisana miejscowość dostaje okrąg o średnicy 5 km; przełączenie na drugie narzędzie zamienia zaznaczenie w tym samym miejscu. ' +
    'Kliknij jeszcze raz wybrane narzędzie, żeby je odznaczyć i swobodnie przesuwać mapę. ' +
    'Prostokąt: przeciągnij po mapie; za rogi zmienisz jego rozmiar. Każdy obszar, nawet cała Polska, liczymy z Twoimi ustawieniami.',
  open: 'Ilu klientów mogłaby przyciągnąć nowa firma w danym miejscu. Liczymy to modelem Huffa: każdy mieszkaniec wybiera między firmami, ' +
    'a bliższa firma przyciąga go mocniej. Uwzględniamy konkurentów z OpenStreetMap i Overture Maps oraz »inne możliwości« ' +
    '(firmy, których nie ma w tych bazach, zakupy gdzie indziej). Liczba służy do porównywania miejsc między sobą — to nie prognoza sprzedaży: ' +
    'model zna tylko miejsce zamieszkania klientów (nie pracy ani dojazdów), nie zna ich zamożności ani tego, że duży sklep przyciąga mocniej niż mały.',
  demand: 'Ilu klientów mieszka w zasięgu klienta od danego miejsca (w okręgu o tym promieniu) — tę samą liczbę pokazuje dymek po kliknięciu. ' +
    'Mieszkańcy to szacunek: spis 2021 rozłożony na budynki mieszkalne z OpenStreetMap.',
  build: 'Ile nowych budynków mieszkalnych ma pozwolenie na budowę w zasięgu od danego miejsca (rejestr GUNB, wybrany okres). ' +
    'Pozwolenie nie oznacza jeszcze wybudowanego domu, a blok liczy się jak jeden budynek (rejestr nie podaje liczby mieszkań). ' +
    'Konkurencji tu nie liczymy — firm budowlanych i wykończeniowych prawie nie ma w OpenStreetMap ani Overture Maps.',
  competition: 'Gdzie jest najwięcej firm wybranego typu. Dane z OpenStreetMap i Overture Maps — mogą być niepełne.',
  trend: 'Gdzie w ostatnich 12 miesiącach wydano w zasięgu więcej pozwoleń na nowe budynki niż w 12 miesiącach wcześniej. ' +
    'Czerwony = budów przybywa (rozwijająca się okolica), niebieski = ubywa, przezroczysty = bez zmian. ' +
    'Pozwolenie nie oznacza jeszcze wybudowanego domu.',
  reach: 'Jak daleko typowy klient jest gotów dojść lub dojechać (przy budowach: jak daleko Ty dojeżdżasz do klienta). ' +
    'Fryzjer, sklep spożywczy: kilkaset metrów do 2 km; market budowlany, brukarz: 10–20 km. ' +
    'Po kliknięciu w zbadany obszar widać ten zasięg jako okrąg — kropką na jego krawędzi też go zmienisz. ' +
    'Najmniej 0,3 km (dane o mieszkańcach mają rozdzielczość ok. 300 m), przy budowach 1 km (pozwolenie znamy z dokładnością do obrębu).',
  legend: 'Ciemniejszy kolor = więcej. Skala jest logarytmiczna: o jeden odcień ciemniej to ok. 20–80% więcej, ' +
    'więc różnice o kilka–kilkanaście procent prawie nie zmieniają koloru (i dobrze — dane nie są aż tak dokładne). ' +
    'Przezroczyste miejsca mają bardzo małe wartości. Dokładne liczby zobaczysz po kliknięciu mapy. ' +
    'Kolory dopasowują się do tego, co widać na ekranie: po przybliżeniu do miasta najjaśniejsze i najciemniejsze miejsca są liczone tylko z widocznej części, ' +
    'więc widać różnice wewnątrz miasta (legenda pokazuje aktualne liczby).',
  gaps: 'Szare kreskowanie: większość klientów tego miejsca mieszka tam, gdzie w danych jest podejrzanie mało firm ' +
    '(najwyżej ¼ tego, co wynika ze średniej krajowej przy takiej liczbie mieszkańców). Wynik może być wtedy skutkiem luki w danych ' +
    '(brak firm w OpenStreetMap i Overture Maps), a nie braku konkurencji. ' +
    'Małych miejscowości, w których średnio byłyby mniej niż 3 firmy, nie oceniamy.',
  summary: 'Liczby dotyczą całego zaznaczonego obszaru. Mieszkańcy to szacunek: spis powszechny 2021 rozłożony na budynki mieszkalne. ' +
    'Firmy pochodzą z OpenStreetMap i Overture Maps (powtórzenia usuwamy) — nie wszystkie firmy są na tych mapach, więc liczba bywa zaniżona. ' +
    'Kliknij w zaznaczony obszar, żeby zobaczyć liczby dla jednego miejsca.',
  estimate: 'Ilu klientów mogłaby przyciągnąć nowa firma w tym miejscu (model Huffa) — to ta liczba wyznacza kolor mapy »Gdzie otworzyć«. ' +
    'Różni się od liczby mieszkańców wyżej, bo liczymy też klientów spoza okręgu (bliższych mocniej), a część z nich wybierze konkurencję ' +
    'albo »inne możliwości«. Służy do porównywania miejsc między sobą — to nie prognoza sprzedaży.',
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

// Najmniejszy zasięg dla wybranych klientów: przy pozwoleniach 1 km (lokalizacja z dokładnością do obrębu — tyle i tak liczy
// serwer), inaczej 0,3 km. Suwak nie może pokazywać mniej, niż naprawdę liczymy (uwaga Marcina: „0,3 km”, a dymek „w promieniu 1 km”).
const PERMITS_MIN_KM = 1;
const minReachKm = () => (currentDemand() && currentDemand().source === 'permits' ? PERMITS_MIN_KM : KM_MIN);

// Ustawia zasięg (np. typowy dla wybranej branży albo przeciągnięty kropką na mapie), nie mniej niż minimum dla klientów.
function setReach(km) {
  $('reach-input').value = kmToSlider(Math.min(KM_MAX, Math.max(minReachKm(), Number(km))));
  showReach();
}
export const setReachKm = setReach;

function syncReachMin() {
  $('reach-input').min = kmToSlider(minReachKm());
  if (reachKm() < minReachKm()) setReach(minReachKm());
}

// ---- Promień okręgu (pole w karcie przy okręgu): 1–350 km; zaokrąglenie zależne od wielkości ----
// Każdy okrąg liczymy z ustawieniami użytkownika; powyżej 30 km — bez rankingu najlepszych miejsc (backend: routes.TOP_RADIUS_KM).
export const RADIUS_MIN_KM = 1;
export const RADIUS_MAX_KM = 350;
export function snapRadius(km) {
  const n = Number(km);
  if (!Number.isFinite(n)) return 10;
  const step = n < 5 ? 0.5 : n < 50 ? 1 : 5;
  return Math.min(RADIUS_MAX_KM, Math.max(RADIUS_MIN_KM, Math.round(n / step) * step));
}
// „12,5” albo „12.5” z pola tekstowego → liczba (NaN, gdy to nie liczba).
export const parseKm = (text) => Number(String(text).trim().replace(',', '.'));

// ---- Krok 1: narzędzie do zaznaczania obszaru (okrąg / prostokąt), bez domyślnego wyboru ----

export function initTools(onPick) {
  document.querySelectorAll('.tool-button').forEach((b) => b.addEventListener('click', () => onPick(b.dataset.tool)));
}

// tool = null: żadne narzędzie nie jest wybrane (mapę przesuwa się myszą).
export function setTool(tool) {
  document.querySelectorAll('.tool-button').forEach((b) => {
    b.setAttribute('aria-pressed', String(b.dataset.tool === tool));
    b.classList.remove('attention');
  });
}

// Pulsująca ramka wokół przycisków narzędzi — gdy ktoś kliknie mapę, zanim wybierze okrąg albo prostokąt.
export function toolsAttention(on) {
  document.querySelectorAll('.tool-button').forEach((b) => b.classList.toggle('attention', on));
  const tab = document.querySelector('#tabs [data-tab=settings]');
  if (tab) tab.classList.toggle('attention', on);
}

// Pulsujące pola „Typ działalności” i „Twoi klienci to” — gdy obszar jest zaznaczony, a nie ma czego liczyć.
export function settingsAttention(on) {
  for (const id of ['type-select', 'demand-select']) $(id).classList.toggle('attention', on);
  const tab = document.querySelector('#tabs [data-tab=settings]');
  if (tab) tab.classList.toggle('attention', on);
}

// ---- Formularz ----

// Pusta pozycja list: zaproszenie do wyboru, a nie zakaz („nie wybieraj” brzmiało jak polecenie — uwaga Marcina).
//
// „Pracuję przy budowie / wykończeniu” (v3.7) to osobna pozycja na liście branż, a nie typ z katalogu: dla brukarza czy
// instalatora klientami są nowe domy i bloki (pozwolenia na budowę), a konkurencji nie liczymy (takich firm prawie nie ma
// w OSM i Overture). Przy pozostałych branżach klientami są tylko ludzie — „barber + nowe bloki” nie miało sensu.
export const BUILD = 'build';
export const isBuild = () => $('type-select').value === BUILD;

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

// Lista klientów zależna od branży: przy budowie — nowe budowy (pozwolenia), poza tym — ludzie ze spisu.
// Dopisek „(sugerowane)” przy czynnikach zalecanych dla typu; wybór zostaje, jeśli nadal jest na liście.
function fillDemands() {
  const select = $('demand-select');
  const keep = select.value;
  const type = currentType();
  const suggested = new Set(type ? type.suggested_demands : []);
  const source = isBuild() ? 'permits' : 'census';
  select.replaceChildren(new Option('Wybierz klientów…', ''));
  for (const demand of catalog.demands.filter((d) => d.source === source)) {
    select.append(new Option(demand.name + (suggested.has(demand.id) ? ' (sugerowane)' : ''), demand.id));
  }
  select.value = [...select.options].some((o) => o.value === keep) ? keep : '';
}

// Po zmianie typu: lista klientów pasuje do branży, domyślni klienci są zaznaczeni, a suwak zasięgu wraca do wartości typowej
// dla branży (przy budowie — dla pozwoleń, 10 km).
function onTypeChange() {
  fillDemands();
  const type = currentType();
  if (isBuild()) {
    $('demand-select').value = 'new_all';
    setReach(demandById('new_all').default_reach_km);
  } else if (type) {
    $('demand-select').value = type.default_demand;
    setReach(type.bandwidth_km);
  }
  syncReachMin();
  syncMonthsRow();
}

// onChange: wywoływane po każdej zmianie formularza, która wymaga nowego zapytania (suwaki: dopiero po puszczeniu).
export function renderCatalog(data, onChange) {
  catalog = data;
  const typeSelect = $('type-select');
  typeSelect.innerHTML = '';
  typeSelect.append(new Option('Wybierz branżę…', ''));
  for (const group of catalog.groups) {
    const optgroup = document.createElement('optgroup');
    optgroup.label = group.name;
    for (const type of group.types) optgroup.append(new Option(type.name, type.id));
    typeSelect.append(optgroup);
  }
  const build = document.createElement('optgroup');
  build.label = 'Praca u klienta';
  build.append(new Option('Pracuję przy budowie / wykończeniu (brukarz, instalator, okna…)', BUILD));
  typeSelect.append(build);
  const demandSelect = $('demand-select');
  fillDemands();
  $('months-select').value = String(catalog.default_months);

  typeSelect.addEventListener('change', () => { onTypeChange(); syncLayers(); onChange(); });
  demandSelect.addEventListener('change', () => { syncReachMin(); syncMonthsRow(); syncLayers(); onChange(); });
  $('months-select').addEventListener('change', onChange);
  // Przy przeciąganiu suwaków tylko aktualizujemy podpis; zapytanie idzie po puszczeniu (zdarzenie change).
  $('reach-input').addEventListener('input', showReach);
  $('reach-input').addEventListener('change', onChange);
  setReach(1.5);
  syncReachMin();
  syncMonthsRow();
  syncLayers();
}

// Parametry formularza; puste = brak wyboru (backend wymaga co najmniej jednego z: type, demand).
export function selectedParams() {
  const demand = currentDemand();
  const params = {
    type: isBuild() ? '' : $('type-select').value,             // przy budowie nie ma typu firmy — liczymy tylko budowy
    demand: demand ? demand.id : '',
    reach_km: reachKm(),
  };
  if (demand && demand.needs_months) params.months = $('months-select').value;
  return params;
}

// Czy jest co liczyć (branża albo klienci)? Bez tego karta przy obszarze nie pokazuje przycisku „Analizuj”.
export function hasSettings() {
  const p = selectedParams();
  return !!(p.type || p.demand);
}

// ---- Warstwy mapy: wybór w lewym panelu (radio), tylko dostępne dla bieżących ustawień ----
// typ + klienci → „Gdzie otworzyć”, „Gdzie są klienci”; sam popyt → „Gdzie są klienci”; sama branża → „Gdzie są {firmy}”;
// praca przy budowie → „Gdzie się buduje” i „Gdzie buduje się więcej niż rok temu” (trend).

export function availableLayers() {
  const type = currentType();
  const demand = currentDemand();
  const layers = type && demand ? ['open', 'demand'] : demand ? ['demand'] : type ? ['competition'] : [];
  if (demand && demand.source === 'permits') layers.push('trend');
  return layers;
}

function layerText(layer) {
  const type = currentType();
  return { open: 'Gdzie otworzyć', demand: isBuild() ? 'Gdzie się buduje' : 'Gdzie są klienci',
    trend: 'Gdzie buduje się więcej niż rok temu', competition: `Gdzie są ${type ? type.plural : 'firmy'}` }[layer];
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
    help.dataset.help = layer === 'demand' && isBuild() ? 'build' : layer;
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
  if (layer === 'demand') return `${demand ? demand.name : 'Klienci'} w zasięgu`;
  if (layer === 'trend') return 'Zmiana liczby nowych budów';
  return `${type ? capitalize(type.plural) : 'Firmy'} w zasięgu`;
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

function legendHtml(title, bar, rows, gapHint = false) {
  const el = $('legend');
  el.innerHTML = '<div class="legend-title"><b></b> <button type="button" class="help" data-help="legend" aria-label="Jak czytać kolory?">?</button></div>' +
    `<div class="legend-body"><div class="bar" style="background:${bar}"></div><div class="stops">${rows}</div></div>` +
    (gapHint ? '<div class="legend-gap"><span class="hatch"></span> mało danych o firmach <button type="button" class="help" data-help="gaps" aria-label="Co oznacza kreskowanie?">?</button></div>' : '');
  el.querySelector('b').textContent = title;   // tytuł zawiera nazwy z katalogu — wstawiamy jako tekst
  el.hidden = false;
}

const stopRow = (t, text) =>
  `<div class="stop" style="bottom:${(t * 100).toFixed(1)}%"><span class="tick"></span>${text}</div>`;

// scale: { lo, hi } z logScale() — wartości, przy których kolor jest najjaśniejszy / najciemniejszy.
export function renderLegend(title, scale, gapHint = false) {
  if (!scale) { $('legend').hidden = true; return; }
  const label = (prefix, v) => `${prefix}${fmt(v, legendDigits(v))}`;
  const stops = [{ t: 1, text: label('≥ ', twoDigits(scale.hi)) }, { t: 0, text: label('≤ ', twoDigits(scale.lo)) }];
  if (scale.hi > scale.lo) {
    // Na telefonie pasek jest niski: mniej podpisów i większy odstęp od końców, żeby się nie zlewały.
    const narrow = window.innerWidth < 768;
    for (const tick of niceLogTicks(scale, narrow ? 2 : 5, narrow ? 0.2 : 0.1)) stops.push({ t: tick.t, text: label('', tick.v) });
  }
  legendHtml(title, fogGradientCss('to top'), stops.map((s) => stopRow(s.t, s.text)).join(''), gapHint);
}

// Legenda trendu: paleta rozbieżna, podpisy słowne zamiast liczb (wartości to ważone odległością przyrosty pozwoleń).
export function renderTrendLegend(title) {
  const rows = [stopRow(1, 'więcej budów'), stopRow(0.5, 'bez zmian'), stopRow(0, 'mniej budów')].join('');
  legendHtml(title, trendGradientCss('to top'), rows);
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
// Marcin: „prostota” — na ekranie tylko dwie liczby (klienci i firmy w obszarze), a pod nimi skąd są dane. Wyjaśnienia są pod pytajnikami.

// Szacunek do setek (od 1000), do dziesiątek (od 100), inaczej do jedności — nie pokazujemy fałszywej precyzji.
const roundEstimate = (n) => (n >= 1000 ? Math.round(n / 100) * 100 : n >= 100 ? Math.round(n / 10) * 10 : Math.round(n));

// Liczba klientów: mieszkańcy to szacunek (spis rozłożony na budynki) — „ok.”; pozwolenia to dokładna liczba z rejestru.
const demandValue = (n, permits) => (permits ? fmt(n) : `ok. ${fmt(roundEstimate(n))}`);

// Źródła liczb jednym zdaniem: „Mieszkańcy: spis powszechny 2021. Fryzjerzy: OpenStreetMap 2 707, Overture Maps 2 259.”
function sourcesText(demand, permits, typePlural, competitors) {
  const parts = [];
  if (demand) parts.push(permits ? `${demand.name}: pozwolenia na budowę z GUNB, ${permits.from} – ${permits.to}.`
    : `${demand.name}: spis powszechny 2021 (Eurostat).`);
  if (competitors) parts.push(`${capitalize(typePlural)}: OpenStreetMap ${fmt(competitors.osm)}, Overture Maps ${fmt(competitors.overture)}.`);
  return parts.join(' ');
}

// summary z /api/surface; ctx: { demandId, permitsPeriod }. Wiersz klientów tylko przy wybranych klientach, wiersz firm — przy branży.
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
  const demand = summary.demand_total != null ? demandById(ctx.demandId) : null;
  const permits = ctx.permitsPeriod;
  if (demand) add(`${demand.name}: ${demandValue(summary.demand_total, permits)}`, 'strong');
  if (summary.competitors) add(`${capitalize(summary.type_plural)}: ${fmt(summary.competitors.total)}`, 'strong');
  // Luka w danych zostaje (mapa ma mówić prawdę), ale jednym zdaniem — liczby są pod pytajnikiem kreskowania.
  if (summary.data_gap) add('⚠ W danych prawdopodobnie brakuje części firm w tym obszarze.', 'warn');
  add(sourcesText(demand, permits, summary.type_plural, summary.competitors), 'source');
  $('summary-box').hidden = false;
}

export const hideSummary = () => { $('summary-box').hidden = true; };

// Wymiary prostokąta, np. „12,4 × 8,1 km”.
export const sizeText = (widthKm, heightKm) => `${fmt(widthKm, 1)} × ${fmt(heightKm, 1)} km`;

// ---- Karta przy zaznaczonym obszarze (okrąg albo prostokąt) ----
// Okrąg: pole „Promień: [12,5] km” (zmiana pola → onRadius(km)). Prostokąt: wymiary i ewentualny problem (za duży / za mały).
// Dopóki nie wybrano branży ani klientów, karta NIE ma przycisku „Analizuj” — mówi, co trzeba zrobić (setReady(false)).
// Zwraca { el, setRadius(km), setSize(tekst, problem), setReady(gotowe) }.
export function areaCard({ kind, radiusKm: radius, onRadius, onConfirm, onCancel }) {
  const el = document.createElement('div');
  el.className = 'selection-card';
  const head = document.createElement('div');
  head.className = 'sel-title';
  head.textContent = kind === 'circle' ? 'Zaznaczony okrąg' : 'Zaznaczony prostokąt';
  const size = document.createElement('div');
  size.className = 'sel-size';
  let input = null;
  if (kind === 'circle') {
    const label = document.createElement('label');
    label.className = 'sel-radius';
    input = document.createElement('input');
    input.type = 'text';
    input.inputMode = 'decimal';
    input.className = 'sel-km';
    input.setAttribute('aria-label', 'Promień w kilometrach');
    label.append('Promień: ', input, ' km');
    const apply = () => {
      const km = parseKm(input.value);
      if (Number.isFinite(km) && km > 0) onRadius(snapRadius(km));
      else input.value = fmt(radius, radius < 10 ? 1 : 0);
    };
    input.addEventListener('change', apply);
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); apply(); input.blur(); } });
    size.append(label);
  }
  const body = document.createElement('div');
  body.className = 'sel-body';
  const buttons = document.createElement('div');
  buttons.className = 'sel-buttons';
  const ok = document.createElement('button');
  ok.type = 'button';
  ok.className = 'sel-ok';
  ok.textContent = '✓ Analizuj obszar';
  ok.addEventListener('click', onConfirm);
  const cancel = document.createElement('button');
  cancel.type = 'button';
  cancel.className = 'sel-cancel';
  cancel.textContent = '✕';
  cancel.title = 'Anuluj';
  cancel.setAttribute('aria-label', 'Anuluj zaznaczenie');
  cancel.addEventListener('click', onCancel);
  buttons.append(ok);
  // ✕ wisi poza kartą, po prawej, na wysokości tytułu (Marcin: pod treścią karty wyglądał źle); na telefonie — w rogu karty (style.css).
  el.append(cancel, head, size, body, buttons);
  let problem = '';
  let ready = false;
  const refresh = () => {
    ok.hidden = !ready;                                  // bez branży i klientów nie ma czego analizować — nie udajemy, że jest
    ok.disabled = !!problem;
    // Na telefonie ustawienia są w zakładce „Ustawienia” pod mapą (pulsuje), a nie po lewej.
    const where = window.matchMedia('(max-width: 767px)').matches ? 'w „Ustawieniach”' : 'po lewej';
    body.textContent = ready ? '' : `Wybierz ${where} branżę lub klientów.`;
    body.classList.toggle('need', !ready);
  };
  const card = {
    el,
    setRadius(km) {
      radius = km;
      if (input && document.activeElement !== input) input.value = fmt(km, km < 10 ? 1 : 0);
    },
    setSize(text, why = '') {
      problem = why;
      size.textContent = why || text;
      size.classList.toggle('bad', !!why);
      refresh();
    },
    setReady(value) { ready = value; refresh(); },
  };
  if (kind === 'circle') card.setRadius(radius);
  refresh();
  return card;
}

// ---- Dymek klikniętego punktu (dokładne liczby z /api/point, spec v3 §4) ----

const km = (r) => fmt(r, 1);

// Zwraca element DOM (tekst wstawiamy przez textContent — nazwy firm nie są HTML-em).
// onSetCenter: „Zaznacz tu nowy okrąg”; onClose: ✕ — taki sam jak na karcie zaznaczenia (poza dymkiem, na wysokości pierwszej linii).
export function pointPopup(d, { onSetCenter, onClose }) {
  const box = document.createElement('div');
  box.className = 'point-card';
  const close = document.createElement('button');
  close.type = 'button';
  close.className = 'sel-cancel';
  close.textContent = '✕';
  close.title = 'Zamknij';
  close.setAttribute('aria-label', 'Zamknij szczegóły');
  close.addEventListener('click', onClose);
  box.append(close);
  const add = (text, bold = false) => {
    const p = document.createElement('div');
    if (bold) p.className = 'strong';
    p.textContent = text;
    box.append(p);
    return p;
  };
  const permits = d.permits_period != null;
  add(`W promieniu ${km(d.radius_km)} km:`, true);
  if (d.demand != null) add(`${d.demand_name}: ${demandValue(d.demand, permits)}`);
  if (d.competitors != null) add(`${capitalize(d.type_plural || d.type_name)}: ${fmt(d.competitors)}`);
  // Klientów na firmę dopiero przy co najmniej 2 firmach — przy 0 lub 1 ten iloraz nic nie mówi.
  if (d.demand != null && d.competitors > 1) add(`Na 1 firmę: ${demandValue(d.demand / d.competitors, permits)} ${clientsNoun(permits)}`);
  if (d.expected != null) {
    // Liczba z modelu Huffa (kolor mapy „Gdzie otworzyć”) — skąd się bierze i czemu różni się od liczby mieszkańców, mówi pytajnik.
    const row = add(`Szacowani klienci nowej firmy: ok. ${fmt(roundEstimate(d.expected))} `, true);
    const help = document.createElement('button');
    help.type = 'button';
    help.className = 'help';
    help.dataset.help = 'estimate';
    help.setAttribute('aria-label', 'Skąd ta liczba?');
    help.textContent = '?';
    row.append(help);
  }
  if (d.data_gap && d.data_gap.warn) add('⚠ W danych prawdopodobnie brakuje tu części firm.').className = 'warn';
  if (onSetCenter) {
    const link = document.createElement('button');
    link.type = 'button';
    link.className = 'link-button';
    link.textContent = 'Zaznacz tu nowy okrąg';
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

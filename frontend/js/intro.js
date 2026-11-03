// Animacja wprowadzająca (v3.6), dwa kroki:
//   • „tools” — kursor jedzie do przycisków „◯ Okrąg” i „▭ Prostokąt” w lewym panelu (bez wybranego narzędzia nie da się
//     zaznaczyć obszaru), przyciski pulsują;
//   • „circle” / „rect” — po wybraniu narzędzia: jak nim zaznaczyć obszar (kliknięcie + kropka na krawędzi albo przeciągnięcie).
// Sama animacja to czysty CSS (@keyframes w style.css); ten plik tworzy elementy, mierzy położenie przycisków i mapy (inne na
// telefonie) i pilnuje, kiedy pokazać animację i schować. Wszystko dzieje się na ŚRODKU MAPY — przy starcie to środek Polski
// (do v3.5 kursor klikał w ułamek szerokości mapy, co przy widoku całej Polski wypadało na Litwie).
// Każdy krok pokazujemy sam z siebie tylko raz (localStorage); przycisk „?” przy mapie pokazuje go ponownie.
const STORAGE_KEY = 'gdzie-otworzyc-intro-v36';

const CURSOR_SVG = '<svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true">' +
  '<path d="M3 2 L3 19 L8 14.5 L11.5 22 L14.5 20.6 L11 13.2 L18 13 Z" fill="#fff" stroke="#222" stroke-width="1.6" stroke-linejoin="round"/></svg>';

const CAPTIONS = {
  tools: 'Zacznij od wyboru po lewej: <b>◯ Okrąg</b> albo <b>▭ Prostokąt</b>. Potem zaznaczysz na mapie obszar, który chcesz zbadać.',
  circle: 'Kliknij mapę w miejscu, które chcesz zbadać — pojawi się okrąg. <b>Kropką na krawędzi</b> zmienisz promień (możesz go też ' +
    'wpisać w km), <b>kropką w środku</b> przesuniesz okrąg.',
  rect: 'Przeciągnij po mapie, żeby zaznaczyć prostokąt. Za <b>rogi</b> zmienisz jego rozmiar.',
};

const seen = (step) => {
  try { return localStorage.getItem(`${STORAGE_KEY}-${step}`) === '1'; } catch (e) { return false; }   // bez dostępu do pamięci: pokazujemy
};
const markSeen = (step) => {
  try { localStorage.setItem(`${STORAGE_KEY}-${step}`, '1'); } catch (e) { /* tryb prywatny: trudno, zobaczy jeszcze raz */ }
};

// mapEl: kontener mapy Leaflet. Nakładka leży nad całą stroną (position: fixed), bo kursor jedzie też do lewego panelu.
export function initIntro(mapEl) {
  const overlay = document.createElement('div');
  overlay.id = 'app-intro';
  overlay.hidden = true;
  overlay.innerHTML = '<div class="intro-ring"></div><div class="intro-circle"></div><div class="intro-dot intro-dot-center"></div>' +
    '<div class="intro-dot intro-dot-edge"></div><div class="intro-rect"></div>' +
    `<div class="intro-cursor">${CURSOR_SVG}</div>` +
    '<div class="intro-caption"><p></p><button type="button" class="intro-ok">Rozumiem</button></div>';
  document.body.append(overlay);
  let step = null;

  const toolButtons = () => [...document.querySelectorAll('.tool-button')];

  // Położenie elementów w pikselach strony: środek mapy, promień okręgu (jak w aplikacji: 20% krótszego boku), przyciski narzędzi.
  function layout() {
    const m = mapEl.getBoundingClientRect();
    const px = (v) => `${Math.round(v)}px`;
    const set = (name, x, y) => { overlay.style.setProperty(`--${name}x`, px(x)); overlay.style.setProperty(`--${name}y`, px(y)); };
    const cx = m.left + m.width / 2;
    const cy = m.top + m.height / 2;
    const r = 0.2 * Math.min(m.width, m.height);
    set('c', cx, cy);                                    // środek mapy: tu kursor klika (okrąg) / wokół niego rysuje (prostokąt)
    set('s', cx - r * 0.9, cy + r * 1.1);                // skąd kursor wjeżdża
    set('e0', cx + r, cy);                               // kropka na krawędzi — przed i po przeciągnięciu
    set('e1', cx + r * 1.4, cy);
    set('r0', cx - m.width * 0.22, cy - m.height * 0.16);  // początek i koniec przeciągnięcia prostokąta
    set('r1', cx + m.width * 0.22, cy + m.height * 0.16);
    overlay.style.setProperty('--cr', px(r));
    overlay.style.setProperty('--rw', px(m.width * 0.44));
    overlay.style.setProperty('--rh', px(m.height * 0.32));
    const [circle, rect] = toolButtons().map((b) => b.getBoundingClientRect());
    // Przycisk niewidoczny (np. zwinięty arkusz na telefonie) — kursor zostaje na mapie, zostaje sam podpis.
    const visible = (b) => b && b.width > 0 && b.height > 0;
    overlay.classList.toggle('no-buttons', !(visible(circle) && visible(rect)));
    if (visible(circle)) set('t1', circle.left + circle.width / 2, circle.top + circle.height / 2);
    if (visible(rect)) set('t2', rect.left + rect.width / 2, rect.top + rect.height / 2);
    const caption = overlay.querySelector('.intro-caption');
    caption.style.left = px(cx);
    caption.style.top = px(m.bottom - 58);               // nad stopką z atrybucją
    caption.style.maxWidth = px(Math.min(420, m.width - 24));
  }

  function hide() {
    if (overlay.hidden) return;
    overlay.hidden = true;
    toolButtons().forEach((b) => b.classList.remove('intro-pulse'));
    if (step) markSeen(step);
  }

  // tool: null → krok „tools”; 'circle' / 'rect' → jak zaznaczyć tym narzędziem.
  function show(tool = null) {
    step = tool || 'tools';
    overlay.dataset.step = step;
    overlay.querySelector('.intro-caption p').innerHTML = CAPTIONS[step];
    layout();
    // Ponowne odtworzenie animacji CSS: element musi się „odświeżyć”, inaczej przeglądarka nie zacznie jej od początku.
    overlay.hidden = true;
    void overlay.offsetWidth;
    overlay.hidden = false;
    toolButtons().forEach((b) => b.classList.toggle('intro-pulse', step === 'tools'));
  }

  // Znika po pierwszym kliknięciu, przeciągnięciu lub kółku myszy w mapie (zdarzenia łapiemy w fazie przechwytywania) i po „Rozumiem”.
  mapEl.addEventListener('pointerdown', hide, true);
  mapEl.addEventListener('wheel', hide, { capture: true, passive: true });
  overlay.querySelector('.intro-ok').addEventListener('click', hide);
  window.addEventListener('resize', () => { if (!overlay.hidden) layout(); });

  return {
    show,
    hide,
    showFirstTime() { if (!seen('tools')) show(null); },
    // Wybrano narzędzie: pokazujemy, jak nim zaznaczyć — przy pierwszym użyciu tego narzędzia albo gdy trwa krok „tools”.
    toolChosen(tool) {
      const during = !overlay.hidden && step === 'tools';
      if (during) markSeen('tools');
      if (during || !seen(tool)) show(tool);
    },
  };
}

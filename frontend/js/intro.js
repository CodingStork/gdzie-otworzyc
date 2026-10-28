// Animacja wprowadzająca na mapie: kursor klika w mapę (pojawia się okrąg), potem jedzie do przycisku „▭ Prostokąt” i przeciąga ramkę.
// Sama animacja to czysty CSS (@keyframes w style.css); ten plik tylko tworzy elementy, ustawia ich położenie
// (zależy od rozmiaru mapy i miejsca przycisku — inne na telefonie) i pilnuje, kiedy pokazać ją i schować.
// Pierwsza wizyta: pokazujemy (zapamiętane w localStorage); przycisk „?” przy mapie pokazuje ją ponownie.
const STORAGE_KEY = 'gdzie-otworzyc-intro-v34';

const CURSOR_SVG = '<svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true">' +
  '<path d="M3 2 L3 19 L8 14.5 L11.5 22 L14.5 20.6 L11 13.2 L18 13 Z" fill="#fff" stroke="#222" stroke-width="1.6" stroke-linejoin="round"/></svg>';
const ICON_CLICK = '<svg viewBox="0 0 40 28" width="40" height="28" aria-hidden="true"><circle cx="16" cy="14" r="11" fill="#80002611" stroke="#800026" stroke-width="2" stroke-dasharray="4 3"/>' +
  '<circle cx="16" cy="14" r="2.5" fill="#800026"/><path d="M22 12 L22 24 L25.5 21 L28 26.5 L30 25.5 L27.5 20 L32 20 Z" fill="#fff" stroke="#222" stroke-width="1.3" stroke-linejoin="round"/></svg>';
const ICON_RECT = '<svg viewBox="0 0 40 28" width="40" height="28" aria-hidden="true"><rect x="3" y="4" width="28" height="18" fill="#25349411" stroke="#253494" stroke-width="2" stroke-dasharray="4 3"/>' +
  '<rect x="0.5" y="1.5" width="6" height="6" fill="#fff" stroke="#253494"/><rect x="27.5" y="18.5" width="6" height="6" fill="#fff" stroke="#253494"/>' +
  '<path d="M30 17 L30 27 L33 24.6 L35.2 28 L37 27 L35 23.5 L39 23.5 Z" fill="#fff" stroke="#222" stroke-width="1.2" stroke-linejoin="round"/></svg>';

function seen() {
  try { return localStorage.getItem(STORAGE_KEY) === '1'; } catch (e) { return false; }   // bez dostępu do pamięci: pokazujemy za każdym razem
}

function markSeen() {
  try { localStorage.setItem(STORAGE_KEY, '1'); } catch (e) { /* tryb prywatny: trudno, zobaczy jeszcze raz */ }
}

// mapEl: kontener mapy Leaflet (nakładka leży w nim, pod przyciskami mapy).
export function initIntro(mapEl) {
  const overlay = document.createElement('div');
  overlay.id = 'map-intro';
  overlay.hidden = true;
  overlay.innerHTML = '<div class="intro-circle"></div><div class="intro-ring"></div><div class="intro-rect"></div>' +
    `<div class="intro-cursor">${CURSOR_SVG}</div>` +
    `<div class="intro-caption"><div class="intro-icons">${ICON_CLICK}${ICON_RECT}</div>` +
    '<p>Kliknij mapę, żeby wybrać miejsce — albo zaznacz obszar przyciskiem »▭ Prostokąt«</p>' +
    '<button type="button" class="intro-ok">Rozumiem</button></div>';
  mapEl.append(overlay);

  // Położenie elementów animacji: punkt kliknięcia, przycisk „▭ Prostokąt” (zmierzony), prostokąt do „narysowania”.
  function layout() {
    const w = mapEl.clientWidth;
    const h = mapEl.clientHeight;
    const button = document.getElementById('rect-button');
    const m = mapEl.getBoundingClientRect();
    const b = button ? button.getBoundingClientRect() : { left: m.left + 10, top: m.top + 80, width: 90, height: 30 };
    const px = (v) => `${Math.round(v)}px`;
    const set = (name, x, y) => { overlay.style.setProperty(`--${name}x`, px(x)); overlay.style.setProperty(`--${name}y`, px(y)); };
    set('s', w * 0.28, h * 0.5);                        // skąd kursor wjeżdża
    set('c', w * 0.55, h * 0.3);                        // punkt kliknięcia
    set('b', b.left - m.left + b.width * 0.35, b.top - m.top + b.height * 0.5);   // przycisk „▭ Prostokąt”
    set('r0', w * 0.3, h * 0.42);                       // początek i koniec przeciągnięcia
    set('r1', w * 0.72, h * 0.64);
    overlay.style.setProperty('--rw', px(w * 0.42));
    overlay.style.setProperty('--rh', px(h * 0.22));
    overlay.style.setProperty('--cd', px(Math.min(110, Math.min(w, h) * 0.3)));
  }

  function hide() {
    overlay.hidden = true;
    const button = document.getElementById('rect-button');
    if (button) button.classList.remove('intro-pulse');
    markSeen();
  }

  function show() {
    layout();
    // Ponowne odtworzenie animacji CSS: element musi się „odświeżyć”, inaczej przeglądarka nie zacznie jej od początku.
    overlay.hidden = true;
    void overlay.offsetWidth;
    overlay.hidden = false;
    const button = document.getElementById('rect-button');
    if (button) button.classList.add('intro-pulse');
  }

  // Znika po pierwszym kliknięciu, przeciągnięciu lub kółku myszy w mapie (zdarzenia łapiemy w fazie przechwytywania) i po „Rozumiem”.
  mapEl.addEventListener('pointerdown', () => { if (!overlay.hidden) hide(); }, true);
  mapEl.addEventListener('wheel', () => { if (!overlay.hidden) hide(); }, { capture: true, passive: true });
  overlay.querySelector('.intro-ok').addEventListener('click', hide);

  return {
    show,
    hide,
    showFirstTime() { if (!seen()) show(); },
  };
}

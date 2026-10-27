// Skala kolorów: płynny gradient (jedna barwa, jasna → ciemna) wg PERCENTYLA wartości w widocznym obszarze.
// ColorBrewer YlGnBu (9 punktów) — czytelna także dla osób z zaburzeniami widzenia barw.
// Dlaczego percentyl, a nie sama wartość: rozkład wyników jest bardzo skośny (kilka miejsc ma ogromne
// wartości), więc kolor wg wartości malowałby prawie cały obszar na jasno. Percentyl wykorzystuje całą paletę.

export const GRADIENT = ['#ffffd9', '#edf8b1', '#c7e9b4', '#7fcdbb', '#41b6c4', '#1d91c0', '#225ea8', '#253494', '#081d58'];

const RGB = GRADIENT.map((hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)));

// pct 0–100 → kolor "rgb(r,g,b)" z interpolacją liniową między sąsiednimi punktami palety.
export function gradientColor(pct) {
  const x = Math.min(100, Math.max(0, pct)) / 100 * (RGB.length - 1);
  const i = Math.min(Math.floor(x), RGB.length - 2);
  const t = x - i;
  const [r, g, b] = RGB[i].map((c, k) => Math.round(c + (RGB[i + 1][k] - c) * t));
  return `rgb(${r},${g},${b})`;
}

// CSS pasek gradientu do legendy (kierunek np. 'to right' albo 'to top').
export function gradientCss(direction = 'to right') {
  const stops = GRADIENT.map((c, i) => `${c} ${(i / (GRADIENT.length - 1) * 100).toFixed(1)}%`);
  return `linear-gradient(${direction}, ${stops.join(', ')})`;
}

// Skala kolorów: płynny gradient (jedna barwa, jasna → ciemna) wg WARTOŚCI w skali logarytmicznej.
// ColorBrewer YlGnBu (9 punktów) — czytelna także dla osób z zaburzeniami widzenia barw.
// Dlaczego logarytm, a nie percentyl: rozkłady (ludność, liczba firm) są prawostronnie skośne. Percentyl w obszarze
// z dużą ilością słabych terenów wrzuca całe miasto do górnych 10% (4 600 i 19 000 mają prawie ten sam kolor);
// skala log zachowuje proporcje — każdy krok koloru to mniej więcej podwojenie wartości.
// Skalę liczymy w przeglądarce z heksagonów, które aktualnie rysujemy (albo leżą w wybranym okręgu).

export const GRADIENT = ['#ffffd9', '#edf8b1', '#c7e9b4', '#7fcdbb', '#41b6c4', '#1d91c0', '#225ea8', '#253494', '#081d58'];

const RGB = GRADIENT.map((hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)));

// t 0–1 → kolor "rgb(r,g,b)" z interpolacją liniową między sąsiednimi punktami palety.
export function gradientColor(t) {
  const x = Math.min(1, Math.max(0, t)) * (RGB.length - 1);
  const i = Math.min(Math.floor(x), RGB.length - 2);
  const f = x - i;
  const [r, g, b] = RGB[i].map((c, k) => Math.round(c + (RGB[i + 1][k] - c) * f));
  return `rgb(${r},${g},${b})`;
}

// Kwantyl q (0–1) posortowanej rosnąco tablicy, z interpolacją liniową.
function quantile(sorted, q) {
  const x = q * (sorted.length - 1);
  const i = Math.floor(x);
  return i + 1 < sorted.length ? sorted[i] + (sorted[i + 1] - sorted[i]) * (x - i) : sorted[i];
}

// Skala z wartości > 0: dolna granica = percentyl 2, górna = 98 (pojedyncze skrajności nie rozciągają skali).
// Zwraca { lo, hi } albo null, gdy nie ma żadnej dodatniej wartości.
export function logScale(values) {
  const positive = values.filter((v) => v > 0).sort((a, b) => a - b);
  if (!positive.length) return null;
  return { lo: quantile(positive, 0.02), hi: quantile(positive, 0.98) };
}

// Pozycja wartości na skali, 0–1. Zero → 0 (najjaśniejszy); lo == hi → środek palety.
export function logPosition(v, scale) {
  if (!scale || !(v > 0)) return 0;
  if (scale.hi <= scale.lo) return 0.5;
  const t = (Math.log10(Math.min(scale.hi, Math.max(scale.lo, v))) - Math.log10(scale.lo)) /
    (Math.log10(scale.hi) - Math.log10(scale.lo));
  return t;
}

export const logColor = (v, scale) => gradientColor(logPosition(v, scale));

// „Okrągłe” wartości 1–2–5 × 10^n mieszczące się w [lo, hi], nie więcej niż max; zostawiamy te, które nie
// nachodzą na końce paska (margin = ułamek wysokości paska).
export function niceTicks(scale, max = 5, margin = 0.1) {
  if (!scale || scale.hi <= scale.lo) return [];
  const all = [];
  for (let e = Math.floor(Math.log10(scale.lo)); e <= Math.ceil(Math.log10(scale.hi)); e++) {
    for (const m of [1, 2, 5]) {
      const v = m * Math.pow(10, e);
      const t = logPosition(v, scale);
      if (v >= scale.lo && v <= scale.hi && t >= margin && t <= 1 - margin) all.push({ v, t, m });
    }
  }
  if (all.length <= max) return all;
  // Za dużo: najpierw same potęgi dziesięciu, a gdy nadal za dużo — równomiernie wybrane.
  const decades = all.filter(({ m }) => m === 1);
  const pool = decades.length >= 3 ? decades : all;
  if (pool.length <= max) return pool;
  return Array.from({ length: max }, (_, k) => pool[Math.round(k * (pool.length - 1) / (max - 1))]);
}

// CSS pasek gradientu do legendy (kierunek np. 'to right' albo 'to top').
export function gradientCss(direction = 'to right') {
  const stops = GRADIENT.map((c, i) => `${c} ${(i / (GRADIENT.length - 1) * 100).toFixed(1)}%`);
  return `linear-gradient(${direction}, ${stops.join(', ')})`;
}

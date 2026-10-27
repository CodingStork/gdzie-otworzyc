// Kolory mgły: paleta ColorBrewer YlOrRd (żółty → pomarańczowy → czerwony), skala logarytmiczna i przezroczystość.
// Dlaczego YlOrRd, a nie tęcza: jedna barwa o rosnącym nasyceniu czyta się jako „więcej”, a tęcza (Borland & Taylor 2007)
// wprowadza fałszywe granice i nie ma naturalnej kolejności.
// Dlaczego logarytm: ludność i liczby firm mają rozkład prawostronnie skośny — skala liniowa zrobiłaby z całego
// miasta jedną czerwoną plamę. Przy skali log każdy krok koloru to mniej więcej podwojenie wartości.
// Dlaczego przezroczystość: małe wartości znikają, więc zostaje efekt „mgły” zagęszczającej się tam, gdzie jest ważnie.

export const YLORRD = ['#ffffcc', '#ffeda0', '#fed976', '#feb24c', '#fd8d3c', '#fc4e2a', '#e31a1c', '#bd0026', '#800026'];

const RGB = YLORRD.map((hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)));

// Przezroczystość w zależności od pozycji t na skali: 0 poniżej 0,05, potem liniowo do 0,85 przy t = 0,5 i 0,85 powyżej.
export function fogAlpha(t) {
  if (t < 0.05) return 0;
  if (t >= 0.5) return 0.85;
  return 0.85 * (t - 0.05) / 0.45;
}

// t 0–1 → [r, g, b, a] (a 0–1); kolor interpolowany liniowo między sąsiednimi punktami palety.
export function fogColor(t) {
  const clamped = Math.min(1, Math.max(0, t));
  const x = clamped * (RGB.length - 1);
  const i = Math.min(Math.floor(x), RGB.length - 2);
  const f = x - i;
  const [r, g, b] = RGB[i].map((c, k) => Math.round(c + (RGB[i + 1][k] - c) * f));
  return [r, g, b, fogAlpha(clamped)];
}

// Kwantyl q (0–1) posortowanej rosnąco tablicy, z interpolacją liniową.
function quantile(sorted, q) {
  const x = q * (sorted.length - 1);
  const i = Math.floor(x);
  return i + 1 < sorted.length ? sorted[i] + (sorted[i + 1] - sorted[i]) * (x - i) : sorted[i];
}

// Skala z wartości > 0 (null = poza okręgiem): dolna granica = percentyl 5, górna = 99.
// Zwraca { lo, hi } albo null, gdy nie ma żadnej dodatniej wartości.
export function logScale(values) {
  const positive = values.filter((v) => v > 0).sort((a, b) => a - b);
  if (!positive.length) return null;
  return { lo: quantile(positive, 0.05), hi: quantile(positive, 0.99) };
}

// Pozycja wartości na skali, 0–1. Wartość ≤ 0 → 0 (przezroczysta); lo == hi → środek palety.
export function logPosition(v, scale) {
  if (!scale || !(v > 0)) return 0;
  if (scale.hi <= scale.lo) return 0.5;
  return (Math.log10(Math.min(scale.hi, Math.max(scale.lo, v))) - Math.log10(scale.lo)) /
    (Math.log10(scale.hi) - Math.log10(scale.lo));
}

// „Okrągłe” wartości 1–2–5 × 10^n mieszczące się w [lo, hi], nie więcej niż max; zostawiamy te, które nie
// nachodzą na końce paska (margin = ułamek wysokości paska).
export function niceLogTicks(scale, max = 5, margin = 0.1) {
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

// CSS pasek gradientu do legendy — z tą samą przezroczystością co mgła na mapie (kierunek np. 'to top').
export function fogGradientCss(direction = 'to top') {
  const stops = Array.from({ length: 21 }, (_, k) => {
    const t = k / 20;
    const [r, g, b, a] = fogColor(t);
    return `rgba(${r},${g},${b},${a.toFixed(2)}) ${(t * 100).toFixed(0)}%`;
  });
  return `linear-gradient(${direction}, ${stops.join(', ')})`;
}

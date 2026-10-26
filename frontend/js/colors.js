// Skala kolorów: sekwencyjna (jedna barwa, jasna → ciemna), klasy kwantylowe.
// ColorBrewer YlGnBu — czytelna także dla osób z zaburzeniami widzenia barw.

export const PALETTE = ['#ffffcc', '#a1dab4', '#41b6c4', '#2c7fb8', '#253494'];

// Numer klasy: ile granic jest nie większych od wartości (granice = kwantyle z odpowiedzi API).
function classIndex(value, breaks) {
  let i = 0;
  while (i < breaks.length && value >= breaks[i]) i++;
  return i;
}

// Przy mniej niż 5 klasach (np. mało zróżnicowane dane) rozkładamy kolory równomiernie po palecie.
function paletteColor(index, classes, palette) {
  if (classes <= 1) return palette[palette.length - 1];
  return palette[Math.round(index * (palette.length - 1) / (classes - 1))];
}

export function colorFor(value, breaks, palette = PALETTE) {
  return paletteColor(classIndex(value, breaks), breaks.length + 1, palette);
}

// Kolory kolejnych klas — do legendy (te same, których używa colorFor).
export function classColors(breaks, palette = PALETTE) {
  const n = breaks.length + 1;
  return Array.from({ length: n }, (_, i) => paletteColor(i, n, palette));
}

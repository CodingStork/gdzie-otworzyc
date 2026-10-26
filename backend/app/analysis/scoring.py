"""Wynik „klienci na 1 konkurenta”, percentyle, klasy kolorów i wybór najlepszych miejsc."""
import numpy as np
from scipy.stats import rankdata


def score(D: np.ndarray, S: np.ndarray) -> np.ndarray:
    """Wynik = D / (S + 1): ilu potencjalnych klientów przypada na jednego konkurenta w zasięgu.

    „+1” wygładza przypadek braku konkurencji (bez niego dzielilibyśmy przez zero)
    i działa tak, jakby w okolicy był "wirtualny" konkurent.
    """
    return D / (S + 1)


def percentile_rank(x: np.ndarray) -> np.ndarray:
    """Percentyl (liczba całkowita 0–100) każdej wartości; remisy dostają średnią rangę."""
    n = len(x)
    if n == 0:
        return np.array([], dtype=int)
    if n == 1:
        return np.array([100])
    ranks = rankdata(x, method="average")  # 1..n
    return np.rint((ranks - 1) / (n - 1) * 100).astype(int)


def quantile_breaks(x: np.ndarray, k: int = 5) -> list[float]:
    """Granice k klas kwantylowych (k−1 liczb, rosnące, bez powtórzeń) do legendy mapy.

    Klasy kwantylowe mają w każdej klasie podobną liczbę heksagonów, więc kolory
    są dobrze wykorzystane nawet przy mocno skośnym rozkładzie.
    """
    if len(x) == 0:
        return []
    cuts = np.quantile(x, [i / k for i in range(1, k)])
    return [float(v) for v in np.unique(cuts)]


def pick_top(scores: np.ndarray, D: np.ndarray, xy: np.ndarray, min_sep_m: float,
             n: int = 5, d_quantile: float = 0.25) -> list[int]:
    """Wybiera indeksy n najlepszych miejsc (najwyższy wynik) z zachowaniem odstępu min_sep_m.

    1. Kandydaci: popyt D co najmniej na poziomie kwartyla — żeby nie polecać pustych
       terenów (lasy, pola), gdzie nie ma ani klientów, ani konkurencji (wynik bywa wysoki
       tylko dlatego, że mianownik jest mały), oraz wynik > 0.
    2. Zachłannie od najwyższego wyniku, odrzucając miejsca bliższe niż min_sep_m od
       już wybranych (tzw. non-maximum suppression) — inaczej top-5 to byłyby sąsiednie
       heksagony tego samego skupiska.
    """
    if len(scores) == 0:
        return []
    candidates = (D >= np.quantile(D, d_quantile)) & (scores > 0)
    order = [i for i in np.argsort(-scores, kind="stable") if candidates[i]]
    chosen: list[int] = []
    for i in order:
        if len(chosen) == n:
            break
        if all(np.hypot(*(xy[i] - xy[j])) >= min_sep_m for j in chosen):
            chosen.append(int(i))
    return chosen

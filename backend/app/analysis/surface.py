"""Rdzeń analizy v3: powierzchnie ciągłe liczone na regularnej siatce w EPSG:2180.

Trzy wielkości dla każdego punktu siatki g (każde źródło popytu i = środek komórki z ludnością,
każdy konkurent k = firma z OpenStreetMap):

* P(g) „Gdzie są klienci”   = Σ_i d_i · f(d_ig)                       — dostępny popyt,
* K(g) „Gdzie są firmy”     = Σ_k f(d_kg)                              — zagęszczenie konkurencji,
* E(g) „Gdzie otworzyć”     = Σ_i d_i · f(d_ig) / (f(d_ig) + C_i + A0) — model Huffa.

Rozpad odległości f(d) = exp(−d / zasięg): im dalej, tym mniejsza chęć dotarcia do firmy.
"""
import math

import numpy as np
from scipy.spatial import cKDTree

# „Inne możliwości” w modelu Huffa (opcja zewnętrzna): firmy spoza OSM, zakupy gdzie indziej itp.
# exp(−1) = tyle co jeden konkurent oddalony dokładnie o zasięg klienta. Dzięki temu w miejscu
# bez konkurencji klienci nie wybierają nowej firmy w 100% — a braki w OSM są trochę „rekompensowane”.
A0 = math.exp(-1)

CUTOFF = 4          # po przekroczeniu 4·zasięg uznajemy wpływ za zerowy (exp(−4) ≈ 2%)
BLOCK = 2_000       # tyle punktów siatki liczymy naraz (żeby nie zjeść pamięci)


def decay(d_m: np.ndarray, reach_m: float) -> np.ndarray:
    """Rozpad wykładniczy f(d) = exp(−d/zasięg); 0 dla d > 4·zasięg."""
    d = np.asarray(d_m, dtype=float)
    return np.where(d > CUTOFF * reach_m, 0.0, np.exp(-d / reach_m))


def make_grid(center_xy: np.ndarray, radius_m: float, divisions: int = 90):
    """Regularna siatka punktów pokrywająca okrąg. Zwraca (xy, maska „w okręgu”, cell_m, nx, ny).

    Krok = promień/`divisions` (domyślnie 90) ograniczony do 50–300 m (do ok. 25 tys. punktów w okręgu). Punkty leżą wierszami od północy (tak jak piksele
    obrazu), więc tablicę wartości można od razu narysować.
    """
    cell = min(max(radius_m / divisions, 50.0), 300.0)
    n = math.ceil(2 * radius_m / cell)
    half = n * cell / 2
    xs = center_xy[0] - half + cell / 2 + np.arange(n) * cell
    ys = center_xy[1] + half - cell / 2 - np.arange(n) * cell
    gx, gy = np.meshgrid(xs, ys)                         # wiersze = kolejne y (od północy)
    xy = np.column_stack([gx.ravel(), gy.ravel()])
    mask = np.hypot(xy[:, 0] - center_xy[0], xy[:, 1] - center_xy[1]) <= radius_m
    return xy, mask, cell, n, n


def _sum_by_target(grid_xy, source_xy, columns, reach_m) -> np.ndarray:
    """Dla każdego punktu siatki: Σ_j w_j · f(d_j) po źródłach j w odległości ≤ 4·zasięg.

    `columns` to lista wag źródeł (po jednej tablicy na wynik) — wiele wyników liczymy na
    TYCH SAMYCH parach (punkt, źródło), bo znalezienie par jest najdroższą częścią obliczeń.
    Punkty siatki bierzemy porcjami po BLOCK, żeby lista par nie rozrosła się w pamięci.
    Zwraca tablicę (liczba punktów, liczba kolumn).
    """
    out = np.zeros((len(grid_xy), len(columns)))
    if len(source_xy) == 0 or len(grid_xy) == 0:
        return out
    tree = cKDTree(source_xy)
    for s in range(0, len(grid_xy), BLOCK):
        part = grid_xy[s:s + BLOCK]
        pairs = cKDTree(part).sparse_distance_matrix(tree, CUTOFF * reach_m, output_type="ndarray")
        i, j = pairs["i"], pairs["j"]
        f = np.exp(-pairs["v"] / reach_m)                # pary są już obcięte do 4·zasięg (patrz decay)
        for k, w in enumerate(columns):
            out[s:s + BLOCK, k] = np.bincount(i, weights=w[j] * f, minlength=len(part))
    return out


def demand_potential(grid_xy, demand_xy, demand_w, reach_m) -> np.ndarray:
    """P(g) = Σ_i d_i · f(d_ig) — ilu klientów jest „w zasięgu”, bliżsi liczą się bardziej."""
    return _sum_by_target(grid_xy, demand_xy, [np.asarray(demand_w, float)], reach_m)[:, 0]


def competition_density(grid_xy, comp_xy, reach_m) -> np.ndarray:
    """K(g) = Σ_k f(d_kg) — im więcej firm blisko, tym wyższa wartość."""
    return _sum_by_target(grid_xy, comp_xy, [np.ones(len(comp_xy))], reach_m)[:, 0]


def competition_availability(demand_xy, comp_xy, reach_m) -> np.ndarray:
    """C_i = Σ_k f(d_ik) — „siła” istniejących konkurentów dla każdego źródła popytu i (patrz `huff_and_potential`)."""
    return _sum_by_target(demand_xy, comp_xy, [np.ones(len(comp_xy))], reach_m)[:, 0]


def huff_multi(grid_xy, demand_xy, demand_w, availability, reach_m) -> tuple[np.ndarray, np.ndarray]:
    """Model Huffa dla WIELU czynników popytu naraz na tych samych źródłach (kolumny `demand_w`: źródła × czynniki).

    Znalezienie par (punkt, źródło) jest najdroższe, a wagi czynników (np. kobiety, mężczyźni, wszyscy) tylko je mnożą,
    więc liczymy je raz. `availability` to C_i z `competition_availability` — niezależne od czynnika, więc w ETL liczone raz na typ.
    Zwraca (E, P): tablice (punkty × czynniki).
    """
    demand_w = np.asarray(demand_w, float)
    demand_w = demand_w[:, None] if demand_w.ndim == 1 else demand_w
    m = demand_w.shape[1]
    out_e, out_p = np.zeros((len(grid_xy), m)), np.zeros((len(grid_xy), m))
    if len(demand_xy) == 0 or len(grid_xy) == 0:
        return out_e, out_p
    tree = cKDTree(demand_xy)
    for s in range(0, len(grid_xy), BLOCK):
        part = grid_xy[s:s + BLOCK]
        pairs = cKDTree(part).sparse_distance_matrix(tree, CUTOFF * reach_m, output_type="ndarray")
        i, j = pairs["i"], pairs["j"]
        f = np.exp(-pairs["v"] / reach_m)
        share = f / (f + availability[j] + A0)           # szansa, że mieszkaniec j wybierze nową firmę
        for k in range(m):
            out_e[s:s + BLOCK, k] = np.bincount(i, weights=demand_w[j, k] * share, minlength=len(part))
            out_p[s:s + BLOCK, k] = np.bincount(i, weights=demand_w[j, k] * f, minlength=len(part))
    return out_e, out_p


def demand_potentials(grid_xy, demand_xy, demand_w, reach_m) -> np.ndarray:
    """P(g) dla wielu czynników naraz (kolumny `demand_w`); wynik: punkty × czynniki."""
    demand_w = np.asarray(demand_w, float)
    demand_w = demand_w[:, None] if demand_w.ndim == 1 else demand_w
    return _sum_by_target(grid_xy, demand_xy, [demand_w[:, k] for k in range(demand_w.shape[1])], reach_m)


def huff_and_potential(grid_xy, demand_xy, demand_w, comp_xy, reach_m) -> tuple[np.ndarray, np.ndarray]:
    """Model Huffa (1963) E(g) oraz potencjał popytu P(g) w jednym przebiegu po parach (punkt, źródło).

    Mieszkaniec z komórki i wybiera między wszystkimi firmami; im bliżej firma, tym większa szansa.
    Szansa wyboru NOWEJ firmy: f(d_ig) / (f(d_ig) + C_i + A0), gdzie C_i = Σ_k f(d_ik) to
    „siła” istniejących konkurentów dla tego mieszkańca, a A0 to opcja zewnętrzna.
    Wynik E(g) = Σ_i d_i · (ta szansa) — suma po komórkach popytu. Mianownik jest zawsze ≥ A0 > 0,
    więc konkurent leżący dokładnie w punkcie g nie powoduje dzielenia przez zero.
    """
    if len(demand_xy) == 0 or len(grid_xy) == 0:
        return np.zeros(len(grid_xy)), np.zeros(len(grid_xy))
    availability = competition_availability(demand_xy, comp_xy, reach_m)   # C_i raz dla każdej komórki popytu
    e, p = huff_multi(grid_xy, demand_xy, np.asarray(demand_w, float), availability, reach_m)
    return e[:, 0], p[:, 0]


def huff_expected(grid_xy, demand_xy, demand_w, comp_xy, reach_m) -> np.ndarray:
    """E(g) — szacowana liczba klientów nowej firmy w punkcie g (patrz `huff_and_potential`)."""
    return huff_and_potential(grid_xy, demand_xy, demand_w, comp_xy, reach_m)[0]


def top_points(values: np.ndarray, xy: np.ndarray, mask: np.ndarray, min_sep_m: float, n: int = 5) -> list[int]:
    """Indeksy do n największych maksimów w masce, odległych od siebie o ≥ min_sep_m (NMS).

    Bierzemy punkty od największej wartości; punkt odpada, jeśli leży za blisko już wybranego.
    Wartości ≤ 0 pomijamy (tam nic nie ma).
    """
    cand = np.flatnonzero(mask & (np.nan_to_num(values) > 0))
    cand = cand[np.argsort(-values[cand], kind="stable")]
    chosen: list[int] = []
    for i in cand:
        if all(math.hypot(xy[i, 0] - xy[c, 0], xy[i, 1] - xy[c, 1]) >= min_sep_m for c in chosen):
            chosen.append(int(i))
            if len(chosen) == n:
                break
    return chosen


def round_significant(values: np.ndarray, digits: int = 3) -> np.ndarray:
    """Zaokrąglenie do `digits` cyfr znaczących (mniejsza odpowiedź JSON).

    Zostawiamy 3 cyfry, a nie 2: przy 2 cyfrach gładko zmieniająca się powierzchnia dostawała widoczne
    „schodki” (pierścienie jednego koloru) po zamianie na mgłę.
    """
    v = np.asarray(values, dtype=float)
    out = np.zeros_like(v)
    nz = v != 0                                          # wartości ujemne (spadek trendu) zaokrąglamy tak samo
    size = np.abs(v[nz])
    scale = 10.0 ** (np.floor(np.log10(size)) - (digits - 1))
    out[nz] = np.sign(v[nz]) * np.round(size / scale) * scale
    return out

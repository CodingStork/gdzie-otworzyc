"""Rdzeń analizy v3: powierzchnie ciągłe liczone na regularnej siatce w EPSG:2180.

Trzy wielkości dla każdego punktu siatki g (każde źródło popytu i = środek komórki z ludnością,
każdy konkurent k = firma z OpenStreetMap):

* P(g) „Gdzie są klienci”   = Σ_i d_i · [d_ig ≤ zasięg]               — ilu klientów mieszka w zasięgu od punktu,
* K(g) „Gdzie są firmy”     = Σ_k [d_kg ≤ zasięg]                      — ile firm jest w zasięgu od punktu,
* E(g) „Gdzie otworzyć”     = Σ_i d_i · f(d_ig) / (f(d_ig) + C_i + A0) — model Huffa.

P i K to sumy w ruchomym oknie (okrąg o promieniu zasięgu przesuwany po mapie): kolor mapy w punkcie to dokładnie ta liczba,
którą pokazuje dymek po kliknięciu („W promieniu 1,5 km: …”). Wcześniej P i K też miały rozpad z odległością i liczyły ludzi
do 4 · zasięg — kolor mówił „2 nowe bloki”, a dymek „w promieniu 1 km: 0” (uwaga Marcina, v3.7).
W modelu Huffa rozpad odległości f(d) = exp(−d / zasięg) zostaje: to jego istota — bliższa firma przyciąga mocniej.
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
MAX_GRID_POINTS = 250_000   # górny limit punktów siatki w okręgu (pomiar: okrąg 240 km, zasięg 1 km — ok. 8 s)


def decay(d_m: np.ndarray, reach_m: float) -> np.ndarray:
    """Rozpad wykładniczy f(d) = exp(−d/zasięg); 0 dla d > 4·zasięg."""
    d = np.asarray(d_m, dtype=float)
    return np.where(d > CUTOFF * reach_m, 0.0, np.exp(-d / reach_m))


def grid_step(radius_m: float, divisions: int = 90, reach_m: float | None = None, max_points: int = MAX_GRID_POINTS) -> float:
    """Krok siatki w metrach — zasady opisane w `make_grid`."""
    cell = max(radius_m / divisions, 50.0)
    if reach_m:
        cell = min(cell, max(reach_m / 2, 50.0))
    return max(cell, math.sqrt(math.pi * radius_m ** 2 / max_points))   # limit liczby punktów w okręgu


def make_grid(center_xy: np.ndarray, radius_m: float, divisions: int = 90, reach_m: float | None = None,
              max_points: int = MAX_GRID_POINTS):
    """Regularna siatka punktów pokrywająca okrąg. Zwraca (xy, maska „w okręgu”, cell_m, nx, ny).

    Krok = promień/`divisions` (domyślnie 90, czyli ok. 180 punktów w poprzek), co najmniej 50 m — ALE nie większy niż pół zasięgu
    klienta (`reach_m`): mapa „ilu klientów w zasięgu” sprawdza okrąg o promieniu zasięgu w każdym punkcie siatki, więc punkty muszą
    leżeć gęściej niż ten okrąg, inaczej między nimi zostają dziury, a kolor nie zgadza się z liczbą w dymku (uwaga Marcina, v3.7:
    okrąg 240 km, zasięg 1 km, punkty co 2,7 km → w sąsiednich punktach 10, 3 i 1). Punktów w okręgu jest najwyżej `max_points`
    (czas liczenia) — przy ogromnym obszarze i bardzo małym zasięgu krok jest wtedy większy niż pół zasięgu i serwis podnosi zasięg
    (patrz `run_surface`). Punkty leżą wierszami od północy (tak jak piksele obrazu), więc tablicę wartości można od razu narysować.
    """
    cell = grid_step(radius_m, divisions, reach_m, max_points)
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


def window_sum(grid_xy, source_xy, columns, radius_m) -> np.ndarray:
    """Suma w ruchomym oknie: dla każdego punktu siatki Σ_j w_j po źródłach j w odległości ≤ radius_m (bez rozpadu).

    Tak samo jak `_sum_by_target`: wiele kolumn wag na tych samych parach, punkty porcjami po BLOCK. Zwraca (punkty × kolumny).
    """
    out = np.zeros((len(grid_xy), len(columns)))
    if len(source_xy) == 0 or len(grid_xy) == 0:
        return out
    tree = cKDTree(source_xy)
    for s in range(0, len(grid_xy), BLOCK):
        part = grid_xy[s:s + BLOCK]
        pairs = cKDTree(part).sparse_distance_matrix(tree, radius_m, output_type="ndarray")
        for k, w in enumerate(columns):
            out[s:s + BLOCK, k] = np.bincount(pairs["i"], weights=w[pairs["j"]], minlength=len(part))
    return out


def demand_potential(grid_xy, demand_xy, demand_w, reach_m) -> np.ndarray:
    """P(g) = Σ_i d_i · [d_ig ≤ zasięg] — ilu klientów mieszka w zasięgu od punktu g (ta sama liczba co w dymku)."""
    return window_sum(grid_xy, demand_xy, [np.asarray(demand_w, float)], reach_m)[:, 0]


def competition_density(grid_xy, comp_xy, reach_m) -> np.ndarray:
    """K(g) = Σ_k [d_kg ≤ zasięg] — ile firm jest w zasięgu od punktu g."""
    return window_sum(grid_xy, comp_xy, [np.ones(len(comp_xy))], reach_m)[:, 0]


def competition_availability(demand_xy, comp_xy, reach_m) -> np.ndarray:
    """C_i = Σ_k f(d_ik) — „siła” istniejących konkurentów dla każdego źródła popytu i (patrz `huff_and_potential`)."""
    return _sum_by_target(demand_xy, comp_xy, [np.ones(len(comp_xy))], reach_m)[:, 0]


def huff_multi(grid_xy, demand_xy, demand_w, availability, reach_m) -> tuple[np.ndarray, np.ndarray]:
    """Model Huffa dla WIELU czynników popytu naraz na tych samych źródłach (kolumny `demand_w`: źródła × czynniki).

    Znalezienie par (punkt, źródło) jest najdroższe, a wagi czynników (np. kobiety, mężczyźni, wszyscy) tylko je mnożą,
    więc liczymy je raz. `availability` to C_i z `competition_availability` — niezależne od czynnika, więc w ETL liczone raz na typ.
    Zwraca (E, P): tablice (punkty × czynniki); P to suma w oknie o promieniu zasięgu (jak `demand_potential`).
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
            out_p[s:s + BLOCK, k] = np.bincount(i, weights=demand_w[j, k] * (pairs["v"] <= reach_m), minlength=len(part))
    return out_e, out_p


def demand_potentials(grid_xy, demand_xy, demand_w, reach_m) -> np.ndarray:
    """P(g) dla wielu czynników naraz (kolumny `demand_w`); wynik: punkty × czynniki."""
    demand_w = np.asarray(demand_w, float)
    demand_w = demand_w[:, None] if demand_w.ndim == 1 else demand_w
    return window_sum(grid_xy, demand_xy, [demand_w[:, k] for k in range(demand_w.shape[1])], reach_m)


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


def peaks_and_edge(values: np.ndarray, mask: np.ndarray, nx: int, ny: int) -> tuple[np.ndarray, np.ndarray]:
    """Lokalne szczyty i krawędź obszaru na siatce `ny × nx` (wiersze od północy, jak w `make_grid`).

    Szczyt = punkt w obszarze, którego wszyscy 8 sąsiedzi też są w obszarze i żaden nie ma większej wartości. Punkt przy
    krawędzi okręgu/prostokąta, gdzie wartości rosną NA ZEWNĄTRZ, nie jest szczytem — najlepsze miejsce leży wtedy poza
    obszarem, a „najlepsze miejsce na krawędzi” byłoby przypadkowym punktem stoku (artefakt granicy, nie wynik).
    Zwraca (maska szczytów, maska krawędzi = punkty w obszarze z co najmniej jednym sąsiadem poza nim).
    """
    v = np.where(mask, np.nan_to_num(np.asarray(values, float)), np.nan).reshape(ny, nx)
    inside = np.asarray(mask, bool).reshape(ny, nx)
    padded_v = np.pad(v, 1, constant_values=np.nan)
    padded_in = np.pad(inside, 1, constant_values=False)
    all_neighbours_inside = inside.copy()
    highest = inside.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            nb_in = padded_in[1 + dy:1 + dy + ny, 1 + dx:1 + dx + nx]
            nb_v = padded_v[1 + dy:1 + dy + ny, 1 + dx:1 + dx + nx]
            all_neighbours_inside &= nb_in
            highest &= ~nb_in | (v >= nb_v)
    peaks = all_neighbours_inside & highest
    edge = inside & ~all_neighbours_inside
    return peaks.ravel(), edge.ravel()


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

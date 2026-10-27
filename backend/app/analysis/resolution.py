"""Poziomy szczegółowości (LOD): jaką siatkę H3 pokazać i na jakiej ją policzyć.

Dwa pojęcia:
  * `display_res` — rozdzielczość heksagonów NARYSOWANYCH na mapie; zależy od przybliżenia (zoomu),
    żeby heksagony miały na ekranie mniej więcej stały rozmiar;
  * `compute_res` — rozdzielczość, na której LICZYMY (nie grubsza niż display_res): im drobniej, tym
    dokładniej odwzorowany okrąg zasięgu, ale tym więcej komórek i par do przetworzenia.
"""
import math

# Przybliżony odstęp między środkami sąsiednich heksagonów H3 [km] w Polsce.
HEX_SPACING_KM = {9: 0.30, 8: 0.80, 7: 2.11, 6: 5.6, 5: 14.8}

# Średnie pole komórki H3 [km²] — do szacowania kosztu obliczeń.
CELL_AREA_KM2 = {9: 0.105, 8: 0.737, 7: 5.16, 6: 36.1, 5: 252.9}

# Bbox przyciągamy do siatki o tym kroku [stopnie], zależnie od display_res (patrz snap_bbox).
SNAP_DEG = {5: 2.0, 6: 1.0, 7: 0.5, 8: 0.25, 9: 0.1}

MAX_CELLS = 800_000        # tyle komórek (obszar + bufor) liczymy najwyżej
MAX_PAIRS = 30_000_000     # i tyle par (komórka, sąsiad w okręgu zasięgu)


def display_res_for_zoom(zoom: int) -> int:
    """Rozdzielczość rysowanych heksagonów dla zoomu mapy: ≤6 → 5, 7–8 → 6, 9 → 7, 10–11 → 8, ≥12 → 9."""
    if zoom <= 6:
        return 5
    if zoom <= 8:
        return 6
    if zoom == 9:
        return 7
    if zoom <= 11:
        return 8
    return 9


def snap_bbox(bbox: tuple[float, float, float, float], res: int) -> tuple[float, float, float, float]:
    """Rozszerza bbox (minLng, minLat, maxLng, maxLat) NA ZEWNĄTRZ do wielokrotności kroku SNAP_DEG[res].

    Po co: użytkownik przesuwa mapę o drobny kawałek, a bbox zmienia się za każdym razem. Po
    przyciągnięciu do siatki małe przesunięcia dają TEN SAM bbox, więc wynik wraca z pamięci
    podręcznej (szybko), a percentyle i kolory nie „skaczą” przy każdym ruchu myszy.
    """
    step = SNAP_DEG[res]
    eps = 1e-9   # odporność na błędy zmiennoprzecinkowe przy wartościach już leżących na siatce
    min_lng, min_lat, max_lng, max_lat = bbox
    return (round(math.floor(min_lng / step + eps) * step, 6), round(math.floor(min_lat / step + eps) * step, 6),
            round(math.ceil(max_lng / step - eps) * step, 6), round(math.ceil(max_lat / step - eps) * step, 6))


def area_km2(bbox: tuple[float, float, float, float], buffer_km: float = 0.0) -> float:
    """Pole prostokąta bbox powiększonego z każdej strony o buffer_km [km²].

    1° szerokości ≈ 110,54 km, 1° długości ≈ 111,32 km · cos(szerokość środka).
    """
    min_lng, min_lat, max_lng, max_lat = bbox
    width = (max_lng - min_lng) * 111.32 * math.cos(math.radians((min_lat + max_lat) / 2)) + 2 * buffer_km
    height = (max_lat - min_lat) * 110.54 + 2 * buffer_km
    return max(width, 0.0) * max(height, 0.0)


def choose_compute_res(bbox: tuple[float, float, float, float], radius_km: float, display_res: int) -> int:
    """Najdrobniejsza rozdzielczość (9, 8, …, display_res), na której obliczenia mieszczą się w limitach.

    Koszt ma dwa składniki: liczba komórek obszaru z buforem r (musimy je wszystkie wczytać) oraz
    liczba PAR (komórka, sąsiad w okręgu) — okrąg o promieniu r obejmuje ok. πr²/pole_komórki
    sąsiadów. Gdy żadna drobna rozdzielczość się nie mieści, zostajemy przy display_res.
    """
    area = area_km2(bbox, radius_km)
    for res in range(9, display_res - 1, -1):
        cells = area / CELL_AREA_KM2[res]
        pairs = cells * max(1.0, math.pi * radius_km ** 2 / CELL_AREA_KM2[res])
        if cells <= MAX_CELLS and pairs <= MAX_PAIRS:
            return res
    return display_res


# ---- v1 (zostaje do Task 5, kiedy service.py przestanie z tego korzystać) ----

def choose_resolution(radius_km: float | None) -> int:
    """Im większy obszar, tym grubsza siatka (mniej heksagonów = szybciej i czytelniej).

    None oznacza "cała Polska" → res 6 (~9 tys. heksagonów).
    """
    if radius_km is None:
        return 6
    if radius_km <= 15:
        return 8
    return 7  # 15–50 km


def effective_bandwidth_km(bandwidth_km: float, res: int) -> float:
    """Szerokość pasma jądra nie może być mniejsza niż ~0,6 odstępu heksagonów.

    Przy zbyt wąskim jądrze każdy heksagon "widziałby" tylko samego siebie, a wynik
    zależałby od przypadkowego położenia siatki (problem MAUP).
    """
    return max(bandwidth_km, 0.6 * HEX_SPACING_KM[res])

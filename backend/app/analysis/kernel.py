"""Sumy w zasięgu klienta na współrzędnych metrycznych.

v2 (`catchment_sums`): suma wartości źródeł w OKRĘGU o promieniu = zasięg klienta. To klasyczna
metoda 2SFCA (two-step floating catchment area) z progiem odległości: dla każdego miejsca okrąg
zasięgu „pływa” po mapie, a my zliczamy w nim popyt (mieszkańców) i podaż (konkurentów). Liczby są
całkowite i sprawdzalne — w odróżnieniu od v1, gdzie źródła ważyło jądro Gaussa (K(d) = exp(-d²/2h²)):
dla klienta „kilka razy dalej niż zasięg” waga wciąż była niezerowa, a sumy nie dało się zweryfikować.
"""
import numpy as np
from pyproj import Transformer
from scipy.sparse import coo_matrix
from scipy.spatial import cKDTree

# Odległości liczymy w EPSG:2180 (PUWG 1992) — układ metryczny dla całej Polski.
# W WGS84 (stopnie) 1° długości geograficznej ma różną długość zależnie od szerokości,
# więc odległość euklidesowa na stopniach byłaby zniekształcona.
_TO_2180 = Transformer.from_crs(4326, 2180, always_xy=True)


def to_metric(lat: np.ndarray, lng: np.ndarray) -> np.ndarray:
    """Zamienia współrzędne geograficzne (WGS84) na metry w EPSG:2180; wynik N×2 (x, y)."""
    x, y = _TO_2180.transform(np.asarray(lng, dtype=float), np.asarray(lat, dtype=float))
    return np.column_stack([x, y])


def catchment_sums(target_xy: np.ndarray, source_xy: np.ndarray, values: np.ndarray, radius_m: float) -> np.ndarray:
    """Dla każdego celu: suma values[j] źródeł w odległości ≤ radius_m (okrąg zasięgu, bez wag).

    `values` ma kształt (M,) albo (M, k). Źródło leżące w tym samym punkcie co cel (odległość 0)
    zawsze się liczy. Cele przetwarzamy porcjami, żeby lista par (cel, źródło) nie rozrosła się
    ponad pamięć — rozmiar porcji dobieramy z szacowanej liczby sąsiadów w okręgu.
    """
    values = np.asarray(values, dtype=float)
    out = np.zeros((len(target_xy),) + values.shape[1:])
    if len(source_xy) == 0 or len(target_xy) == 0:
        return out

    sources = cKDTree(source_xy)
    extent = np.ptp(source_xy, axis=0)
    density = len(source_xy) / max(extent[0] * extent[1], 1.0)               # źródeł na m²
    neighbours = max(1.0, density * np.pi * radius_m ** 2)                   # średnio w okręgu
    chunk = int(min(max(2_000_000 / neighbours, 1_000), 200_000))            # ~2 mln par na porcję

    for start in range(0, len(target_xy), chunk):
        part = target_xy[start:start + chunk]
        # Wszystkie pary (cel, źródło) w odległości ≤ radius: drzewa przeszukują tylko sąsiedztwo,
        # zamiast liczyć N×M odległości.
        pairs = cKDTree(part).sparse_distance_matrix(sources, radius_m, output_type="ndarray")
        mask = coo_matrix((np.ones(len(pairs)), (pairs["i"], pairs["j"])), shape=(len(part), len(source_xy)))
        out[start:start + chunk] = np.asarray(mask @ values).reshape((len(part),) + values.shape[1:])
    return out

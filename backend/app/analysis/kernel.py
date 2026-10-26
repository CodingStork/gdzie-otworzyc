"""Sumy ważone jądrem Gaussa (estymacja jądrowa, KDE) na współrzędnych metrycznych.

Dla punktu docelowego i sumujemy wartości źródeł j z wagą zależną od odległości:
    K(d) = exp(-d² / (2h²)),   d = odległość, h = szerokość pasma ("zasięg klienta")
Źródła dalsze niż 3h pomijamy — ich waga jest już praktycznie zerowa (< 1,2%).
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


def kernel_sums(target_xy: np.ndarray, source_xy: np.ndarray, values: np.ndarray, bandwidth_m: float) -> np.ndarray:
    """Dla każdego celu: suma values[j] · K(odległość do źródła j).

    `values` ma kształt (M,) albo (M, k) — wtedy liczymy k sum naraz (np. popyt i konkurencja).
    Wynik ma kształt (N,) albo (N, k).
    """
    values = np.asarray(values, dtype=float)
    out_shape = (len(target_xy),) + values.shape[1:]
    if len(source_xy) == 0 or len(target_xy) == 0:
        return np.zeros(out_shape)

    radius = 3 * bandwidth_m  # obcięcie jądra
    targets, sources = cKDTree(target_xy), cKDTree(source_xy)
    # Wszystkie pary (cel, źródło) bliższe niż radius — drzewa przeszukują tylko sąsiedztwo,
    # zamiast liczyć N×M odległości.
    pairs = targets.sparse_distance_matrix(sources, radius, output_type="ndarray")
    weights = np.exp(-(pairs["v"] ** 2) / (2 * bandwidth_m ** 2))
    w = coo_matrix((weights, (pairs["i"], pairs["j"])), shape=(len(target_xy), len(source_xy)))
    return np.asarray(w @ values).reshape(out_shape)

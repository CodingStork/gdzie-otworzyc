"""Współrzędne metryczne: przeliczanie WGS84 (stopnie) ↔ EPSG:2180 (metry)."""
import numpy as np
from pyproj import Transformer

# Odległości liczymy w EPSG:2180 (PUWG 1992) — układ metryczny dla całej Polski.
# W WGS84 (stopnie) 1° długości geograficznej ma różną długość zależnie od szerokości,
# więc odległość euklidesowa na stopniach byłaby zniekształcona.
_TO_2180 = Transformer.from_crs(4326, 2180, always_xy=True)
_FROM_2180 = Transformer.from_crs(2180, 4326, always_xy=True)


def to_metric(lat: np.ndarray, lng: np.ndarray) -> np.ndarray:
    """Zamienia współrzędne geograficzne (WGS84) na metry w EPSG:2180; wynik N×2 (x, y)."""
    x, y = _TO_2180.transform(np.asarray(lng, dtype=float), np.asarray(lat, dtype=float))
    return np.column_stack([x, y])


def to_latlng(xy: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Odwrotność `to_metric`: metry w EPSG:2180 → (lat, lng) w stopniach."""
    xy = np.asarray(xy, dtype=float).reshape(-1, 2)
    lng, lat = _FROM_2180.transform(xy[:, 0], xy[:, 1])
    return np.asarray(lat), np.asarray(lng)

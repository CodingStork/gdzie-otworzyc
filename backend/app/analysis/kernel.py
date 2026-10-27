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


class LocalFrame:
    """Lokalny układ metryczny (odwzorowanie poprzeczne Merkatora) z początkiem w wybranym miejscu.

    Siatka mgły musi mieć osie równoległe do południków i równoleżników — inaczej obraz rozciągany
    przez Leaflet między narożnikami w stopniach byłby obrócony względem podkładu (w EPSG:2180 nawet o ok. 4°
    na zachodzie i wschodzie kraju). W promieniu 30 km zniekształcenie długości tego układu jest pomijalne.
    """

    def __init__(self, lat: float, lng: float):
        crs = f"+proj=tmerc +lat_0={lat} +lon_0={lng} +k=1 +x_0=0 +y_0=0 +ellps=GRS80 +units=m"
        self._to = Transformer.from_crs(4326, crs, always_xy=True)
        self._from = Transformer.from_crs(crs, 4326, always_xy=True)

    def to_metric(self, lat, lng) -> np.ndarray:
        x, y = self._to.transform(np.asarray(lng, dtype=float), np.asarray(lat, dtype=float))
        return np.column_stack([x, y])

    def to_latlng(self, xy) -> tuple[np.ndarray, np.ndarray]:
        xy = np.asarray(xy, dtype=float).reshape(-1, 2)
        lng, lat = self._from.transform(xy[:, 0], xy[:, 1])
        return np.asarray(lat), np.asarray(lng)

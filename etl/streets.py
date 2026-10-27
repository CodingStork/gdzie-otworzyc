"""Ulice z OpenStreetMap → tabela `streets(name, lat, lng)` do nazywania lokalizacji (np. „ul. Długa, Zaodrze”).

Wzdłuż każdej drogi z nazwą stawiamy punkty co ok. 100 m. Dzięki temu „najbliższa ulica” to zwykłe
szukanie najbliższego punktu, bez geometrii linii w bazie. Tabela jest posortowana po szerokości
geograficznej, więc zapytanie o prostokąt (`WHERE lat BETWEEN …`) czyta tylko kilka bloków pliku.
"""
import math

import duckdb
import osmium
import pandas as pd

# Drogi, przy których ktoś może mieszkać lub prowadzić sklep (bez dróg serwisowych, polnych, ścieżek).
HIGHWAYS = {"primary", "secondary", "tertiary", "unclassified", "residential", "living_street", "pedestrian"}
STEP_M = 100


def sample_line(coords: list[tuple[float, float]], step_m: float = STEP_M) -> list[tuple[float, float]]:
    """Punkty (lat, lng) wzdłuż linii łamanej, co ok. `step_m`, każdy w środku swojego odcinka.

    Linię o długości L dzielimy na n = ⌈L / krok⌉ równych odcinków i bierzemy środek każdego —
    krótka uliczka dostaje jeden punkt (swój środek), a żaden punkt linii nie jest dalej niż ok. 50 m od próbki.
    Odległości liczymy w lokalnym rzucie płaskim (1° szerokości ≈ 111 320 m, długość skalowana cosinusem).
    """
    lat0 = sum(c[0] for c in coords) / len(coords)
    kx, ky = 111_320 * math.cos(math.radians(lat0)), 110_540
    cumulative = [0.0]
    for (a_lat, a_lng), (b_lat, b_lng) in zip(coords, coords[1:]):
        cumulative.append(cumulative[-1] + math.hypot((b_lng - a_lng) * kx, (b_lat - a_lat) * ky))
    total = cumulative[-1]
    if total == 0:
        return [coords[0]]
    n = math.ceil(total / step_m)
    points, seg = [], 0
    for k in range(n):
        target = (k + 0.5) * total / n
        while cumulative[seg + 1] < target:               # odcinek łamanej, na którym leży ten punkt
            seg += 1
        t = (target - cumulative[seg]) / (cumulative[seg + 1] - cumulative[seg])
        (a_lat, a_lng), (b_lat, b_lng) = coords[seg], coords[seg + 1]
        points.append((a_lat + t * (b_lat - a_lat), a_lng + t * (b_lng - a_lng)))
    return points


def extract_streets(pbf_path) -> pd.DataFrame:
    """Kolumny: name, lat, lng — punkty wzdłuż nazwanych dróg z listy `HIGHWAYS`."""
    rows = []
    processor = (osmium.FileProcessor(str(pbf_path), osmium.osm.NODE | osmium.osm.WAY)
                 .with_locations()
                 .with_filter(osmium.filter.KeyFilter("highway")))
    for way in processor:
        if not way.is_way():                       # KeyFilter przepuszcza też pojedyncze punkty z tagiem highway
            continue
        name = way.tags.get("name")
        if not name or way.tags.get("highway") not in HIGHWAYS:
            continue
        coords = [(n.lat, n.lon) for n in way.nodes if n.location.valid()]
        if len(coords) < 2:
            continue
        rows.extend((name, lat, lng) for lat, lng in sample_line(coords))
    return pd.DataFrame(rows, columns=["name", "lat", "lng"])


def build_streets_table(pbf_path, con: duckdb.DuckDBPyConnection) -> int:
    """Zapisuje tabelę `streets(name, lat, lng)` posortowaną po lat; zwraca liczbę punktów."""
    streets = extract_streets(pbf_path)
    con.register("streets_in", streets)
    con.execute("CREATE OR REPLACE TABLE streets AS SELECT * FROM streets_in ORDER BY lat")
    con.unregister("streets_in")
    return len(streets)

"""Syntetyczna baza do testów E2E: dwa miasta i kilka wsi w okolicach Brzegu i Opola (liczby WYMYŚLONE, nie prawdziwe dane).

Wystarczy, żeby przeklikać aplikację jak użytkownik: są mieszkańcy, salony, sklepy, nazwy miejsc, ulice, pozwolenia,
luki w danych (krok `gaps`) i gotowa mapa Polski (krok `national`, potrzebna dla dużych obszarów).
"""
import math
import random
from pathlib import Path

import h3

from tests.factories import make_db

BRZEG = (50.861, 17.467)
OPOLE = (50.668, 17.926)
VILLAGES = [("Skarbimierz", (50.85, 17.42)), ("Lubsza", (50.92, 17.52)), ("Olszanka", (50.80, 17.40)),
            ("Lewin Brzeski", (50.75, 17.62)), ("Popielów", (50.83, 17.73)), ("Dąbrowa", (50.69, 17.75))]


def _km(a, b):
    return math.hypot((a[0] - b[0]) * 111, (a[1] - b[1]) * 70)


def build(path: Path) -> Path:
    rnd = random.Random(7)
    pop: dict[str, float] = {}

    def town(center, k, peak, scale, floor):
        for cell in h3.grid_disk(h3.latlng_to_cell(*center, 9), k):
            pop[cell] = pop.get(cell, 0) + peak * math.exp(-_km(h3.cell_to_latlng(cell), center) / scale) + floor

    town(BRZEG, 16, 700, 1.0, 15)
    town(OPOLE, 24, 1400, 2.2, 25)
    for _, c in VILLAGES:
        town(c, 5, 60, 0.6, 5)

    pois = []

    def scatter(type_id, center, n, sigma_km):
        for _ in range(n):
            pois.append((type_id, center[0] + rnd.gauss(0, sigma_km / 111), center[1] + rnd.gauss(0, sigma_km / 70),
                         "overture" if rnd.random() < 0.5 else "osm"))

    for type_id, n_brzeg, n_opole in (("beauty", 30, 160), ("hairdresser", 22, 110), ("grocery", 40, 170), ("cafe", 9, 70)):
        scatter(type_id, BRZEG, n_brzeg, 0.9)
        scatter(type_id, OPOLE, n_opole, 2.0)
    places = [("Brzeg", "town", *BRZEG), ("Opole", "city", *OPOLE)] + [(n, "village", *c) for n, c in VILLAGES]
    streets = [(name, BRZEG[0] + i * 0.0012, BRZEG[1] + j * 0.0018)
               for i in range(-20, 21) for j in range(-20, 21)
               for name in [["Długa", "Krótka", "Polna", "Lipowa"][(i + j) % 4]]]
    permits = [(*h3.cell_to_latlng(c), month, "sf", rnd.randint(1, 3))
               for c in list(pop)[::9] for month in ("2025-01-01", "2026-02-01", "2026-09-01") if rnd.random() < 0.4]
    meta = [("osm", "synthetic", "2026-11-03 00:00:00", 1), ("census", "synthetic", "2026-11-03 00:00:00", 1)]
    return make_db(path, pop=pop, pois=pois, permits=permits, places=places, streets=streets, meta=meta, gaps=True, national=True)

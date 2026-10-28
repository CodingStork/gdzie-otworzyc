"""Plan warstw gotowej mapy Polski (tryb „Cała Polska”): nazwy kolumn i zadania obliczeniowe ETL.

Wspólne dla ETL (`etl/national.py` liczy warstwy) i API (`/api/national` wybiera warstwę po nazwie), więc nazwy
i zasięgi nie mogą się rozjechać. Zasięg gotowej mapy to zasięg typowy: z wybraną branżą — `bandwidth_km` typu,
bez branży — `default_reach_km` czynnika popytu; tak samo podnoszony do minimum (0,3 km, dla pozwoleń 1 km) jak w `/api/surface`.
"""
from dataclasses import dataclass

from backend.app.analysis.service import effective_reach_km
from backend.app.catalog import DEFAULT_MONTHS, DEMANDS, TYPES


def reach_label(km: float) -> str:
    return f"{km:g}"


def open_layer(type_id: str, demand_id: str) -> str:
    return f"open__{type_id}__{demand_id}"


def comp_layer(type_id: str) -> str:
    return f"comp__{type_id}"


def demand_layer(demand_id: str, reach_km: float) -> str:
    return f"demand__{demand_id}__{reach_label(reach_km)}"


def trend_layer(demand_id: str) -> str:
    return f"trend__{demand_id}"


def is_trend(layer: str) -> bool:
    return layer.startswith("trend__")


def national_reach_km(type_id: str | None, demand_id: str | None) -> float:
    """Zasięg, dla którego liczymy gotową mapę Polski przy takim wyborze (typ i/lub czynnik popytu)."""
    base = TYPES[type_id].bandwidth_km if type_id else DEMANDS[demand_id].default_reach_km
    return effective_reach_km(demand_id, base)


def layers_for(type_id: str | None, demand_id: str | None) -> tuple[dict[str, str], float]:
    """Nazwy warstw gotowej mapy dla wyboru użytkownika: ({logiczna warstwa → kolumna}, zasięg w km).

    Logiczne warstwy jak w `/api/surface`: "open", "demand", "competition", "trend". Brakującej warstwy nie ma w wyniku
    (np. „Gdzie otworzyć” dla czynnika spoza `suggested_demands` typu — wtedy mapę trzeba policzyć na żywo).
    """
    reach = national_reach_km(type_id, demand_id)
    layers: dict[str, str] = {}
    if type_id and demand_id:
        if demand_id in TYPES[type_id].suggested_demands:
            layers["open"] = open_layer(type_id, demand_id)
    elif type_id:
        layers["competition"] = comp_layer(type_id)
    if demand_id:
        layers["demand"] = demand_layer(demand_id, reach)
        if DEMANDS[demand_id].source == "permits":
            layers["trend"] = trend_layer(demand_id)
    return layers, reach


@dataclass(frozen=True)
class Job:
    """Jedno przejście obliczeń po punktach Polski; `outputs` to warstwy, które z niego powstają."""
    kind: str                       # "huff" (typ × czynniki), "comp" (zagęszczenie firm), "potential" (sam popyt), "trend"
    family: str | None              # "census" / "permits" — z jakiej tabeli pochodzą źródła popytu
    reach_km: float
    type_id: str | None
    demands: tuple[str, ...]
    outputs: tuple[str, ...]


def _family(demand_id: str) -> str:
    return DEMANDS[demand_id].source


def jobs() -> list[Job]:
    """Wszystkie zadania ETL w kolejności; kolejne mogą pomijać warstwy policzone wcześniej (ten sam popyt i zasięg)."""
    out: list[Job] = []
    for t in TYPES.values():
        for family in ("census", "permits"):
            ds = tuple(d for d in t.suggested_demands if _family(d) == family)
            if not ds:
                continue
            reach = effective_reach_km(ds[0], t.bandwidth_km)
            outputs = tuple(open_layer(t.id, d) for d in ds) + tuple(demand_layer(d, reach) for d in ds)
            out.append(Job("huff", family, reach, t.id, ds, outputs))
        out.append(Job("comp", None, effective_reach_km(None, t.bandwidth_km), t.id, (), (comp_layer(t.id),)))
    # sam popyt (bez branży): zasięg domyślny czynnika, czynniki o tym samym zasięgu liczymy razem
    groups: dict[tuple[str, float], list[str]] = {}
    for d in DEMANDS.values():
        groups.setdefault((d.source, effective_reach_km(d.id, d.default_reach_km)), []).append(d.id)
    for (family, reach), ds in groups.items():
        out.append(Job("potential", family, reach, None, tuple(ds), tuple(demand_layer(d, reach) for d in ds)))
    for d in DEMANDS.values():
        if d.source == "permits":
            out.append(Job("trend", "permits", effective_reach_km(d.id, d.default_reach_km), None, (d.id,), (trend_layer(d.id),)))
    return out


def expected_layers() -> list[str]:
    """Wszystkie warstwy, które po kroku `national` muszą istnieć (bez powtórzeń, w kolejności zadań)."""
    seen: dict[str, None] = {}
    for job in jobs():
        for layer in job.outputs:
            seen.setdefault(layer, None)
    return list(seen)


def layer_months(layer: str) -> int | None:
    """Okno pozwoleń (miesiące) dla warstwy zależnej od pozwoleń; None dla pozostałych."""
    parts = layer.split("__")
    demand_id = parts[2] if parts[0] == "open" else parts[1] if parts[0] in ("demand", "trend") else None
    if demand_id and DEMANDS[demand_id].source == "permits":
        return DEFAULT_MONTHS
    return None

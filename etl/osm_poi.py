"""OpenStreetMap → tabele `poi` (firmy wg typów z katalogu) i `places` (nazwy miejscowości/osiedli).

Źródło to ekstrakt Geofabrik (poland-latest.osm.pbf). Czytamy go strumieniowo biblioteką pyosmium,
zostawiając tylko obiekty z interesującymi kluczami tagów. Dla obiektów-obszarów (way, np. budynek
sklepu) punkt = średnia współrzędnych ich wierzchołków — wystarczające dla małych obiektów.
"""
import duckdb
import h3
import osmium
import pandas as pd

from backend.app.catalog import match_types

PLACE_KINDS = ("city", "town", "village", "suburb", "neighbourhood", "quarter", "hamlet")
# Klucze tagów, od których zależy dopasowanie do typów (patrz catalog.py) i nazw miejsc.
KEYS = ("shop", "amenity", "craft", "leisure", "place")
H3_RES = 8


def _point(obj) -> tuple[float, float] | None:
    """(lat, lng) obiektu: dla węzła jego położenie, dla way średnia wierzchołków."""
    if obj.is_node():
        return (obj.location.lat, obj.location.lon) if obj.location.valid() else None
    nodes = [n for n in obj.nodes if n.location.valid()]
    if len(nodes) > 1 and nodes[0].ref == nodes[-1].ref:
        nodes = nodes[:-1]  # zamknięty obrys: ostatni wierzchołek powtarza pierwszy
    if not nodes:
        return None
    return (sum(n.location.lat for n in nodes) / len(nodes), sum(n.location.lon for n in nodes) / len(nodes))


def extract(pbf_path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Zwraca (poi, places). Relacje pomijamy; jeden obiekt może dać kilka wierszy poi (kilka typów)."""
    poi_rows, place_rows = [], []
    # with_locations() zapamiętuje położenia węzłów, żeby way miały współrzędne wierzchołków;
    # filtr po kluczach działa dopiero na obiektach zwracanych do pętli.
    processor = (osmium.FileProcessor(str(pbf_path), osmium.osm.NODE | osmium.osm.WAY)
                 .with_locations()
                 .with_filter(osmium.filter.KeyFilter(*KEYS)))
    for obj in processor:
        tags = {t.k: t.v for t in obj.tags}
        point = _point(obj)
        if point is None:
            continue
        lat, lng = point
        name = tags.get("name")
        osm_id = ("n" if obj.is_node() else "w") + str(obj.id)
        for type_id in match_types(tags):
            poi_rows.append((osm_id, type_id, name, lat, lng))
        if tags.get("place") in PLACE_KINDS and name:
            place_rows.append((name, tags["place"], lat, lng))
    poi = pd.DataFrame(poi_rows, columns=["osm_id", "type_id", "name", "lat", "lng"])
    places = pd.DataFrame(place_rows, columns=["name", "kind", "lat", "lng"])
    return poi, places


def _with_h3(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["h3"] = [h3.latlng_to_cell(lat, lng, H3_RES) for lat, lng in zip(df["lat"], df["lng"])]
    return df


def build_poi_tables(pbf_path, con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Zapisuje tabele poi(osm_id, type_id, name, lat, lng, h3) i places(name, kind, lat, lng, h3)."""
    poi, places = extract(pbf_path)
    for table, df in (("poi", _with_h3(poi)), ("places", _with_h3(places))):
        con.register("df_in", df)
        con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM df_in")
        con.unregister("df_in")
    return {"poi": len(poi), "places": len(places)}
